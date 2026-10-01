"""Rich console utilities.

Status helpers treat ``message`` as plain text: Rich markup in it is escaped,
so dynamic paths, labels and tool output render literally. Errors and
warnings go to stderr so stdout stays usable for structured output.
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()
err_console = Console(stderr=True)

_verbose = False
_quiet = False


def set_verbose(enabled: bool) -> None:
    global _verbose
    _verbose = enabled


def set_quiet(enabled: bool) -> None:
    global _quiet
    _quiet = enabled


def is_quiet() -> bool:
    """Return whether nonessential output is disabled."""
    return _quiet


def print_verbose(message: str) -> None:
    if _verbose:
        err_console.print(f"[dim]\\[VERBOSE][/dim] {escape(message)}")


def print_info(message: str) -> None:
    if _quiet:
        return
    console.print(f"[blue]\\[INFO][/blue] {escape(message)}")


def print_success(message: str) -> None:
    if _quiet:
        return
    console.print(f"[green]\\[SUCCESS][/green] {escape(message)}")


def print_warning(message: str) -> None:
    if _quiet:
        return
    err_console.print(f"[yellow]\\[WARNING][/yellow] {escape(message)}")


def print_error(message: str) -> None:
    err_console.print(f"[red]\\[ERROR][/red] {escape(message)}")


def print_step(step: int, total: int, message: str) -> None:
    if _quiet:
        return
    console.print(f"[cyan]\\[{step}/{total}][/cyan] {escape(message)}")


def write_raw(text: str) -> None:
    """Write ``text`` to stdout verbatim: no markup, emoji, highlighting or wrapping."""
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    sys.stdout.flush()


def print_header(title: str) -> None:
    console.print(Panel(title, border_style="cyan", expand=False))


def create_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    )


def create_table(title: str, columns: list[str]) -> Table:
    table = Table(title=title, show_header=True, header_style="bold cyan")
    for col in columns:
        table.add_column(col)
    return table
