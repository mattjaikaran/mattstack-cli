"""Root justfile template for generated projects.

The monorepo owns every command. A cloned boilerplate's own ``justfile``
targets its standalone Compose stack (the ``django`` service and a ``dev``
profile), which does not exist in the monorepo, so consolidation drops it and
this module generates one root file against the ``api-dev`` service.

The file targets ``just`` 1.21 (Ubuntu 24.04), so it avoids newer attributes
such as ``[working-directory]`` and uses ``cd`` in the recipe instead.
"""

from __future__ import annotations

from mattstack.config import ProjectConfig
from mattstack.runtime_profiles import REALTIME_PROFILE, task_profile
from mattstack.templates.component_guidance import frontend_gate_script
from mattstack.templates.frontend_commands import frontend_commands
from mattstack.templates.root_justfile_backend import (
    backend_install,
    backend_lint,
    backend_recipes,
    backend_test,
    container_recipes,
    quality_run,
)
from mattstack.templates.root_justfile_frontend import frontend_recipe, frontend_recipes

_PROD = "docker compose -f docker-compose.prod.yml --env-file .env.production"


def generate_justfile(config: ProjectConfig) -> str:
    """Generate root justfile content."""
    sections = [_header(config), _setup(config)]
    if config.has_backend:
        sections += [
            _docker_recipes(config),
            backend_recipes(config),
            container_recipes(config),
        ]
    if config.has_frontend:
        sections.append(frontend_recipes(config))
    if config.include_ios:
        sections.append(_ios_recipes(config))
    sections.append(_combined_recipes(config))
    sections.append(_ci_recipe(config))
    sections.append(_gauntlet_recipe(config))
    sections.append(_clean_recipes(config))
    if config.has_backend:
        sections.append(_prod_recipes())
    return "\n\n".join(section.strip("\n") for section in sections if section) + "\n"


def _header(config: ProjectConfig) -> str:
    return f"""\
# {config.display_name} developer tasks. Run `just` with no arguments to list recipes.
#
# `set dotenv-load` exports the root .env to every recipe; a missing .env is
# not an error. Host commands therefore see the same settings as the containers.

set shell := ["bash", "-cu"]
set dotenv-load

# Set CONFIRM=1 (env var or `just CONFIRM=1 clean-volumes`) to allow deletes.
CONFIRM := env("CONFIRM", "")

# List every recipe
default:
    @just --list

# Show this help
help:
    @just --list"""


def _setup(config: ProjectConfig) -> str:
    lines = ["", "# Install all dependencies and refresh lockfiles", "setup:"]
    if config.has_backend:
        lines += [
            "    @echo 'Setting up backend...'",
            f"    cd backend && {backend_install(config)}",
        ]
    if config.has_frontend:
        format_run = "" if config.is_nextjs else " && bun run format"
        lines += [
            "    @echo 'Setting up frontend...'",
            f"    cd frontend && bun install{format_run}",
        ]
    if config.has_backend:
        lines += [
            "    @echo 'Creating .env with generated secrets (if missing)...'",
            "    @test -f .env || mattstack env secrets",
        ]
    lines.append("    @echo 'Setup complete!'")
    return "\n".join(lines)


def _docker_recipes(config: ProjectConfig) -> str:
    profiles = [task_profile(config), REALTIME_PROFILE if config.use_realtime else None]
    lines = ["", "# Start all services (Docker)", "up:", "    docker compose up -d"]
    for profile in profiles:
        if profile:
            lines += [
                "",
                f"# Start all services + the {profile} profile",
                f"up-{profile}:",
                f"    docker compose --profile {profile} up -d",
            ]
    lines += [
        "",
        "# Stop all services",
        "down:",
        "    docker compose down",
        "",
        "# Tail service logs",
        "logs:",
        "    docker compose logs -f",
        "",
        "# Restart all services",
        "restart:",
        "    docker compose restart",
    ]
    return "\n".join(lines)


def _ios_recipes(config: ProjectConfig) -> str:
    scheme = config.display_name.replace(" ", "")
    return f"""\
# Build iOS project
ios-build:
    cd ios && xcodebuild -scheme {scheme} -sdk iphonesimulator build

# Run iOS tests
ios-test:
    cd ios && xcodebuild -scheme {scheme} -sdk iphonesimulator test"""


def _combined_recipes(config: ProjectConfig) -> str:
    cmds = frontend_commands(config)
    lines = ["", "# Run backend tests and the frontend test suite", "test:"]
    if config.has_backend:
        lines += ["    @echo 'Running backend tests...'", f"    {backend_test(config)}"]
    if config.has_frontend:
        lines += ["    @echo 'Running frontend tests...'", frontend_recipe(cmds.test, "test")]
    lines += ["", "# Lint all code", "lint:"]
    if config.has_backend:
        lines.append(f"    {backend_lint(config)}")
    if config.has_frontend:
        lines.append(f"    cd frontend && {cmds.lint}")
    lines += ["", "# Type-check the project", "typecheck:"]
    if config.has_frontend:
        lines.append(frontend_recipe(cmds.typecheck, "type-check"))
    elif config.is_ninja_backend:
        lines.append("    just backend-typecheck")
    elif config.is_nestjs_backend:
        lines.append("    cd backend && bun run build")
    else:
        lines.append("    cd backend && uv run mypy .")
    lines += ["", "# Format all code", "format:"]
    if config.has_backend:
        fmt = (
            "bun run format" if config.is_nestjs_backend else f"{quality_run(config)} ruff format ."
        )
        lines.append(f"    cd backend && {fmt}")
    if config.has_frontend:
        frontend_format = cmds.format or "echo 'No frontend format script'"
        lines.append(f"    cd frontend && {frontend_format}")
    if config.is_fullstack and not config.is_nestjs_backend:
        lines += [
            "",
            "# Regenerate the OpenAPI client (types, SDK, Zod, TanStack Query)",
            "sync-api:",
            "    mattstack sync openapi",
        ]
    return "\n".join(lines)


def _ci_recipe(config: ProjectConfig) -> str:
    """Static checks that work without a .env, database, or Docker."""
    lines = [
        "",
        "# Run CI checks locally (no .env or database needed)",
        "ci:",
        "    #!/usr/bin/env bash",
        "    set -euo pipefail",
        "    if [ -f .env ]; then",
        "        for k in $(grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' .env | tr -d =); "
        'do unset "$k"; done',
        "    fi",
    ]
    if config.has_backend:
        if config.is_nestjs_backend:
            lines.append("    (cd backend && bun run lint)")
        else:
            run = quality_run(config)
            lines.append(f"    (cd backend && {run} ruff check . && {run} ruff format --check .)")
            if config.is_ninja_backend:
                settings = f"{config.django_package}.settings.test"
                lines += [
                    f"    (cd backend && DJANGO_SETTINGS_MODULE={settings} {run} "
                    "python manage.py check)",
                    f"    (cd backend && DJANGO_SETTINGS_MODULE={settings} {run} "
                    "python manage.py makemigrations --check --dry-run)",
                ]
    if config.has_frontend:
        cmds = frontend_commands(config)
        checks = ["bun install --frozen-lockfile", cmds.lint]
        if cmds.typecheck:
            checks.append(cmds.typecheck)
        checks.append("bun run build")
        lines.append(f"    (cd frontend && {' && '.join(checks)})")
    return "\n".join(lines)


def _gauntlet_recipe(config: ProjectConfig) -> str:
    lines = ["", "# Run every local gate: component gauntlets, API drift, audit", "gauntlet:"]
    if config.has_backend:
        if config.is_ninja_backend:
            lines.append("    just backend-gauntlet")
        else:
            lines += ["    just backend-lint", "    just backend-test"]
    if config.has_frontend:
        if frontend_gate_script(config.frontend_dir, quick=False):
            lines.append("    cd frontend && bun run gauntlet")
        else:
            lines += [
                "    just frontend-lint",
                "    just frontend-typecheck",
                "    just frontend-test",
            ]
    if config.is_fullstack and not config.is_nestjs_backend:
        lines.append("    mattstack sync check")
    lines.append("    mattstack audit --no-todo")
    return "\n".join(lines)


def _clean_recipes(config: ProjectConfig) -> str:
    lines = ["", "# Remove build artifacts; keeps containers' data volumes", "clean:"]
    if config.has_backend:
        lines += [
            "    docker compose down",
            "    rm -rf backend/.pytest_cache backend/__pycache__ backend/dist",
        ]
    if config.has_frontend:
        lines.append("    rm -rf frontend/node_modules frontend/dist")
    if config.has_backend:
        lines += [
            "",
            "# DESTRUCTIVE: delete the database and Redis volumes (CONFIRM=1)",
            "clean-volumes:",
            '    @test "{{ CONFIRM }}" = 1 || '
            "{ echo 'Deletes local data. Rerun with CONFIRM=1' >&2; exit 1; }",
            "    docker compose down -v",
        ]
    return "\n".join(lines)


def _prod_recipes() -> str:
    return f"""\

# Build production images (uses .env.production)
prod-build:
    {_PROD} build

# Start production (uses .env.production)
prod-up:
    {_PROD} up -d --build

# Stop production
prod-down:
    {_PROD} down"""
