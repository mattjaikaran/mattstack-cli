"""Root scaffold command definitions."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer


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
    task_backend: Annotated[
        str | None,
        typer.Option(
            "--task-backend",
            help="Background tasks: celery, huey, django_q, django_rq, dramatiq (django-ninja),"
            " or none (no worker; enqueueing fails). Default: celery",
        ),
    ] = None,
    realtime: Annotated[
        bool | None,
        typer.Option(
            "--realtime/--no-realtime",
            help="Add the Centrifugo realtime profile (django-ninja only; default off)",
        ),
    ] = None,
    media_storage: Annotated[
        str | None,
        typer.Option(
            "--media-storage",
            help="Production media storage: local or s3 (django-ninja only; default local)",
        ),
    ] = None,
    ai: Annotated[
        str | None,
        typer.Option(
            "--ai",
            help="AI layer vector store: none, pgvector, or qdrant (django-ninja only;"
            " any choice uses the pgvector image and the backend's ai extra)",
        ),
    ] = None,
    graph: Annotated[
        str | None,
        typer.Option(
            "--graph",
            help="AI layer graph: cte (recursive SQL, default) or neo4j (graph profile)",
        ),
    ] = None,
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
        task_backend=task_backend,
        realtime=realtime,
        media_storage=media_storage,
        ai=ai,
        graph=graph,
    )


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
            help="Framework for the new component. Frontend: react-vite, react-vite-starter,"
            " react-rsbuild, react-rsbuild-kibo, nextjs; backend: django-ninja, django-matt,"
            " fastapi, nestjs",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview what would be added without making changes"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace existing root files with generated versions"),
    ] = False,
) -> None:
    """Add a component (frontend, backend, ios) to an existing project."""
    from mattstack.commands.add import run_add

    run_add(
        component=component,
        project_path=path or Path.cwd(),
        framework=framework,
        dry_run=dry_run,
        force=force,
    )


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
        typer.Option(
            "--force", help="Apply new, updated, and cleanly merged files; otherwise only preview"
        ),
    ] = False,
) -> None:
    """Preview or apply boilerplate changes since the commit recorded in mattstack.yml."""
    from mattstack.commands.upgrade import run_upgrade

    run_upgrade(
        path=path or Path.cwd(),
        component=component,
        dry_run=dry_run,
        force=force,
    )


def doctor(
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit structured diagnostics")
    ] = False,
) -> None:
    """Check your development environment."""
    from mattstack.commands.doctor import run_doctor

    run_doctor(path=path, json_output=json_output)


def info() -> None:
    """Show available presets, repos, and usage."""
    from mattstack.commands.info import run_info

    run_info()


def presets() -> None:
    """List available presets, repos, and usage examples."""
    from mattstack.commands.info import run_info

    run_info()


def audit(
    path: Annotated[
        Path | None,
        typer.Argument(help="Project path to audit (default: current directory)"),
    ] = None,
    audit_type: Annotated[
        list[str] | None,
        typer.Option("--type", "-t", help="Audit types: repeat or comma-separate values"),
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
    versions: Annotated[
        bool,
        typer.Option("--versions", help="Report tool/service versions; exit 1 on drift"),
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
        versions=versions,
    )


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
            import yaml as _yaml

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


def register_scaffold_commands(application: typer.Typer) -> None:
    """Register root commands without importing the application."""
    application.command("init")(init)
    application.command("add")(add)
    application.command("upgrade")(upgrade)
    application.command("doctor")(doctor)
    application.command("info")(info)
    application.command("presets")(presets)
    application.command("audit")(audit)
    application.command("config")(config_cmd)
