"""Generate the frontend API client from the backend OpenAPI contract.

`@hey-api/openapi-ts` is the only generator. The frontend pins it to an exact
version; mattstack runs that local binary with a fixed plugin list and never
downloads a tool.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import subprocess  # nosec B404 # Required CLI subprocess support.
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.markup import escape

from mattstack.parsers.frontend_layout import package_dependencies
from mattstack.parsers.openapi_spec import (
    EXACT_VERSION,
    GENERATED_DIR,
    HEY_API_NAME,
    HEY_API_PACKAGE,
    load_contract,
    resolve_schema,
)
from mattstack.project import ResolvedProject, resolve_project
from mattstack.utils.console import err_console, print_error, print_info, print_success

MANIFEST = ".mattstack-openapi.json"
# Types, SDK, Zod schemas, and TanStack Query hooks; all ship inside the generator.
PLUGINS = ("@hey-api/typescript", "@hey-api/sdk", "zod", "@tanstack/react-query")
MAX_LISTED = 10

PathOption = Annotated[Path | None, typer.Option("--path", "-p", help="Project root")]
SchemaOption = Annotated[
    Path | None,
    typer.Option(
        "--schema",
        help="OpenAPI JSON file, relative to the project. Default: the Django Ninja "
        "export (backend/docs/openapi/openapi.json), else openapi.json",
    ),
]
OutputOption = Annotated[
    Path, typer.Option("--output", "-o", help="Output directory, relative to the frontend")
]


@dataclass(frozen=True)
class _Job:
    project: ResolvedProject
    source: Path
    frontend: Path
    target: Path
    output: Path


def _error(message: str) -> None:
    """Print an error without wrapping, so printed commands run when copied."""
    err_console.print(f"[red]\\[ERROR][/red] {escape(message)}", soft_wrap=True)


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


def _job(path: Path | None, schema: Path | None, output: Path) -> _Job:
    project = resolve_project(path or Path.cwd())
    source = resolve_schema(project, schema)
    load_contract(source)
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
    return _Job(project, source, frontend, target, output)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _declared_version(frontend: Path) -> str | None:
    package = _read_object(frontend / "package.json")
    for section in ("devDependencies", "dependencies"):
        entries = package.get(section)
        value = entries.get(HEY_API_NAME) if isinstance(entries, dict) else None
        if isinstance(value, str):
            return value
    return None


def _tool(job: _Job) -> Path:
    """Return the frontend's own generator binary after checking its exact pin."""
    manifest = job.frontend / "package.json"
    install = (
        f"mattstack client add {HEY_API_PACKAGE} --dev --exact "
        f"--path {shlex.quote(str(job.project.root))}"
    )
    declared = _declared_version(job.frontend)
    if declared is None:
        raise ValueError(f"{HEY_API_NAME} is not in {manifest}. Install the pinned tool: {install}")
    if not EXACT_VERSION.fullmatch(declared):
        raise ValueError(
            f"Pin {HEY_API_NAME} to an exact version in {manifest} (found {declared!r}): {install}"
        )
    binary = job.frontend / "node_modules" / ".bin" / "openapi-ts"
    installed = _read_object(job.frontend / "node_modules" / HEY_API_NAME / "package.json").get(
        "version"
    )
    if not binary.is_file() or installed != declared:
        found = f"found {installed}" if installed else "not installed"
        raise ValueError(
            f"{HEY_API_NAME} {declared} is pinned but {found} in {job.frontend}. "
            "Run `bun install` in the frontend"
        )
    return binary


def _generate(job: _Job, binary: Path, destination: Path) -> dict[str, str]:
    client = (
        "@hey-api/client-axios"
        if "axios" in package_dependencies(job.frontend)
        else "@hey-api/client-fetch"
    )
    argv = [str(binary), "-i", str(job.source.resolve()), "-o", str(destination)]
    argv += ["-c", client, "--no-log-file", "-p", *PLUGINS]
    result = subprocess.run(  # nosec B603 # Argv; trust project tools and PATH.
        argv,
        cwd=job.frontend,
        env=job.project.env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        print_error(result.stderr.strip() or result.stdout.strip() or "Client generation failed")
        raise typer.Exit(code=result.returncode)
    generated = _files(destination)
    if not generated:
        raise ValueError("The generator produced no client files")
    return generated


def _replace(target: Path, generated: Path, files: dict[str, str]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".mattstack-openapi-", dir=target.parent))
    try:
        shutil.copytree(generated, staged, dirs_exist_ok=True)
        (staged / MANIFEST).write_text(json.dumps(files, indent=2) + "\n", encoding="utf-8")
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


def sync_openapi(
    path: PathOption = None,
    schema: SchemaOption = None,
    output: OutputOption = GENERATED_DIR,
    force: Annotated[
        bool, typer.Option("--force", help="Replace edited or unmanaged generated output")
    ] = False,
) -> None:
    """Generate types, SDK, Zod schemas, and TanStack Query hooks from the OpenAPI contract."""
    try:
        job = _job(path, schema, output)
        current = _files(job.target)
        if current and not force and _read_manifest(job.target) != current:
            raise ValueError("Output contains unmanaged or edited files; review it and use --force")
        binary = _tool(job)
        with tempfile.TemporaryDirectory(prefix="mattstack-openapi-") as temporary:
            generated = Path(temporary) / "client"
            _replace(job.target, generated, _generate(job, binary, generated))
        print_success(f"Generated OpenAPI client in {job.target}")
        print_info("Run `mattstack sync check` and the frontend type check before committing")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        _error(str(exc))
        raise typer.Exit(code=1) from exc


def sync_check(
    path: PathOption = None, schema: SchemaOption = None, output: OutputOption = GENERATED_DIR
) -> None:
    """Regenerate into a temporary directory; exit 1 when committed output differs."""
    try:
        job = _job(path, schema, output)
        binary = _tool(job)
        with tempfile.TemporaryDirectory(prefix="mattstack-openapi-") as temporary:
            expected = _generate(job, binary, Path(temporary) / "client")
        current = _files(job.target)
        names = expected.keys() | current.keys()
        drift = sorted(name for name in names if expected.get(name) != current.get(name))
        if drift:
            for name in drift[:MAX_LISTED]:
                state = "stale" if name in current and name in expected else "missing"
                if name not in expected:
                    state = "extra"
                err_console.print(f"  {state}: {escape(str(job.output / name))}", soft_wrap=True)
            if len(drift) > MAX_LISTED:
                err_console.print(f"  ... and {len(drift) - MAX_LISTED} more")
            schema_arg = f" --schema {shlex.quote(str(schema))}" if schema else ""
            _error(
                f"{len(drift)} generated file(s) differ from the OpenAPI contract. Regenerate: "
                f"mattstack sync openapi --path {shlex.quote(str(job.project.root))}{schema_arg}"
                f" --output {shlex.quote(str(output))}"
            )
            raise typer.Exit(code=1)
        print_success(f"Generated client matches {job.source}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        _error(str(exc))
        raise typer.Exit(code=1) from exc
