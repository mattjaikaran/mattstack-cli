"""Info command: show presets, repos, and config options."""

from __future__ import annotations

from rich.markup import escape

from mattstack.config import get_repo_urls
from mattstack.presets import list_presets
from mattstack.utils.console import console, create_table
from mattstack.utils.sources import redact_repo


def run_info() -> None:
    """Display all available presets and source repos."""
    console.print()
    _show_presets()
    console.print()
    _show_repos()
    console.print()
    _show_usage()
    console.print()


def _show_presets() -> None:
    table = create_table("Available Presets", ["Name", "Type", "Variant", "Description"])
    for preset in list_presets():
        table.add_row(
            f"[cyan]{preset.name}[/cyan]",
            preset.project_type.value,
            preset.variant.value,
            preset.description,
        )
    console.print(table)


def _show_repos() -> None:
    table = create_table("Source Repositories", ["Key", "URL"])
    for key, url in get_repo_urls().items():
        table.add_row(f"[cyan]{escape(key)}[/cyan]", escape(redact_repo(url)))
    console.print(table)


def _show_usage() -> None:
    console.print("[bold]Usage Examples:[/bold]")
    console.print()
    examples = [
        ("mattstack init", "Interactive wizard"),
        ("mattstack init my-app --preset starter-fullstack", "Preset mode"),
        ("mattstack init my-app --preset rsbuild-fullstack", "Rsbuild + Django"),
        ("mattstack init my-app --preset kibo-fullstack", "Kibo UI + Django"),
        ("mattstack init my-app --preset nextjs-fullstack", "Next.js + Django"),
        ("mattstack init my-app --preset b2b-fullstack --ios", "With iOS"),
        ("mattstack init --config stack.yaml", "Config file"),
        ("mattstack add frontend --framework react-rsbuild", "Add Rsbuild to existing"),
        ("mattstack add frontend --framework nextjs", "Add Next.js to existing"),
        ("mattstack doctor", "Check environment"),
    ]
    for cmd, desc in examples:
        console.print(f"  [cyan]{cmd}[/cyan]  {desc}")
