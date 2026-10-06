"""Root project command definitions."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer


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
    mode: Annotated[
        str | None,
        typer.Option("--mode", help="Execution mode: host or container (default: project setting)"),
    ] = None,
) -> None:
    """Start development services and supervise host processes until you press Ctrl+C."""
    from mattstack.commands.dev import run_dev

    run_dev(path=path or Path.cwd(), services=services, no_docker=no_docker, mode=mode)


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


def env(
    action: Annotated[
        str,
        typer.Argument(help="Action: check, sync, show, secrets (create missing .env files)"),
    ] = "check",
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
) -> None:
    """Manage environment variables (.env files)."""
    from mattstack.commands.env import run_env

    run_env(action=action, path=path or Path.cwd())


def version() -> None:
    """Show mattstack version."""
    from mattstack.commands.version import run_version

    run_version()


def completions(
    install: Annotated[bool, typer.Option("--install", help="Install shell completions")] = False,
    show: Annotated[bool, typer.Option("--show", help="Show completion script")] = False,
) -> None:
    """Manage shell completions (bash/zsh/fish)."""
    from mattstack.commands.completions import run_completions

    run_completions(install=install, show=show)


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


def health(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
    live: Annotated[
        bool,
        typer.Option("--live", help="Probe HTTP endpoints (backend + frontend)"),
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit structured service health")
    ] = False,
) -> None:
    """Check health of all project services (Docker, DB, Redis, servers)."""
    from mattstack.commands.health import run_health

    run_health(path=path or Path.cwd(), live=live, json_output=json_output)


def workflow(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
    ci: Annotated[
        str | None,
        typer.Option(
            "--ci",
            help="Opt in to hosted CI: github or gitlab. Gates run locally by default"
            " (make gauntlet, pre-push hook); hosted runners cost build minutes.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview without writing files"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace an existing workflow file"),
    ] = False,
) -> None:
    """Generate an opt-in hosted CI workflow (GitHub Actions or GitLab CI)."""
    from mattstack.commands.workflow import run_generate_workflow

    run_generate_workflow(path=path or Path.cwd(), ci=ci, dry_run=dry_run, force=force)


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


def register_project_commands(application: typer.Typer) -> None:
    """Register root commands without importing the application."""
    application.command("dev")(dev)
    application.command("test")(test_cmd)
    application.command("lint")(lint)
    application.command("env")(env)
    application.command("version")(version)
    application.command("completions")(completions)
    application.command("create")(create)
    application.command("fmt")(fmt)
    application.command("health")(health)
    application.command("workflow")(workflow)
    application.command("protect")(protect)
    application.command("notify")(notify)
    application.command("verify")(verify)
