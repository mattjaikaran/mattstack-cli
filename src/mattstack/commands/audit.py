"""Audit command: run Gauntlet and format the findings.

MattStack implements no checks. This module shells out to
`gauntlet check --tier=<tier> --json` and passes the parsed result to
`mattstack.gauntlet.report`.
"""

from __future__ import annotations

import difflib
from pathlib import Path

import typer

from mattstack.gauntlet.client import (
    DEFAULT_TIER,
    GauntletError,
    GauntletUnavailableError,
    check,
    load_config,
)
from mattstack.gauntlet.html_report import generate_html_report
from mattstack.gauntlet.models import ENGINES, RunResult, Severity
from mattstack.gauntlet.report import (
    install_instructions,
    print_json,
    print_report,
    write_todo,
)
from mattstack.utils.console import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
)

# The default value of the `--base-url` option. Used to decide whether the
# user set the option explicitly.
DEFAULT_BASE_URL = "http://localhost:8000"


def run_audit(
    path: Path,
    *,
    audit_types: list[str] | None = None,
    live: bool = False,
    no_todo: bool = False,
    json_output: bool = False,
    fix: bool = False,
    base_url: str = DEFAULT_BASE_URL,
    min_severity: str | None = None,
    html_output: bool = False,
    tier: str = DEFAULT_TIER,
    skip_if_absent: bool | None = None,
) -> None:
    """Run Gauntlet on a project directory and format the findings."""
    project_path = path.resolve()
    if not project_path.is_dir():
        print_error(f"Not a directory: {project_path}")
        raise typer.Exit(code=1)

    engine_filter = _parse_audit_types(audit_types)
    severity = _parse_severity(min_severity)
    _warn_about_removed_flags(live=live, fix=fix, base_url=base_url)

    settings = load_config(project_path)
    skip_absent = settings.skip_if_absent if skip_if_absent is None else skip_if_absent

    if not json_output:
        console.print(f"\n[bold cyan]Auditing:[/bold cyan] {project_path}")
        console.print(f"[dim]Verification engine: Gauntlet (tier: {tier})[/dim]")

    try:
        result = check(project_path, tier=tier, config=settings)
    except GauntletUnavailableError as exc:
        if not skip_absent:
            print_error(install_instructions(exc.binary))
            raise typer.Exit(code=1) from None
        note = " ".join(install_instructions(exc.binary).split())
        _emit(
            RunResult.empty(tier=tier, reason=note),
            project_path,
            json_output=json_output,
            html_output=html_output,
            no_todo=no_todo,
            skipped=True,
            note=note,
        )
        return
    except GauntletError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    result = result.filter_checks(engine_filter).filter_severity(severity)
    _emit(
        result,
        project_path,
        json_output=json_output,
        html_output=html_output,
        no_todo=no_todo,
    )


def _emit(
    result: RunResult,
    project_path: Path,
    *,
    json_output: bool,
    html_output: bool,
    no_todo: bool,
    skipped: bool = False,
    note: str = "",
) -> None:
    """Write the run to the requested outputs."""
    if json_output:
        # The envelope carries `skipped` and `skip_reason`, so a consumer
        # never reads a run that did not happen as a clean pass.
        print_json(result)
        return

    print_report(result, project_path, skipped=skipped, note=note)
    if skipped:
        return

    if not no_todo:
        todo_path = write_todo(result, project_path)
        if todo_path:
            print_success(f"Wrote findings to {todo_path}")
        elif result.findings:
            print_info("No actionable findings to write to todo.md")

    if html_output:
        html_path = project_path / "audit-report.html"
        html_path.write_text(generate_html_report(result, project_path), encoding="utf-8")
        print_success(f"HTML report written to {html_path}")

    if result.error_count:
        print_warning(f"{result.error_count} errors need attention")
    elif result.warning_count:
        print_info(f"{result.warning_count} warnings to review")
    else:
        print_success("Project looks clean!")


def _parse_audit_types(audit_types: list[str] | None) -> set[str] | None:
    """Validate `--type` values and return them as a filter set.

    Accepts a Gauntlet engine name (`sentinel`) or a full check id
    (`sentinel:secret`). Returns ``None`` when you set no filter.
    """
    if not audit_types:
        return None

    selected: set[str] = set()
    for raw in audit_types:
        value = raw.strip().lower()
        engine = value.split(":", 1)[0]
        if engine not in ENGINES:
            valid = ", ".join(ENGINES)
            suggestion = difflib.get_close_matches(engine, list(ENGINES), n=1)
            msg = f"Unknown audit type: '{raw}'. Valid: {valid}"
            if suggestion:
                msg += f". Did you mean '{suggestion[0]}'?"
            print_error(msg)
            raise typer.Exit(code=1) from None
        selected.add(value)
    return selected


def _parse_severity(min_severity: str | None) -> Severity | None:
    """Validate the `--severity` value."""
    if not min_severity:
        return None
    try:
        return Severity(min_severity)
    except ValueError:
        valid = ", ".join(s.value for s in Severity)
        suggestion = difflib.get_close_matches(min_severity, [s.value for s in Severity], n=1)
        msg = f"Unknown severity: '{min_severity}'. Valid: {valid}"
        if suggestion:
            msg += f". Did you mean '{suggestion[0]}'?"
        print_error(msg)
        raise typer.Exit(code=1) from None


def _warn_about_removed_flags(*, live: bool, fix: bool, base_url: str) -> None:
    """Explain the options whose behavior left mattstack.

    Gauntlet does not probe live endpoints and does not auto-fix, so these
    options no longer change the audit result.
    """
    if live or base_url != DEFAULT_BASE_URL:
        print_info("Gauntlet does not probe live endpoints; --live and --base-url have no effect.")
    if fix:
        print_warning("Gauntlet does not auto-fix; run `mattstack lint --fix` instead.")
