"""Typer CLI app for mattstack."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from mattstack.commands.client import client_app
from mattstack.commands.context import context_app

app = typer.Typer(
    name="mattstack",
    help="Scaffold fullstack monorepos from battle-tested boilerplates.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

app.add_typer(client_app, name="client")
app.add_typer(context_app, name="context")


def _register_subgroups() -> None:
    """Lazily register subcommand groups to avoid import-time overhead."""
    from mattstack.commands.board import board_app
    from mattstack.commands.db import db_app
    from mattstack.commands.deps import deps_app
    from mattstack.commands.generate import generate_app
    from mattstack.commands.hooks import hooks_app
    from mattstack.commands.rules import rules_app
    from mattstack.commands.sync import sync_app
    from mattstack.commands.todo import todo_app

    app.add_typer(generate_app, name="generate")
    app.add_typer(db_app, name="db")
    app.add_typer(sync_app, name="sync")
    app.add_typer(deps_app, name="deps")
    app.add_typer(hooks_app, name="hooks")
    app.add_typer(board_app, name="board")
    app.add_typer(todo_app, name="todo")
    app.add_typer(rules_app, name="rules")


_register_subgroups()


@app.callback()
def main(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress non-essential output"),
    ] = False,
) -> None:
    """Scaffold fullstack monorepos from battle-tested boilerplates."""
    if verbose:
        from mattstack.utils.console import set_verbose

        set_verbose(True)
    if quiet:
        from mattstack.utils.console import set_quiet

        set_quiet(True)


@app.command()
def init(
    name: Annotated[
        str | None,
        typer.Argument(help="Project name"),
    ] = None,
    preset: Annotated[
        str | None,
        typer.Option("--preset", "-p", help="Use a preset (e.g. starter-fullstack, b2b-api)"),
    ] = None,
    config: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to YAML config file"),
    ] = None,
    ios: Annotated[
        bool,
        typer.Option("--ios", help="Include iOS client"),
    ] = False,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output directory (default: current)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview what would be generated without creating files"),
    ] = False,
) -> None:
    """Create a new project from boilerplates."""
    from mattstack.commands.init import run_init

    run_init(
        name=name,
        preset=preset,
        config_file=config,
        ios=ios,
        output_dir=output_dir,
        dry_run=dry_run,
    )


@app.command()
def add(
    component: Annotated[
        str,
        typer.Argument(help="Component to add: frontend, backend, ios"),
    ],
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path (default: current directory)"),
    ] = None,
    framework: Annotated[
        str | None,
        typer.Option(
            "--framework",
            "-f",
            help="Frontend framework: react-vite, react-vite-starter, react-rsbuild,"
            " react-rsbuild-kibo, nextjs",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview what would be added without making changes"),
    ] = False,
) -> None:
    """Add a component (frontend, backend, ios) to an existing project."""
    from mattstack.commands.add import run_add

    run_add(
        component=component,
        project_path=path or Path.cwd(),
        framework=framework,
        dry_run=dry_run,
    )


@app.command()
def upgrade(
    path: Annotated[
        Path | None,
        typer.Argument(help="Project path (default: current directory)"),
    ] = None,
    component: Annotated[
        str | None,
        typer.Option("--component", "-c", help="Upgrade specific component: backend, frontend"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview changes without applying them"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite modified files (use with caution)"),
    ] = False,
) -> None:
    """Pull latest boilerplate changes into an existing project."""
    from mattstack.commands.upgrade import run_upgrade

    run_upgrade(
        path=path or Path.cwd(),
        component=component,
        dry_run=dry_run,
        force=force,
    )


@app.command()
def doctor() -> None:
    """Check your development environment."""
    from mattstack.commands.doctor import run_doctor

    run_doctor()


@app.command()
def info() -> None:
    """Show available presets, repos, and usage."""
    from mattstack.commands.info import run_info

    run_info()


@app.command()
def presets() -> None:
    """List available presets, repos, and usage examples."""
    from mattstack.commands.info import run_info

    run_info()


@app.command()
def audit(
    path: Annotated[
        Path | None,
        typer.Argument(help="Project path to audit (default: current directory)"),
    ] = None,
    audit_type: Annotated[
        list[str] | None,
        typer.Option("--type", "-t", help="Audit type: types, quality, endpoints, tests"),
    ] = None,
    live: Annotated[
        bool,
        typer.Option("--live", help="Enable live endpoint probing (GET only)"),
    ] = False,
    no_todo: Annotated[
        bool,
        typer.Option("--no-todo", help="Skip writing to tasks/todo.md"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Auto-remove debug statements"),
    ] = False,
    base_url: Annotated[
        str,
        typer.Option("--base-url", help="Base URL for live endpoint probing"),
    ] = "http://localhost:8000",
    severity: Annotated[
        str | None,
        typer.Option("--severity", "-s", help="Minimum severity: error, warning, info"),
    ] = None,
    html: Annotated[
        bool,
        typer.Option("--html", help="Generate HTML dashboard report"),
    ] = False,
) -> None:
    """Run static analysis on a generated project."""
    from mattstack.commands.audit import run_audit

    run_audit(
        path=path or Path.cwd(),
        audit_types=audit_type,
        live=live,
        no_todo=no_todo,
        json_output=json_output,
        fix=fix,
        base_url=base_url,
        min_severity=severity,
        html_output=html,
    )


@app.command("config")
def config_cmd(
    action: Annotated[
        str,
        typer.Argument(help="Action: show, path, init"),
    ] = "show",
) -> None:
    """Manage user configuration (~/.mattstack/config.yaml)."""
    from mattstack.user_config import (
        USER_CONFIG_PATH,
        init_user_config,
        load_user_config,
    )
    from mattstack.utils.console import console, print_success

    if action == "show":
        config = load_user_config()
        if not config:
            console.print("[dim]No user config found.[/dim]")
            console.print("[dim]Create one with: mattstack config init[/dim]")
            console.print(f"[dim]Expected path: {USER_CONFIG_PATH}[/dim]")
        else:
            import yaml as _yaml  # type: ignore[import-untyped]

            console.print(f"[bold cyan]Config:[/bold cyan] {USER_CONFIG_PATH}\n")
            console.print(_yaml.dump(config, default_flow_style=False))
    elif action == "path":
        typer.echo(str(USER_CONFIG_PATH))
    elif action == "init":
        path = init_user_config()
        print_success(f"Config template created at {path}")
    else:
        from mattstack.utils.console import print_error

        print_error(f"Unknown action: {action}. Use: show, path, init")
        raise typer.Exit(code=1)


@app.command()
def dev(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
    services: Annotated[
        str | None,
        typer.Option("--services", "-s", help="Services to start: backend,frontend,docker"),
    ] = None,
    no_docker: Annotated[
        bool,
        typer.Option("--no-docker", help="Skip Docker infrastructure"),
    ] = False,
) -> None:
    """Start all development services (docker, backend, frontend)."""
    from mattstack.commands.dev import run_dev

    run_dev(path=path or Path.cwd(), services=services, no_docker=no_docker)


@app.command("test")
def test_cmd(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
    backend_only: Annotated[
        bool,
        typer.Option("--backend-only", help="Run backend tests only"),
    ] = False,
    frontend_only: Annotated[
        bool,
        typer.Option("--frontend-only", help="Run frontend tests only"),
    ] = False,
    coverage: Annotated[
        bool,
        typer.Option("--coverage", help="Run with coverage"),
    ] = False,
    parallel: Annotated[
        bool,
        typer.Option("--parallel", help="Run backend and frontend tests in parallel"),
    ] = False,
) -> None:
    """Run tests across backend and frontend."""
    from mattstack.commands.test import run_test

    run_test(
        path=path or Path.cwd(),
        backend_only=backend_only,
        frontend_only=frontend_only,
        coverage=coverage,
        parallel=parallel,
    )


@app.command()
def lint(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Auto-fix lint issues"),
    ] = False,
    format_check: Annotated[
        bool,
        typer.Option("--format-check", help="Check formatting"),
    ] = False,
    backend_only: Annotated[
        bool,
        typer.Option("--backend-only", help="Lint backend only"),
    ] = False,
    frontend_only: Annotated[
        bool,
        typer.Option("--frontend-only", help="Lint frontend only"),
    ] = False,
    parallel: Annotated[
        bool,
        typer.Option("--parallel", help="Run backend and frontend linting in parallel"),
    ] = False,
) -> None:
    """Run linters across backend and frontend."""
    from mattstack.commands.lint import run_lint

    run_lint(
        path=path or Path.cwd(),
        fix=fix,
        format_check=format_check,
        backend_only=backend_only,
        frontend_only=frontend_only,
        parallel=parallel,
    )


@app.command()
def env(
    action: Annotated[
        str,
        typer.Argument(help="Action: check, sync, show"),
    ] = "check",
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
) -> None:
    """Manage environment variables (.env files)."""
    from mattstack.commands.env import run_env

    run_env(action=action, path=path or Path.cwd())


@app.command()
def version() -> None:
    """Show mattstack version."""
    from mattstack.commands.version import run_version

    run_version()


@app.command()
def completions(
    install: Annotated[bool, typer.Option("--install", help="Install shell completions")] = False,
    show: Annotated[bool, typer.Option("--show", help="Show completion script")] = False,
) -> None:
    """Manage shell completions (bash/zsh/fish)."""
    from mattstack.commands.completions import run_completions

    run_completions(install=install, show=show)


@app.command()
def create(
    name: Annotated[
        str | None,
        typer.Argument(help="Project name"),
    ] = None,
    preset: Annotated[
        str | None,
        typer.Option("--preset", "-p", help="Use a preset (e.g. starter-fullstack, b2b-api)"),
    ] = None,
    config: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to YAML config file"),
    ] = None,
    ios: Annotated[
        bool,
        typer.Option("--ios", help="Include iOS client"),
    ] = False,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output directory (default: current)"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview what would be generated without creating files"),
    ] = False,
) -> None:
    """Create a new project (alias for init)."""
    from mattstack.commands.init import run_init

    run_init(
        name=name,
        preset=preset,
        config_file=config,
        ios=ios,
        output_dir=output_dir,
        dry_run=dry_run,
    )


@app.command()
def fmt(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
    backend_only: Annotated[
        bool,
        typer.Option("--backend-only", help="Format backend only"),
    ] = False,
    frontend_only: Annotated[
        bool,
        typer.Option("--frontend-only", help="Format frontend only"),
    ] = False,
) -> None:
    """Format all code (alias for lint --fix --format-check)."""
    from mattstack.commands.lint import run_lint

    run_lint(
        path=path or Path.cwd(),
        fix=True,
        format_check=True,
        backend_only=backend_only,
        frontend_only=frontend_only,
    )


@app.command()
def health(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
    live: Annotated[
        bool,
        typer.Option("--live", help="Probe HTTP endpoints (backend + frontend)"),
    ] = False,
) -> None:
    """Check health of all project services (Docker, DB, Redis, servers)."""
    from mattstack.commands.health import run_health

    run_health(path=path or Path.cwd(), live=live)


@app.command()
def workflow(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
    platform: Annotated[
        str,
        typer.Option("--platform", help="CI platform: github-actions, gitlab-ci"),
    ] = "github-actions",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview without writing files"),
    ] = False,
) -> None:
    """Generate CI/CD workflow files (GitHub Actions, GitLab CI)."""
    from mattstack.commands.workflow import run_generate_workflow

    run_generate_workflow(path=path or Path.cwd(), platform=platform, dry_run=dry_run)


@app.command()
def protect(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview changes without writing"),
    ] = False,
) -> None:
    """Enable branch protection (no-commit-to-branch, CODEOWNERS, GitHub ruleset)."""
    from mattstack.commands.protect import run_protect

    run_protect(path=path or Path.cwd(), dry_run=dry_run)


@app.command()
def notify(
    app: Annotated[str, typer.Option("--app", "-a", help="Application name")] = "",
    commit: Annotated[str, typer.Option("--commit", "-c", help="Deploy commit SHA")] = "",
    env: Annotated[str, typer.Option("--env", "-e", help="Deploy environment")] = "production",
    frontend_url: Annotated[str, typer.Option("--frontend-url", help="Deployed frontend URL")] = "",
    backend_url: Annotated[str, typer.Option("--backend-url", help="Deployed backend URL")] = "",
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
) -> None:
    """Send a deploy-complete notification via the configured backend."""
    from mattstack.commands.notify import run_notify

    run_notify(
        path=path or Path.cwd(),
        app=app,
        commit=commit,
        env=env,
        frontend_url=frontend_url,
        backend_url=backend_url,
    )


@app.command()
def verify(
    scope: Annotated[bool, typer.Option("--scope", help="Enforce the declared plan scope")] = False,
    scope_file: Annotated[
        Path | None,
        typer.Option("--scope-file", help="Scope file (default SCOPE.md)"),
    ] = None,
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
) -> None:
    """Verify changed files stay within the declared plan scope."""
    from mattstack.utils.console import print_error

    if not scope:
        print_error("Use --scope to enforce the plan scope")
        raise typer.Exit(code=1)

    from mattstack.commands.verify import run_verify

    run_verify(path=path or Path.cwd(), scope_file=scope_file)


if __name__ == "__main__":
    app()
