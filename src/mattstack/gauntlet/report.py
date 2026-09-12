"""Render Gauntlet findings for a human, for JSON, and for tasks/todo.md.

This module is the only place that knows how mattstack presents a run. It
implements no checks. Every value it prints comes from
`mattstack.gauntlet.models.RunResult`.

The HTML dashboard lives in `mattstack.gauntlet.html_report`.
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.table import Table
from rich.text import Text

from mattstack.gauntlet.models import Finding, RunResult, Severity
from mattstack.utils.console import console

# Markers around the generated block in tasks/todo.md. The audit rewrites
# only the text between them, so a repeated run stays idempotent.
AUDIT_START = "<!-- audit:start -->"
AUDIT_END = "<!-- audit:end -->"

SEVERITY_ICONS: dict[Severity, str] = {
    Severity.ERROR: "[red]ERR[/red]",
    Severity.WARNING: "[yellow]WRN[/yellow]",
    Severity.INFO: "[blue]INF[/blue]",
}


def install_instructions(binary: str = "gauntlet") -> str:
    """Return the message shown when Gauntlet is not installed."""
    return (
        "Gauntlet is not installed. mattstack delegates all audit checks to "
        "Gauntlet.\n"
        f"  Install it from https://github.com/mattjaikaran/gauntlet and put "
        f"'{binary}' on PATH.\n"
        "  Or run `mattstack audit --skip-if-absent` to continue without it."
    )


def print_report(
    result: RunResult,
    project_path: Path,
    *,
    skipped: bool = False,
    note: str = "",
) -> None:
    """Print findings as a Rich table, then a summary line."""
    console.print(
        f"\n[bold]Tier:[/bold] {result.tier or 'unknown'}"
        f"  [bold]Gauntlet:[/bold] {result.gauntlet_version or 'unknown'}"
        f"  [bold]Duration:[/bold] {result.duration_ms / 1000:.1f}s"
    )

    if skipped:
        console.print(f"\n[yellow]Audit skipped.[/yellow] {note}")
        return

    if not result.findings:
        console.print("\n[green]No issues found.[/green]")
        return

    table = Table(title="Audit Findings", show_header=True, header_style="bold cyan")
    table.add_column("Sev", width=4)
    table.add_column("Check", width=18)
    table.add_column("Location", width=30)
    table.add_column("Message", min_width=40)

    for finding in sorted(result.findings, key=lambda f: (f.severity.value, f.check, f.location)):
        table.add_row(
            SEVERITY_ICONS[finding.severity],
            finding.check,
            finding.location,
            finding.title,
        )

    console.print()
    console.print(table)
    console.print(_summary_line(result))


def _summary_line(result: RunResult) -> Text:
    """Build the coloured summary line."""
    line = Text("\nSummary: ")
    line.append(f"{result.error_count} errors", style="red")
    line.append(", ")
    line.append(f"{result.warning_count} warnings", style="yellow")
    line.append(", ")
    line.append(f"{result.info_count} info", style="blue")
    line.append(f" ({len(result.findings)} total, {result.blocking_count} blocking)")
    return line


def print_json(result: RunResult) -> None:
    """Print the run as JSON on stdout."""
    console.print_json(json.dumps(result.to_audit_dict(), indent=2))


def write_todo(result: RunResult, project_path: Path) -> Path | None:
    """Write actionable findings to tasks/todo.md. Idempotent.

    Returns the path written, or ``None`` when no finding is actionable.
    """
    actionable = [f for f in result.findings if f.actionable]
    if not actionable:
        return None

    todo_dir = project_path / "tasks"
    todo_dir.mkdir(parents=True, exist_ok=True)
    todo_path = todo_dir / "todo.md"

    section = _build_audit_section(actionable)
    if todo_path.exists():
        content = _replace_audit_section(todo_path.read_text(encoding="utf-8"), section)
    else:
        content = f"# Project TODO\n\n{section}\n"

    todo_path.write_text(content, encoding="utf-8")
    return todo_path


def _build_audit_section(findings: list[Finding]) -> str:
    """Build the markdown audit section, grouped by category."""
    lines = [AUDIT_START, "## Audit Findings", ""]

    by_category: dict[str, list[Finding]] = {}
    for finding in findings:
        by_category.setdefault(finding.category, []).append(finding)

    for category, items in sorted(by_category.items()):
        lines.append(f"### {category.replace('_', ' ').title()}")
        for item in sorted(items, key=lambda f: (f.severity.value, f.location)):
            icon = "x" if item.severity == Severity.ERROR else " "
            lines.append(
                f"- [{icon}] **{item.severity.value.upper()}** "
                f"`{item.location}` — {item.title} ({item.id})"
            )
            if item.suggested_fix:
                lines.append(f"  - {item.suggested_fix}")
        lines.append("")

    lines.append(AUDIT_END)
    return "\n".join(lines)


def _replace_audit_section(content: str, new_section: str) -> str:
    """Replace the marked audit block, or append it when absent."""
    if AUDIT_START in content and AUDIT_END in content:
        start = content.index(AUDIT_START)
        end = content.index(AUDIT_END) + len(AUDIT_END)
        return content[:start] + new_section + content[end:]
    return content.rstrip() + "\n\n" + new_section + "\n"
