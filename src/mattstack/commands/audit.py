"""Audit command orchestrator."""

from __future__ import annotations

import difflib
import json
from pathlib import Path

import typer
from rich.markup import escape

from mattstack.auditors.base import AuditConfig, AuditReport, AuditType, BaseAuditor, Severity
from mattstack.auditors.dependencies import DependencyAuditor
from mattstack.auditors.endpoints import EndpointAuditor
from mattstack.auditors.quality import CodeQualityAuditor
from mattstack.auditors.report import print_report, write_todo
from mattstack.auditors.tests import CoverageAuditor
from mattstack.auditors.types import TypeSafetyAuditor
from mattstack.auditors.vulnerabilities import VulnerabilityAuditor
from mattstack.utils.console import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
    write_raw,
)

SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
}

AUDITOR_CLASSES: dict[AuditType, type[BaseAuditor]] = {
    AuditType.TYPES: TypeSafetyAuditor,
    AuditType.QUALITY: CodeQualityAuditor,
    AuditType.ENDPOINTS: EndpointAuditor,
    AuditType.TESTS: CoverageAuditor,
    AuditType.DEPENDENCIES: DependencyAuditor,
    AuditType.VULNERABILITIES: VulnerabilityAuditor,
}


def run_audit(
    path: Path,
    *,
    audit_types: list[str] | None = None,
    live: bool = False,
    no_todo: bool = False,
    json_output: bool = False,
    fix: bool = False,
    base_url: str = "http://localhost:8000",
    min_severity: str | None = None,
    html_output: bool = False,
) -> None:
    """Run audit on a project directory.

    Exits 1 when any error-severity finding exists, regardless of ``min_severity``.
    """
    project_path = path.resolve()

    if not project_path.is_dir():
        print_error(f"Not a directory: {project_path}")
        raise typer.Exit(code=1)

    # Parse audit type strings
    types: list[AuditType] | None = None
    if audit_types:
        types = []
        for t in audit_types:
            try:
                types.append(AuditType(t))
            except ValueError:
                valid = ", ".join(at.value for at in AuditType)
                suggestion = difflib.get_close_matches(t, [at.value for at in AuditType], n=1)
                msg = f"Unknown audit type: '{t}'. Valid: {valid}"
                if suggestion:
                    msg += f". Did you mean '{suggestion[0]}'?"
                print_error(msg)
                raise typer.Exit(code=1) from None

    # Parse min severity string
    parsed_severity: Severity | None = None
    if min_severity:
        try:
            parsed_severity = Severity(min_severity)
        except ValueError:
            valid = ", ".join(s.value for s in Severity)
            suggestion = difflib.get_close_matches(min_severity, [s.value for s in Severity], n=1)
            msg = f"Unknown severity: '{min_severity}'. Valid: {valid}"
            if suggestion:
                msg += f". Did you mean '{suggestion[0]}'?"
            print_error(msg)
            raise typer.Exit(code=1) from None

    config = AuditConfig(
        project_path=project_path,
        audit_types=types,
        live=live,
        write_todo=not no_todo,
        json_output=json_output,
        fix=fix,
        base_url=base_url,
        min_severity=parsed_severity,
    )

    if not json_output:
        console.print(f"\n[bold cyan]Auditing:[/bold cyan] {escape(str(project_path))}\n")

    report = AuditReport()
    auditor_instances: list[BaseAuditor] = []

    # Run each applicable auditor
    for audit_type, auditor_cls in AUDITOR_CLASSES.items():
        if not config.should_run(audit_type):
            continue

        if not json_output:
            print_info(f"Running {audit_type.value} audit...")

        auditor = auditor_cls(config)
        findings = auditor.run()
        report.findings.extend(findings)
        report.auditors_run.append(audit_type.value)
        auditor_instances.append(auditor)

        if not json_output and findings:
            console.print(f"  Found {len(findings)} issues")

    # Run plugins
    from mattstack.auditors.plugins import discover_plugins

    plugin_classes = discover_plugins(project_path)
    for plugin_cls in plugin_classes:
        if not json_output:
            print_info(f"Running plugin: {plugin_cls.__name__}...")
        auditor = plugin_cls(config)
        findings = auditor.run()
        report.findings.extend(findings)
        report.auditors_run.append(f"plugin:{plugin_cls.__name__}")

    error_count = sum(1 for f in report.findings if f.severity == Severity.ERROR)

    # Filter findings by minimum severity (display only; never hides the exit status)
    if config.min_severity is not None:
        min_order = SEVERITY_ORDER[config.min_severity]
        report.findings = [f for f in report.findings if SEVERITY_ORDER[f.severity] >= min_order]

    # Output results
    if json_output:
        write_raw(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report)

        # Auto-fix summary
        if fix:
            total_fixes = 0
            for auditor in auditor_instances:
                if isinstance(auditor, CodeQualityAuditor):
                    total_fixes += auditor.fix_count
            if total_fixes:
                print_info(f"Auto-fix applied: {total_fixes} debug statement(s) removed")
            else:
                print_info("No auto-fixable issues found")

        # Write to todo.md
        if config.write_todo:
            todo_path = write_todo(report, project_path)
            if todo_path:
                print_success(f"Wrote findings to {todo_path}")
            elif report.findings:
                print_info("No actionable findings to write to todo.md")

        # HTML dashboard
        if html_output:
            from mattstack.auditors.html_report import generate_html_report

            html_content = generate_html_report(report, project_path)
            html_path = project_path / "audit-report.html"
            html_path.write_text(html_content, encoding="utf-8")
            print_success(f"HTML report written to {html_path}")

        # Exit summary
        if error_count:
            print_warning(f"{error_count} errors need attention")
        elif report.warning_count:
            print_info(f"{report.warning_count} warnings to review")
        else:
            print_success("Project looks clean!")

    if error_count:
        raise typer.Exit(code=1)
