"""`generate engine`: run the django-ninja boilerplate's engine generator, then sync the client."""

from __future__ import annotations

import subprocess  # nosec B404 # Required CLI subprocess support.
from pathlib import Path
from typing import Annotated

import typer

from mattstack.commands.openapi import sync_openapi
from mattstack.config import BackendFramework
from mattstack.project import ResolvedProject, resolve_project
from mattstack.utils.console import print_error, print_info

PathOption = Annotated[Path | None, typer.Option("--path", "-p", help="Project root path")]
ModulesOption = Annotated[
    str | None,
    typer.Option(
        "--modules",
        "-m",
        help="Comma-separated module apps, such as artists,tours "
        "(default: one module named after the engine)",
    ),
]


def _resolve(path: Path | None) -> ResolvedProject:
    """Resolve the project and require a Django Ninja backend with manage.py."""
    try:
        project = resolve_project(path or Path.cwd())
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None
    if project.backend_framework is not BackendFramework.DJANGO_NINJA:
        print_error(
            f"generate engine needs a Django Ninja backend; found {project.backend_framework}"
        )
        raise typer.Exit(code=1)
    if not (project.backend_dir / "manage.py").is_file():
        print_error(f"No manage.py found in {project.backend_dir} (project root: {project.root})")
        raise typer.Exit(code=1)
    return project


def _manage(project: ResolvedProject, args: list[str]) -> None:
    """Run a Django management command in backend/ with the project environment."""
    cmd = ["uv", "run", "python", "manage.py", *args]
    print_info(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(  # nosec B603 # Argv; trust project tools and PATH.
            cmd,
            cwd=project.backend_dir,
            env=project.env,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print_error("uv not found on PATH")
        raise typer.Exit(code=127) from None
    if result.returncode != 0:
        print_error(f"manage.py {args[0]} failed (exit code {result.returncode})")
        raise typer.Exit(code=1)


def engine(
    name: Annotated[str, typer.Argument(help="Engine name, a Python identifier such as booking")],
    modules: ModulesOption = None,
    path: PathOption = None,
) -> None:
    """Generate an engine of module apps in backend/, then sync the frontend client.

    The client is regenerated from a fresh OpenAPI export, so the new module tags
    reach the frontend. Without a frontend, only the backend is generated.
    """
    project = _resolve(path)
    args = ["generate_feature", "engine", "--app-name", name]
    if modules:
        args += ["--modules", modules]
    _manage(project, args)
    if project.config.has_frontend:
        _manage(project, ["export_openapi"])
        sync_openapi(path=project.root)
    else:
        print_info("No frontend in this project; skipping sync openapi")
