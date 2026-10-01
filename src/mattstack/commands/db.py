"""Database management commands for mattstack projects."""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 # Required CLI subprocess support.
import sys
import time
from pathlib import Path
from typing import Annotated

import typer

from mattstack.commands.db_target import inspect_target
from mattstack.config import BackendFramework
from mattstack.project import EnvFileError, ResolvedProject, compose_services, resolve_project
from mattstack.utils.console import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
)

db_app = typer.Typer(
    name="db",
    help="Database management commands (Django).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

PathOption = Annotated[
    Path | None,
    typer.Option("--path", "-p", help="Project root path (default: current project)"),
]
YesOption = Annotated[
    bool,
    typer.Option("--yes", "-y", help="Confirm deleting all data without a prompt"),
]
ForceOption = Annotated[
    bool,
    typer.Option(
        "--force",
        help="Allow deleting data on a non-local, production, or unverified database",
    ),
]

_DJANGO_FRAMEWORKS = (None, BackendFramework.DJANGO_NINJA, BackendFramework.DJANGO_MATT)


def _resolve(path: Path | None) -> ResolvedProject:
    """Resolve the project and validate that it has a Django backend."""
    try:
        project = resolve_project(path or Path.cwd())
    except EnvFileError as e:
        print_error(str(e))
        raise typer.Exit(code=1) from None
    backend = project.backend_dir
    if project.backend_framework not in _DJANGO_FRAMEWORKS:
        print_error(f"db commands need a Django backend; found {project.backend_framework}")
        raise typer.Exit(code=1)
    if not (backend / "manage.py").is_file():
        print_error(f"No manage.py found in {backend} (project root: {project.root})")
        raise typer.Exit(code=1)
    return project


def _exit_code(returncode: int) -> int:
    """Map a child status to a shell exit code (signals become 128 + N)."""
    return returncode if returncode >= 0 else 128 - returncode


def _run(
    project: ResolvedProject,
    cmd: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run ``cmd`` with the project environment (root .env + shell env)."""
    print_info(f"Running: {' '.join(cmd)}")
    start = time.monotonic()
    try:
        result = subprocess.run(  # nosec B603 # Argv; trust project tools and PATH.
            cmd,
            cwd=cwd or project.backend_dir,
            env=project.env,
            text=True,
            capture_output=capture,
        )
    except FileNotFoundError:
        print_error(f"{cmd[0]} not found on PATH")
        raise typer.Exit(code=127) from None
    elapsed = time.monotonic() - start
    console.print(f"[dim]Completed in {elapsed:.1f}s (exit code {result.returncode})[/dim]")
    return result


def _run_manage(
    project: ResolvedProject,
    args: list[str],
    *,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a Django management command via uv."""
    return _run(project, ["uv", "run", "python", "manage.py", *args], capture=capture)


def _fail(message: str, result: subprocess.CompletedProcess[str]) -> typer.Exit:
    print_error(message)
    if result.stderr:
        sys.stderr.write(result.stderr if result.stderr.endswith("\n") else result.stderr + "\n")
    return typer.Exit(code=_exit_code(result.returncode) or 1)


def _authorize_destructive(
    project: ResolvedProject, action: str, *, yes: bool, force: bool
) -> None:
    """Exit unless deleting all data in the target database is authorized.

    Local development targets need ``--yes`` or an interactive confirmation.
    Non-local, production, or unverifiable targets also need ``--force``.
    """
    target = inspect_target(project)
    if target is None:
        print_error(
            f"Cannot read the database target from Django settings in {project.backend_dir}"
        )
        if not force:
            print_info("Fix the settings, or pass --force to run against an unverified target")
            raise typer.Exit(code=1)
        label = "an unverified database"
    else:
        label = target.label
        print_warning(
            f"{action} deletes all data in {label} "
            f"(settings: {target.settings or 'unknown'}, DEBUG={target.debug})"
        )
        reasons = [
            reason
            for reason, flagged in (
                ("a non-local host", not target.is_local),
                ("production settings", target.is_production),
            )
            if flagged
        ]
        if reasons and not force:
            print_error(f"Refusing to {action}: target has {' and '.join(reasons)}")
            print_info("Pass --force to delete data on this database anyway")
            raise typer.Exit(code=1)

    if yes:
        return
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print_error(f"Refusing to {action} without confirmation: no TTY. Re-run with --yes")
        raise typer.Exit(code=1)

    import questionary

    if not questionary.confirm(f"Delete all data in {label}?", default=False).ask():
        print_info("Aborted")
        raise typer.Exit(code=1)


def _flush_and_migrate(project: ResolvedProject) -> None:
    print_warning("Flushing database...")
    flush_result = _run_manage(project, ["flush", "--no-input"])
    if flush_result.returncode != 0:
        raise _fail("Database flush failed", flush_result)
    print_info("Running migrations...")
    migrate_result = _run_manage(project, ["migrate"])
    if migrate_result.returncode != 0:
        raise _fail("Migration after flush failed", migrate_result)


def _resolve_seed_file(backend: Path, file_override: str | None) -> Path | None:
    """Find the seed file to execute."""
    if file_override:
        candidate = backend / file_override
        return candidate if candidate.is_file() else None

    seed_py = backend / "seed.py"
    if seed_py.is_file():
        return seed_py

    seeds_dir = backend / "seeds"
    if seeds_dir.is_dir():
        for name in ["__main__.py", "run.py", "seed.py"]:
            candidate = seeds_dir / name
            if candidate.is_file():
                return candidate

    return None


def _require_seed_file(project: ResolvedProject, file_override: str | None) -> Path:
    seed_file = _resolve_seed_file(project.backend_dir, file_override)
    if seed_file is None:
        if file_override:
            print_error(f"Seed file not found: {project.backend_dir / file_override}")
        else:
            print_error("No seed file found")
            print_info("Expected: backend/seed.py or backend/seeds/ directory")
        raise typer.Exit(code=1)
    return seed_file


def _run_seed(project: ResolvedProject, seed_file: Path) -> None:
    try:
        shown = str(seed_file.relative_to(project.backend_dir))
    except ValueError:
        shown = str(seed_file)
    print_info(f"Running seed file: {shown}")
    result = _run(project, ["uv", "run", "python", shown])
    if result.returncode != 0:
        raise _fail("Seed failed", result)
    print_success("Database seeded")


@db_app.command()
def migrate(path: PathOption = None) -> None:
    """Run Django migrations."""
    project = _resolve(path)
    result = _run_manage(project, ["migrate"])
    if result.returncode != 0:
        raise _fail("Migration failed", result)
    print_success("Migrations applied")


@db_app.command()
def makemigrations(
    app_label: Annotated[
        str | None,
        typer.Option("--app", "-a", help="Target specific Django app"),
    ] = None,
    path: PathOption = None,
) -> None:
    """Create new Django migrations."""
    project = _resolve(path)
    args = ["makemigrations"]
    if app_label:
        args.append(app_label)
    result = _run_manage(project, args)
    if result.returncode != 0:
        raise _fail("makemigrations failed", result)
    print_success("Migrations created")


@db_app.command()
def status(path: PathOption = None) -> None:
    """Show migration status."""
    project = _resolve(path)
    result = _run_manage(project, ["showmigrations"])
    if result.returncode != 0:
        raise _fail("Failed to show migrations", result)


@db_app.command()
def seed(
    fresh: Annotated[
        bool,
        typer.Option("--fresh", help="Delete all data and re-migrate before seeding"),
    ] = False,
    file: Annotated[
        str | None,
        typer.Option("--file", "-f", help="Path to seed file (relative to backend/)"),
    ] = None,
    yes: YesOption = False,
    force: ForceOption = False,
    path: PathOption = None,
) -> None:
    """Seed database with sample data."""
    project = _resolve(path)
    seed_file = _require_seed_file(project, file)
    if fresh:
        _authorize_destructive(project, "seed --fresh", yes=yes, force=force)
        _flush_and_migrate(project)
    _run_seed(project, seed_file)


@db_app.command()
def reset(
    seed_after: Annotated[
        bool,
        typer.Option("--seed", help="Seed database after reset"),
    ] = False,
    yes: YesOption = False,
    force: ForceOption = False,
    path: PathOption = None,
) -> None:
    """Reset a local dev database: delete all data and re-migrate."""
    project = _resolve(path)
    seed_file = _require_seed_file(project, None) if seed_after else None
    _authorize_destructive(project, "reset", yes=yes, force=force)
    _flush_and_migrate(project)
    print_success("Database reset complete")
    if seed_file is not None:
        _run_seed(project, seed_file)


def _docker_psql_command(project: ResolvedProject) -> list[str] | None:
    """Return a psql command for the compose db service, when it serves this project."""
    if "db" not in compose_services(project.root) or shutil.which("docker") is None:
        return None
    target = inspect_target(project)
    if target is None or "postgresql" not in target.engine or not target.is_local:
        return None
    return [
        "docker",
        "compose",
        "exec",
        "db",
        "sh",
        "-c",
        'exec psql -U "${POSTGRES_USER:-postgres}" -d "$1"',
        "sh",
        target.name,
    ]


@db_app.command()
def shell(path: PathOption = None) -> None:
    """Open a database shell (uses the compose db container when psql is missing)."""
    project = _resolve(path)
    if shutil.which("psql") is None:
        docker_cmd = _docker_psql_command(project)
        if docker_cmd is not None:
            print_info("psql is not on PATH; opening psql in the compose db service")
            result = _run(project, docker_cmd, cwd=project.root)
            raise typer.Exit(code=_exit_code(result.returncode))
    result = _run_manage(project, ["dbshell"])
    raise typer.Exit(code=_exit_code(result.returncode))


@db_app.command()
def dump(
    app_label: Annotated[
        str | None,
        typer.Option("--app", "-a", help="Dump specific Django app"),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Output file path"),
    ] = None,
    path: PathOption = None,
) -> None:
    """Dump database fixtures as JSON."""
    project = _resolve(path)
    args = ["dumpdata", "--indent", "2"]
    if app_label:
        args.append(app_label)
    if output:
        args.extend(["--output", output])

    result = _run_manage(project, args, capture=bool(output))
    if result.returncode != 0:
        raise _fail("dumpdata failed", result)
    print_success(f"Fixtures dumped to {output}" if output else "Fixtures dumped")


@db_app.command()
def load(
    fixture: Annotated[
        str,
        typer.Argument(help="Fixture file to load"),
    ],
    path: PathOption = None,
) -> None:
    """Load fixtures into the database."""
    project = _resolve(path)
    result = _run_manage(project, ["loaddata", fixture])
    if result.returncode != 0:
        raise _fail(f"Failed to load fixture: {fixture}", result)
    print_success(f"Fixture loaded: {fixture}")
