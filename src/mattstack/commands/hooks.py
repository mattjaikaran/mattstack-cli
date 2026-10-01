"""Hooks command: git hooks management for fullstack monorepos."""

from __future__ import annotations

import subprocess  # nosec B404 # Required CLI subprocess support.
import time
from pathlib import Path
from typing import Annotated

import typer

from mattstack.utils.console import (
    console,
    create_table,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from mattstack.utils.process import command_available

hooks_app = typer.Typer(
    name="hooks",
    help="Git hooks management (install, status, run).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@hooks_app.command("install")
def install(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
) -> None:
    """Install pre-commit hooks."""
    project = (path or Path.cwd()).resolve()
    start = time.perf_counter()

    console.print()
    console.print("[bold cyan]mattstack hooks install[/bold cyan]")
    console.print()

    # Check .pre-commit-config.yaml exists
    config_file = project / ".pre-commit-config.yaml"
    if not config_file.exists():
        print_error(f"No .pre-commit-config.yaml found in {project}")
        print_info("Generate one with: mattstack init or create it manually")
        raise typer.Exit(code=1)

    # Check pre-commit available
    if not command_available("pre-commit"):
        print_error("pre-commit is not installed")
        print_info("Install with: uv tool install pre-commit")
        raise typer.Exit(code=1)

    # Install pre-commit hooks
    print_info("Installing pre-commit hooks...")
    result = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
        ["pre-commit", "install"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print_error(f"pre-commit install failed: {result.stderr.strip()}")
        raise typer.Exit(code=1)
    print_success("pre-commit hooks installed")

    # Install commit-msg hook if commitlint is configured
    config_text = config_file.read_text(encoding="utf-8")
    if "commitlint" in config_text or "commit-msg" in config_text:
        print_info("Installing commit-msg hook (commitlint detected)...")
        result = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
            ["pre-commit", "install", "--hook-type", "commit-msg"],
            cwd=project,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print_warning(f"commit-msg hook install failed: {result.stderr.strip()}")
        else:
            print_success("commit-msg hook installed")

    elapsed = time.perf_counter() - start
    console.print(f"[dim]({elapsed:.1f}s)[/dim]")


@hooks_app.command("status")
def status(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
) -> None:
    """Show installed git hooks."""
    project = (path or Path.cwd()).resolve()

    console.print()
    console.print("[bold cyan]mattstack hooks status[/bold cyan]")
    console.print()

    hooks_dir = project / ".git" / "hooks"
    if not hooks_dir.is_dir():
        print_error(f"No .git/hooks directory found in {project}")
        print_info("Is this a git repository?")
        raise typer.Exit(code=1)

    hook_types = [
        "pre-commit",
        "commit-msg",
        "pre-push",
        "pre-merge-commit",
        "prepare-commit-msg",
        "post-commit",
        "post-merge",
    ]

    table = create_table("Git Hooks", ["Hook", "Status", "Source"])
    installed_count = 0

    for hook in hook_types:
        hook_file = hooks_dir / hook
        if hook_file.exists() and not hook_file.name.endswith(".sample"):
            content = hook_file.read_text(encoding="utf-8", errors="replace")
            source = "pre-commit" if "pre-commit" in content else "custom"
            table.add_row(hook, "[green]installed[/green]", source)
            installed_count += 1
        else:
            table.add_row(hook, "[dim]not installed[/dim]", "-")

    console.print(table)
    console.print()

    has_config = (project / ".pre-commit-config.yaml").exists()
    if has_config and installed_count == 0:
        print_warning(".pre-commit-config.yaml exists but no hooks installed")
        print_info("Run: mattstack hooks install")
    elif not has_config:
        print_info("No .pre-commit-config.yaml found")
    else:
        print_success(f"{installed_count} hook(s) installed")


@hooks_app.command("run")
def run(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
) -> None:
    """Run pre-commit hooks on all files."""
    project = (path or Path.cwd()).resolve()
    start = time.perf_counter()

    console.print()
    console.print("[bold cyan]mattstack hooks run[/bold cyan]")
    console.print()

    if not command_available("pre-commit"):
        print_error("pre-commit is not installed")
        print_info("Install with: uv tool install pre-commit")
        raise typer.Exit(code=1)

    if not (project / ".pre-commit-config.yaml").exists():
        print_error(f"No .pre-commit-config.yaml found in {project}")
        raise typer.Exit(code=1)

    print_info("Running pre-commit on all files...")
    result = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
        ["pre-commit", "run", "--all-files"],
        cwd=project,
        text=True,
    )

    elapsed = time.perf_counter() - start
    console.print()

    if result.returncode == 0:
        print_success("All hooks passed")
    else:
        print_error("Some hooks failed")

    console.print(f"[dim]({elapsed:.1f}s)[/dim]")

    if result.returncode != 0:
        raise typer.Exit(code=1)
