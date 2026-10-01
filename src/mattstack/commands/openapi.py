"""Generate TypeScript from a local OpenAPI contract with a project-owned tool."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from mattstack.project import resolve_project
from mattstack.utils.console import print_error, print_info, print_success

MANIFEST = ".mattstack-openapi.json"


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
        Path, typer.Option("--schema", help="Local OpenAPI JSON file, relative to the project")
    ] = Path("openapi.json"),
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
        source = schema if schema.is_absolute() else project.root / schema
        contract = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(contract, dict) or not isinstance(contract.get("openapi"), str):
            raise ValueError("Use an OpenAPI JSON document with an openapi version field")
        if not isinstance(contract.get("paths"), dict):
            raise ValueError("The OpenAPI document must contain a paths object")
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
                "Install a pinned @hey-api/openapi-ts dev dependency in the frontend first"
            )
        with tempfile.TemporaryDirectory(prefix="mattstack-openapi-") as temporary:
            generated = Path(temporary) / "client"
            result = subprocess.run(
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
                    print_error(
                        "OpenAPI client differs from the backend contract; run sync openapi"
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
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
