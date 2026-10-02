"""Client command: unified frontend package manager wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape

from mattstack.project import resolve_project
from mattstack.utils.console import console, print_error, print_info, print_success
from mattstack.utils.package_manager import (
    PackageManager,
    build_add_cmd,
    build_exec_cmd,
    build_install_cmd,
    build_remove_cmd,
    build_run_cmd,
    resolve_package_manager_source,
    run_pm_command,
)

client_app = typer.Typer(
    name="client",
    help="Frontend package manager commands (bun/npm/yarn/pnpm).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _package_dir(path: Path) -> Path | None:
    """Return the frontend package directory for ``path``, if one exists.

    The resolved project frontend wins, so a nested working directory still
    finds `frontend/`. Any other directory with a package.json also works.
    """
    root = path.resolve()
    for candidate in (resolve_project(root).frontend_dir, root / "frontend", root):
        if (candidate / "package.json").exists():
            return candidate
    return None


def _frontend_dir(path: Path) -> Path:
    """Return the frontend package directory for ``path``, or exit when none exists."""
    work_dir = _package_dir(path)
    if work_dir is None:
        print_error(f"No package.json found in {path.resolve()} or its frontend/")
        raise typer.Exit(code=1)
    return work_dir


def _resolve(path: Path, pm_override: str | None) -> tuple[Path, PackageManager]:
    """Resolve working directory and package manager."""
    work_dir = _frontend_dir(path)
    try:
        pm = resolve_package_manager_source(work_dir, pm_override).manager
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=2) from None
    return work_dir, pm


@client_app.command("add")
def add(
    packages: Annotated[list[str], typer.Argument(help="Packages to install")],
    dev: Annotated[bool, typer.Option("--dev", "-D", help="Install as dev dependency")] = False,
    exact: Annotated[
        bool,
        typer.Option("--exact", "-E", help="Pin the exact resolved version (no ^ or ~ range)"),
    ] = False,
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
    pm: Annotated[
        str | None, typer.Option("--pm", help="Package manager: bun, npm, yarn, pnpm")
    ] = None,
) -> None:
    """Add packages to the frontend project."""
    work_dir, resolved_pm = _resolve(path or Path.cwd(), pm)
    cmd = build_add_cmd(resolved_pm, packages, dev=dev, exact=exact)
    print_info(f"[{resolved_pm.value}] {cmd}")
    result = run_pm_command(cmd, cwd=work_dir)
    if result.returncode == 0:
        print_success(f"Installed: {', '.join(packages)}")
    else:
        print_error(f"Failed with exit code {result.returncode}")
        raise typer.Exit(code=result.returncode)


@client_app.command("remove")
def remove(
    packages: Annotated[list[str], typer.Argument(help="Packages to remove")],
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
    pm: Annotated[
        str | None, typer.Option("--pm", help="Package manager: bun, npm, yarn, pnpm")
    ] = None,
) -> None:
    """Remove packages from the frontend project."""
    work_dir, resolved_pm = _resolve(path or Path.cwd(), pm)
    cmd = build_remove_cmd(resolved_pm, packages)
    print_info(f"[{resolved_pm.value}] {cmd}")
    result = run_pm_command(cmd, cwd=work_dir)
    if result.returncode == 0:
        print_success(f"Removed: {', '.join(packages)}")
    else:
        print_error(f"Failed with exit code {result.returncode}")
        raise typer.Exit(code=result.returncode)


@client_app.command("install")
def install(
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
    pm: Annotated[
        str | None, typer.Option("--pm", help="Package manager: bun, npm, yarn, pnpm")
    ] = None,
) -> None:
    """Install all frontend dependencies."""
    work_dir, resolved_pm = _resolve(path or Path.cwd(), pm)
    cmd = build_install_cmd(resolved_pm)
    print_info(f"[{resolved_pm.value}] {cmd}")
    result = run_pm_command(cmd, cwd=work_dir)
    if result.returncode == 0:
        print_success("Dependencies installed")
    else:
        print_error(f"Failed with exit code {result.returncode}")
        raise typer.Exit(code=result.returncode)


@client_app.command("run")
def run_script(
    script: Annotated[str, typer.Argument(help="Script name from package.json")],
    extra: Annotated[list[str] | None, typer.Argument(help="Extra arguments")] = None,
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
    pm: Annotated[
        str | None, typer.Option("--pm", help="Package manager: bun, npm, yarn, pnpm")
    ] = None,
) -> None:
    """Run a package.json script."""
    work_dir, resolved_pm = _resolve(path or Path.cwd(), pm)
    cmd = build_run_cmd(resolved_pm, script, extra)
    print_info(f"[{resolved_pm.value}] {cmd}")
    result = run_pm_command(cmd, cwd=work_dir)
    raise typer.Exit(code=result.returncode)


@client_app.command("dev")
def dev(
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
    pm: Annotated[
        str | None, typer.Option("--pm", help="Package manager: bun, npm, yarn, pnpm")
    ] = None,
) -> None:
    """Start the frontend dev server (runs 'dev' script)."""
    work_dir, resolved_pm = _resolve(path or Path.cwd(), pm)
    cmd = build_run_cmd(resolved_pm, "dev")
    print_info(f"[{resolved_pm.value}] {cmd}")
    result = run_pm_command(cmd, cwd=work_dir)
    raise typer.Exit(code=result.returncode)


@client_app.command("build")
def build(
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
    pm: Annotated[
        str | None, typer.Option("--pm", help="Package manager: bun, npm, yarn, pnpm")
    ] = None,
) -> None:
    """Build the frontend for production (runs 'build' script)."""
    work_dir, resolved_pm = _resolve(path or Path.cwd(), pm)
    cmd = build_run_cmd(resolved_pm, "build")
    print_info(f"[{resolved_pm.value}] {cmd}")
    result = run_pm_command(cmd, cwd=work_dir)
    if result.returncode == 0:
        print_success("Build complete")
    else:
        print_error(f"Build failed with exit code {result.returncode}")
        raise typer.Exit(code=result.returncode)


@client_app.command("exec")
def exec_bin(
    binary: Annotated[str, typer.Argument(help="Binary to execute (bunx/npx/pnpm dlx)")],
    extra: Annotated[
        list[str] | None,
        typer.Argument(help="Arguments for the binary. Put them after -- when they start with -"),
    ] = None,
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
    pm: Annotated[
        str | None, typer.Option("--pm", help="Package manager: bun, npm, yarn, pnpm")
    ] = None,
) -> None:
    """Execute a package binary (like bunx/npx).

    Pass options for the binary after a `--` separator, for example
    `mattstack client exec tsc -- --noEmit`. mattstack does not parse
    anything after `--`.
    """
    work_dir, resolved_pm = _resolve(path or Path.cwd(), pm)
    cmd = build_exec_cmd(resolved_pm, binary, extra)
    print_info(f"[{resolved_pm.value}] {cmd}")
    result = run_pm_command(cmd, cwd=work_dir)
    raise typer.Exit(code=result.returncode)


@client_app.command("which")
def which_pm(
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
) -> None:
    """Show which package manager would be used and why."""
    root = (path or Path.cwd()).resolve()
    frontend_dir = resolve_project(root).frontend_dir
    work_dir = frontend_dir if (frontend_dir / "package.json").exists() else root
    try:
        resolution = resolve_package_manager_source(work_dir)
    except ValueError as error:
        print_error(str(error))
        raise typer.Exit(code=2) from None

    console.print(f"[bold cyan]Package manager:[/bold cyan] {resolution.manager.value}")
    console.print(f"[dim]Source:[/dim] {escape(resolution.source)}")
