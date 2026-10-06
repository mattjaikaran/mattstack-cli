"""Locate and read the backend's OpenAPI contract, the source of frontend types.

The backend exports the contract; ``@hey-api/openapi-ts`` turns it into
TypeScript types, an SDK, Zod schemas, and TanStack Query hooks.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path
from typing import Any

from mattstack.config import BackendFramework
from mattstack.project import ResolvedProject, resolve_project

# Schema path for backends without a documented export location.
ROOT_SCHEMA = Path("openapi.json")
# Django Ninja's `manage.py export_openapi` writes here, relative to the backend.
NINJA_SCHEMA = Path("docs/openapi/openapi.json")
# Generated client directory, relative to the frontend.
GENERATED_DIR = Path("src/api/generated")
ZOD_FILE = "zod.gen.ts"
# Generator version verified against the parity audit; plugins ship inside it.
HEY_API_NAME = "@hey-api/openapi-ts"
HEY_API_VERSION = "0.99.0"
HEY_API_PACKAGE = f"{HEY_API_NAME}@{HEY_API_VERSION}"
# An exact npm version, so regenerating the client is reproducible.
EXACT_VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")


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


def load_contract(source: Path) -> dict[str, Any]:
    """Read and minimally validate an OpenAPI JSON document."""
    try:
        contract = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} is not valid JSON ({exc}); export the schema again") from exc
    if not isinstance(contract, dict) or not isinstance(contract.get("openapi"), str):
        raise ValueError(f"{source} has no openapi version field; use an OpenAPI JSON document")
    if not isinstance(contract.get("paths"), dict):
        raise ValueError(f"{source} has no paths object; use an OpenAPI JSON document")
    return contract


def component_schemas(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return ``components.schemas`` entries that are JSON objects."""
    components = contract.get("components")
    schemas = components.get("schemas") if isinstance(components, dict) else None
    if not isinstance(schemas, dict):
        return {}
    return {name: node for name, node in schemas.items() if isinstance(node, dict)}


def find_contract(project_path: Path) -> tuple[ResolvedProject, Path] | None:
    """Return the project and its discovered OpenAPI file, or None when there is none."""
    try:
        project = resolve_project(project_path)
        return project, resolve_schema(project, None)
    except ValueError:
        return None
