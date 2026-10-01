"""Hooks command: git hooks management for fullstack monorepos."""

from __future__ import annotations

import re
import subprocess  # nosec B404 # Required CLI subprocess support.
import time
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from mattstack.templates.pre_commit_config import HOOK_PREREQUISITES
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

_GIT_HOOK_TYPES = (
    "pre-commit",
    "pre-merge-commit",
    "pre-push",
    "prepare-commit-msg",
    "commit-msg",
    "post-checkout",
    "post-commit",
    "post-merge",
    "post-rewrite",
    "pre-rebase",
)
# Stage names that pre-commit still accepts for older configs.
_LEGACY_STAGES = {"commit": "pre-commit", "push": "pre-push", "merge-commit": "pre-merge-commit"}
# These hooks declare the commit-msg stage in their own manifests, so the
# config may not name it.
_COMMIT_MSG_HOOKS = ("commitlint", "commitizen")


def load_hook_config(config_file: Path) -> dict[str, Any]:
    """Parse .pre-commit-config.yaml; raise ValueError with the fix when it is invalid."""
    try:
        data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(
            f"{config_file} is not valid YAML ({exc}). "
            f"Fix it, then check: pre-commit validate-config {config_file}"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(f"{config_file} must be a mapping with a repos list")
    return data


def _strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _hooks(config: dict[str, Any]) -> list[dict[str, Any]]:
    hooks: list[dict[str, Any]] = []
    for repo in config.get("repos") or []:
        if isinstance(repo, dict):
            hooks.extend(h for h in repo.get("hooks") or [] if isinstance(h, dict))
    return hooks


def required_hook_types(config: dict[str, Any]) -> list[str]:
    """Return the git hook types the config's hooks run in, in git's order."""
    stages = {"pre-commit", *_strings(config.get("default_install_hook_types"))}
    for hook in _hooks(config):
        stages.update(_strings(hook.get("stages")))
        if any(name in str(hook.get("id", "")) for name in _COMMIT_MSG_HOOKS):
            stages.add("commit-msg")
    types = {_LEGACY_STAGES.get(stage, stage) for stage in stages}
    return [name for name in _GIT_HOOK_TYPES if name in types]


def missing_prerequisites(config: dict[str, Any]) -> list[str]:
    """Return tools that hook entries run but that are not on PATH."""
    entries = "\n".join(str(hook.get("entry", "")) for hook in _hooks(config))
    return [
        tool
        for tool in HOOK_PREREQUISITES
        if re.search(rf"(?<![\w./-]){tool}(?=\s)", entries) and not command_available(tool)
    ]


def _hooks_dir(project: Path) -> Path | None:
    """Return the directory git runs hooks from, honouring core.hooksPath and worktrees."""
    result = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
        ["git", "rev-parse", "--git-path", "hooks"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return (project / result.stdout.strip()).resolve()


@hooks_app.command("install")
def install(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
) -> None:
    """Install the git hook types that .pre-commit-config.yaml uses, then verify them."""
    project = (path or Path.cwd()).resolve()
    start = time.perf_counter()

    console.print()
    console.print("[bold cyan]mattstack hooks install[/bold cyan]")
    console.print()

    config_file = project / ".pre-commit-config.yaml"
    if not config_file.exists():
        print_error(f"No .pre-commit-config.yaml found in {project}")
        print_info("Generate one with: mattstack init or create it manually")
        raise typer.Exit(code=1)

    if not command_available("pre-commit"):
        print_error("pre-commit is not installed")
        print_info("Install with: uv tool install pre-commit")
        raise typer.Exit(code=1)

    try:
        config = load_hook_config(config_file)
    except (OSError, ValueError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    missing = missing_prerequisites(config)
    if missing:
        for tool in missing:
            print_error(f"{tool} is not on PATH; a hook entry in {config_file} runs it")
            print_info(f"Install it: {HOOK_PREREQUISITES[tool]}")
        print_info(f"Then rerun: mattstack hooks install --path {project}")
        raise typer.Exit(code=1)

    hook_types = required_hook_types(config)
    for hook_type in hook_types:
        result = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
            ["pre-commit", "install", "--hook-type", hook_type],
            cwd=project,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            print_error(f"pre-commit install --hook-type {hook_type} failed: {detail}")
            raise typer.Exit(code=1)

    hooks_dir = _hooks_dir(project)
    if hooks_dir is None:
        print_error(f"git cannot resolve the hooks directory of {project}")
        print_info(f"Check with: git -C {project} rev-parse --git-path hooks")
        raise typer.Exit(code=1)
    absent = [name for name in hook_types if not _is_pre_commit_hook(hooks_dir / name)]
    if absent:
        print_error(
            "pre-commit reported success, but these git hooks are missing in "
            f"{hooks_dir}: {', '.join(absent)}"
        )
        print_info(f"Check with: git -C {project} rev-parse --git-path hooks")
        raise typer.Exit(code=1)
    for hook_type in hook_types:
        print_success(f"{hook_type} hook installed ({hooks_dir / hook_type})")

    elapsed = time.perf_counter() - start
    console.print(f"[dim]({elapsed:.1f}s)[/dim]")


def _is_pre_commit_hook(hook_file: Path) -> bool:
    if not hook_file.is_file():
        return False
    return "pre-commit" in hook_file.read_text(encoding="utf-8", errors="replace")


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
