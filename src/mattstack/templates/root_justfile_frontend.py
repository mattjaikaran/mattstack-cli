"""Frontend recipes for the generated root justfile."""

from __future__ import annotations

from mattstack.config import ProjectConfig
from mattstack.templates.frontend_commands import frontend_commands
from mattstack.templates.frontend_runtime import FRONTEND_PORT


def frontend_recipe(command: str | None, job: str) -> str:
    """Run the command, or fail: a missing check must not report success."""
    if command:
        return f"    cd frontend && {command}"
    return f"    @echo 'frontend/package.json defines no {job} script' >&2; exit 1"


def frontend_recipes(config: ProjectConfig) -> str:
    cmds = frontend_commands(config)
    dev = "bun run dev"
    if config.is_nextjs:
        dev = f'bun run dev -p "${{FRONTEND_PORT:-{FRONTEND_PORT}}}"'
    return f"""\
# Install frontend deps
frontend-setup:
    cd frontend && bun install

# Run frontend dev server
frontend-dev:
    cd frontend && {dev}

# Build frontend with the root .env browser API settings
frontend-build:
    cd frontend && bun run build

# Run frontend tests
frontend-test:
{frontend_recipe(cmds.test, "test")}

# Type-check frontend
frontend-typecheck:
{frontend_recipe(cmds.typecheck, "type-check")}

# Lint frontend
frontend-lint:
    cd frontend && {cmds.lint}"""
