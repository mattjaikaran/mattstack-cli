"""Init command: interactive wizard + orchestration."""

from __future__ import annotations

from pathlib import Path

import questionary  # type: ignore
import typer
from rich.panel import Panel
from rich.table import Table

from mattstack.config import (
    BackendFramework,
    FrontendFramework,
    ProjectConfig,
    ProjectType,
    Variant,
)
from mattstack.gauntlet.init import CONFIG_FILENAME
from mattstack.gauntlet.init import write_config as write_gauntlet_config
from mattstack.generators.backend_only import BackendOnlyGenerator
from mattstack.generators.frontend_only import FrontendOnlyGenerator
from mattstack.generators.fullstack import FullstackGenerator
from mattstack.presets import get_all_presets, get_preset
from mattstack.templates.mattstack_yml import generate_mattstack_yml
from mattstack.utils.console import console, print_error, print_info, print_success
from mattstack.utils.git import get_git_user
from mattstack.utils.yaml_config import load_config_file

STYLE = questionary.Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "bold"),
        ("answer", "fg:cyan bold"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:cyan"),
    ]
)


def run_init(
    name: str | None = None,
    preset: str | None = None,
    config_file: str | None = None,
    ios: bool = False,
    output_dir: Path | None = None,
    dry_run: bool = False,
) -> None:
    """Main init entry point. Routes to interactive, preset, or config-file mode."""
    if output_dir is None:
        output_dir = Path.cwd()

    try:
        if config_file:
            _run_from_config(Path(config_file), output_dir, dry_run=dry_run)
        elif preset and name:
            _run_from_preset(name, preset, ios, output_dir, dry_run=dry_run)
        elif name and not preset:
            # Name given but no preset — still run interactive for options
            _run_interactive(output_dir, default_name=name, dry_run=dry_run)
        else:
            _run_interactive(output_dir, dry_run=dry_run)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise typer.Exit(code=130) from None


def _run_from_config(config_path: Path, output_dir: Path, *, dry_run: bool = False) -> None:
    """Generate from a YAML config file."""
    config = load_config_file(config_path, output_dir)
    if config is None:
        raise typer.Exit(code=1)
    config.dry_run = dry_run
    _generate(config)


def _run_from_preset(
    name: str,
    preset_name: str,
    ios: bool,
    output_dir: Path,
    *,
    dry_run: bool = False,
) -> None:
    """Generate from a named preset."""
    all_presets = get_all_presets()
    preset = all_presets.get(preset_name) or get_preset(preset_name)
    if preset is None:
        print_error(f"Unknown preset: {preset_name}")
        print_error("Run 'mattstack info' to see available presets")
        raise typer.Exit(code=1)

    default_author, default_email = get_git_user()

    config = preset.to_config(name, output_dir / name)
    if ios:
        config.include_ios = True
    config.dry_run = dry_run
    config.author_name = default_author or config.author_name
    config.author_email = default_email or config.author_email

    _show_summary(config)
    _generate(config)


def _run_interactive(
    output_dir: Path,
    default_name: str | None = None,
    *,
    dry_run: bool = False,
) -> None:
    """Run the interactive wizard."""
    _show_welcome()

    default_author, default_email = get_git_user()

    # 1. Project name
    if default_name:
        project_name = default_name
    else:
        project_name = questionary.text(
            "Project name:",
            style=STYLE,
        ).ask()
        if not project_name:
            raise KeyboardInterrupt

    from mattstack.config import normalize_name

    normalized = normalize_name(project_name)
    if normalized != project_name:
        console.print(f"  [dim]Normalized to: {normalized}[/dim]")

    # 2. Project type
    project_type_choice = questionary.select(
        "Project type:",
        choices=[
            questionary.Choice("Fullstack Monorepo (Backend + Frontend)", value="fullstack"),
            questionary.Choice("Backend Only (API)", value="backend-only"),
            questionary.Choice("Frontend Only", value="frontend-only"),
        ],
        style=STYLE,
    ).ask()
    if not project_type_choice:
        raise KeyboardInterrupt
    project_type = ProjectType(project_type_choice)

    # 3. Variant
    variant_choice = questionary.select(
        "Variant:",
        choices=[
            questionary.Choice("Starter (standard)", value="starter"),
            questionary.Choice("B2B (organizations, teams, roles)", value="b2b"),
        ],
        style=STYLE,
    ).ask()
    if not variant_choice:
        raise KeyboardInterrupt
    variant = Variant(variant_choice)

    # 4. Backend framework (if applicable)
    backend_framework = BackendFramework.DJANGO_NINJA
    if project_type in (ProjectType.FULLSTACK, ProjectType.BACKEND_ONLY):
        bf_choice = questionary.select(
            "Backend framework:",
            choices=[
                questionary.Choice("Django Ninja Extra (Python, default)", value="django-ninja"),
                questionary.Choice(
                    "django-matt (Python, MattAPI controllers + CRUDService)", value="django-matt"
                ),
                questionary.Choice(
                    "FastAPI (Python, async, SQLAlchemy + Alembic + Celery)",
                    value="fastapi",
                ),
                questionary.Choice(
                    "NestJS (Node.js/TypeScript, Fastify + Drizzle ORM + JWT/OAuth)",
                    value="nestjs",
                ),
            ],
            style=STYLE,
        ).ask()
        if not bf_choice:
            raise KeyboardInterrupt
        backend_framework = BackendFramework(bf_choice)

    # 5. Frontend framework (if applicable)
    frontend_framework = FrontendFramework.REACT_VITE
    if project_type in (ProjectType.FULLSTACK, ProjectType.FRONTEND_ONLY):
        fw_choice = questionary.select(
            "Frontend framework:",
            choices=[
                questionary.Choice("React Vite + TanStack Router", value="react-vite"),
                questionary.Choice(
                    "React Vite + React Router (simpler)", value="react-vite-starter"
                ),
                questionary.Choice(
                    "React Rsbuild + TanStack Router (Rust-powered)", value="react-rsbuild"
                ),
                questionary.Choice(
                    "React Rsbuild + Kibo UI (dashboards, kanban, calendars)",
                    value="react-rsbuild-kibo",
                ),
                questionary.Choice("Next.js (App Router, TypeScript, Tailwind)", value="nextjs"),
            ],
            style=STYLE,
        ).ask()
        if not fw_choice:
            raise KeyboardInterrupt
        frontend_framework = FrontendFramework(fw_choice)

    # 6. iOS (if fullstack)
    include_ios = False
    if project_type == ProjectType.FULLSTACK:
        include_ios = questionary.confirm(
            "Include iOS client?",
            default=False,
            style=STYLE,
        ).ask()
        if include_ios is None:
            raise KeyboardInterrupt

    # 7. Celery (Django only — NestJS uses Bull queues internally)
    use_celery = True
    if project_type in (ProjectType.FULLSTACK, ProjectType.BACKEND_ONLY):
        if backend_framework == BackendFramework.NESTJS:
            use_celery = False  # NestJS has Bull/Redis queues built-in
        else:
            use_celery = questionary.confirm(
                "Include Celery background tasks?",
                default=True,
                style=STYLE,
            ).ask()
            if use_celery is None:
                raise KeyboardInterrupt

    # Build config
    config = ProjectConfig(
        name=project_name,
        path=output_dir / project_name,
        project_type=project_type,
        variant=variant,
        frontend_framework=frontend_framework,
        backend_framework=backend_framework,
        include_ios=include_ios,
        use_celery=use_celery,
        use_redis=use_celery,  # Redis follows Celery
        author_name=default_author,
        author_email=default_email,
    )
    config.dry_run = dry_run

    # 7. Summary + confirm
    _show_summary(config)

    proceed = questionary.confirm(
        "Generate project?",
        default=True,
        style=STYLE,
    ).ask()
    if not proceed:
        console.print("[yellow]Cancelled.[/yellow]")
        return

    _generate(config)


def _show_welcome() -> None:
    console.print()
    console.print(
        Panel(
            "[bold cyan]mattstack[/bold cyan] — scaffold fullstack monorepos",
            border_style="cyan",
            expand=False,
        )
    )
    console.print()


def _show_summary(config: ProjectConfig) -> None:
    console.print()
    table = Table(title="Project Summary", show_header=False, border_style="cyan")
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    table.add_row("Name", config.name)
    table.add_row("Type", config.project_type.value)
    table.add_row("Variant", config.variant.value)
    if config.has_backend:
        table.add_row("Backend", config.backend_framework.value)
    if config.has_frontend:
        table.add_row("Frontend", config.frontend_framework.value)
    if config.has_backend:
        table.add_row("Celery", "yes" if config.use_celery else "no")
        table.add_row("Redis", "yes" if config.use_redis else "no")
    table.add_row("iOS", "yes" if config.include_ios else "no")
    table.add_row("Path", str(config.path))

    console.print(table)
    console.print()


def _generate(config: ProjectConfig) -> bool:
    """Run the appropriate generator."""
    if config.path.exists() and not config.dry_run:
        print_error(f"Directory already exists: {config.path}")
        raise typer.Exit(code=1)

    generator: FullstackGenerator | BackendOnlyGenerator | FrontendOnlyGenerator
    if config.project_type == ProjectType.FULLSTACK:
        generator = FullstackGenerator(config)
    elif config.project_type == ProjectType.BACKEND_ONLY:
        generator = BackendOnlyGenerator(config)
    elif config.project_type == ProjectType.FRONTEND_ONLY:
        generator = FrontendOnlyGenerator(config)
    else:
        print_error(f"Unknown project type: {config.project_type}")
        raise typer.Exit(code=1)
    success = generator.run()

    if success:
        generator.write_file("mattstack.yml", generate_mattstack_yml())
        _write_gauntlet_config(config)
        _print_next_steps(config)

    return success


def _write_gauntlet_config(config: ProjectConfig) -> None:
    """Write gauntlet.toml so the project has a verification gate."""
    if config.dry_run:
        print_info(f"[dry-run] Would create {CONFIG_FILENAME}")
        return
    written = write_gauntlet_config(
        config.path,
        has_python=config.has_backend,
        has_typescript=config.has_frontend,
        has_rust=False,
    )
    if written is not None:
        print_success(f"Wrote {written.name} (Gauntlet configuration)")


def _print_next_steps(config: ProjectConfig) -> None:
    console.print()
    print_success(f"Project '{config.name}' created successfully!")
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  [cyan]cd {config.name}[/cyan]")
    console.print("  [cyan]make setup[/cyan]")
    console.print("  [cyan]mattstack audit[/cyan]        # Run the Gauntlet gate")
    if config.has_backend:
        console.print("  [cyan]make up[/cyan]          # Start Docker services")
        if config.is_nestjs_backend:
            console.print("  [cyan]make backend-migrate[/cyan]  # Run Drizzle migrations")
        else:
            console.print("  [cyan]make backend-migrate[/cyan]")
            console.print("  [cyan]make backend-superuser[/cyan]")
    if config.is_fullstack:
        api_port = config.backend_api_port
        console.print(f"  [cyan]make backend-dev[/cyan]  # http://localhost:{api_port}")
        console.print("  [cyan]make frontend-dev[/cyan] # http://localhost:3000")
    elif config.has_backend:
        api_port = config.backend_api_port
        console.print(f"  [cyan]make backend-dev[/cyan]  # http://localhost:{api_port}")
    elif config.has_frontend:
        console.print("  [cyan]make frontend-dev[/cyan] # http://localhost:3000")
    console.print()
