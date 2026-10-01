"""Generate TypeScript from a local OpenAPI contract with a project-owned tool."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess  # nosec B404 # Required CLI subprocess support.
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape

from mattstack.config import BackendFramework
from mattstack.project import ResolvedProject, resolve_project
from mattstack.utils.console import err_console, print_error, print_info, print_success

MANIFEST = ".mattstack-openapi.json"
# Schema path for backends without a documented export location.
ROOT_SCHEMA = Path("openapi.json")
# Django Ninja's `manage.py export_openapi` writes here, relative to the backend.
NINJA_SCHEMA = Path("docs/openapi/openapi.json")
# Version used by the generated-client proof recorded in docs/ecosystem.md.
HEY_API_PACKAGE = "@hey-api/openapi-ts@0.99.0"


def _error(message: str) -> None:
    """Print an error without wrapping, so printed commands run when copied."""
    err_console.print(f"[red]\\[ERROR][/red] {escape(message)}", soft_wrap=True)


def ninja_export_command(project: ResolvedProject) -> str:
    """Return the shell command that writes the Ninja schema to ``NINJA_SCHEMA``.

    It loads the root .env the same way the generated Makefile does, because
    consolidation removes ``backend/.env`` and the settings read the environment.
    """
    steps = [f"cd {shlex.quote(str(project.root))}"]
    if (project.root / ".env").is_file():
        steps.append("set -a && . ./.env && set +a")
    backend = os.path.relpath(project.backend_dir, project.root)
    if backend != ".":
        steps.append(f"cd {shlex.quote(backend)}")
    steps.append("uv run python manage.py export_openapi")
    return " && ".join(steps)


def resolve_schema(project: ResolvedProject, schema: Path | None) -> Path:
    """Return the OpenAPI file to read; an explicit ``--schema`` always wins."""
    if schema is not None:
        source = schema if schema.is_absolute() else project.root / schema
        if not source.is_file():
            raise ValueError(
                f"OpenAPI schema not found at {source} (from --schema). "
                "Pass an existing OpenAPI JSON file: --schema <path>"
            )
        return source
    if project.backend_framework == BackendFramework.DJANGO_NINJA:
        source = project.backend_dir / NINJA_SCHEMA
        if source.is_file():
            return source
        rerun = f"mattstack sync openapi --path {shlex.quote(str(project.root))}"
        hint = ""
        if (project.root / ROOT_SCHEMA).is_file():
            hint = f"\nOr use the existing root file: {rerun} --schema {ROOT_SCHEMA}"
        raise ValueError(
            f"No exported Django Ninja schema at {source}. Export it with:\n"
            f"  {ninja_export_command(project)}\n"
            f"Then rerun: {rerun}{hint}"
        )
    source = project.root / ROOT_SCHEMA
    if not source.is_file():
        raise ValueError(
            f"No OpenAPI schema at {source}. Save the backend's OpenAPI JSON document "
            "there, or pass its location: --schema <path>"
        )
    return source


def _check_contract(source: Path) -> None:
    try:
        contract = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} is not valid JSON ({exc}); export the schema again") from exc
    if not isinstance(contract, dict) or not isinstance(contract.get("openapi"), str):
        raise ValueError(f"{source} has no openapi version field; use an OpenAPI JSON document")
    if not isinstance(contract.get("paths"), dict):
        raise ValueError(f"{source} has no paths object; use an OpenAPI JSON document")


def _files(directory: Path) -> dict[str, str]:
    if not directory.is_dir():
        return {}
    return {
        str(file.relative_to(directory)): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted(directory.rglob("*"))
        if file.is_file() and file.name != MANIFEST
    }


def _read_manifest(directory: Path) -> dict[str, str] | None:
    try:
        data = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in data.items()
    ):
        return None
    return data


def sync_openapi(
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project root")] = None,
    schema: Annotated[
        Path | None,
        typer.Option(
            "--schema",
            help="OpenAPI JSON file, relative to the project. Default: the Django Ninja "
            "export (backend/docs/openapi/openapi.json), else openapi.json",
        ),
    ] = None,
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Output directory, relative to the frontend")
    ] = Path("src/api/generated"),
    check: Annotated[
        bool, typer.Option("--check", help="Fail on generated-client drift without changing files")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Replace edited or unmanaged generated output")
    ] = False,
) -> None:
    """Generate a client with the installed @hey-api/openapi-ts package; never download a tool."""
    try:
        project = resolve_project(path or Path.cwd())
        source = resolve_schema(project, schema)
        _check_contract(source)
        print_info(f"Using OpenAPI schema {source}")
        candidate = project.frontend_dir / output
        frontend = project.frontend_dir.resolve()
        target = candidate.resolve()
        if not target.is_relative_to(frontend) or target == frontend:
            raise ValueError("Keep generated output in a dedicated directory inside the frontend")
        if any(item.is_symlink() for item in (candidate, *candidate.parents) if item != frontend):
            raise ValueError("Do not use symbolic links in the generated output path")
        if target.exists() and not target.is_dir():
            raise ValueError("The generated output path must be a directory")
        current = _files(target)
        if not check and current and not force and _read_manifest(target) != current:
            raise ValueError("Output contains unmanaged or edited files; review it and use --force")
        binary = frontend / "node_modules" / ".bin" / "openapi-ts"
        if not binary.is_file():
            raise ValueError(
                f"@hey-api/openapi-ts is not installed in {frontend}. Install the pinned "
                f"local tool: mattstack client add {HEY_API_PACKAGE} --dev --exact "
                f"--path {shlex.quote(str(project.root))}"
            )
        with tempfile.TemporaryDirectory(prefix="mattstack-openapi-") as temporary:
            generated = Path(temporary) / "client"
            result = subprocess.run(  # nosec B603 # Argv; trust project tools and PATH.
                [str(binary), "-i", str(source.resolve()), "-o", str(generated)],
                cwd=frontend,
                env=project.env,
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                print_error(
                    result.stderr.strip() or result.stdout.strip() or "Client generation failed"
                )
                raise typer.Exit(code=result.returncode)
            expected = _files(generated)
            if not expected:
                raise ValueError("The generator produced no client files")
            if check:
                if expected != current:
                    _error(
                        "OpenAPI client differs from the backend contract. Regenerate it: "
                        f"mattstack sync openapi --path {shlex.quote(str(project.root))} "
                        f"--schema {shlex.quote(str(source))} --output {shlex.quote(str(output))}"
                    )
                    raise typer.Exit(code=1)
                print_success("OpenAPI client matches the backend contract")
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            staged = Path(tempfile.mkdtemp(prefix=".mattstack-openapi-", dir=target.parent))
            try:
                shutil.copytree(generated, staged, dirs_exist_ok=True)
                (staged / MANIFEST).write_text(
                    json.dumps(expected, indent=2) + "\n", encoding="utf-8"
                )
                if target.exists():
                    backup = staged.with_name(staged.name + "-previous")
                    target.rename(backup)
                    try:
                        staged.rename(target)
                    except OSError:
                        backup.rename(target)
                        raise
                    shutil.rmtree(backup)
                else:
                    staged.rename(target)
            finally:
                if staged.exists():
                    shutil.rmtree(staged)
        print_success(f"Generated OpenAPI client in {target}")
        print_info("Run the frontend type check and API integration tests before committing")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        _error(str(exc))
        raise typer.Exit(code=1) from exc
