"""Cursor IDE .cursorrules template for generated projects and `mattstack rules`."""

from __future__ import annotations

from mattstack.config import ProjectConfig
from mattstack.templates.stack_facts import BackendFacts, Toolchain, backend_facts


def generate_cursorrules(config: ProjectConfig, tools: Toolchain | None = None) -> str:
    """Generate .cursorrules for Cursor IDE agent configuration."""
    tools = tools or Toolchain()
    backend = backend_facts(config.backend_framework, tools)
    sections = [
        _header(),
        _package_managers(config, backend, tools),
        _development(config, backend, tools),
        _testing(config, backend, tools),
        _code_style(config, backend),
        _key_files(config),
    ]
    return "\n\n".join(sections) + "\n"


def _header() -> str:
    return "# Project Rules for Cursor"


def _package_managers(config: ProjectConfig, backend: BackendFacts, tools: Toolchain) -> str:
    lines = ["## Package Managers"]
    if config.has_backend and backend.is_python:
        lines.append(f"- Python: use `{tools.python_pm}` (NEVER {tools.python_alternatives()})")
    lines.append(f"- JavaScript: use `{tools.js_pm}` (NEVER {tools.js_alternatives()})")
    return "\n".join(lines)


def _development(config: ProjectConfig, backend: BackendFacts, tools: Toolchain) -> str:
    lines = ["## Development"]
    if config.has_backend:
        lines.append("- Docker Compose runs PostgreSQL and Redis: `docker compose up -d`")
        lines.append(f"- Backend dev server: `{backend.dev}`")
        lines.append(f"- Migrations after {backend.migrate_trigger}: `{backend.migrate}`")
    if config.has_frontend:
        lines.append(f"- Frontend dev server: `cd frontend && {tools.js_run('dev')}`")
    lines.append("- Or use `mattstack dev` to start everything at once")
    return "\n".join(lines)


def _testing(config: ProjectConfig, backend: BackendFacts, tools: Toolchain) -> str:
    lines = ["## Testing"]
    if config.has_backend:
        lines.append(f"- Backend: `cd backend && {backend.test}`")
    if config.has_frontend:
        lines.append(f"- Frontend: `cd frontend && {tools.js_run('test')}`")
    lines.append("- Or use `mattstack test` to run all")
    return "\n".join(lines)


def _code_style(config: ProjectConfig, backend: BackendFacts) -> str:
    lines = ["## Code Style"]
    if config.has_backend and backend.is_python:
        lines.append("- Python: type hints required, ruff for linting/formatting")
    lines.append("- TypeScript: strict mode, no `any` types")
    if config.has_backend:
        lines.append(f"- Backend API: {backend.api_rule}")
    return "\n".join(lines)


def _key_files(config: ProjectConfig) -> str:
    lines = [
        "## Key Files",
        "- `CLAUDE.md` — Full project context for AI agents",
    ]
    if config.has_backend:
        lines.append("- `.env.example` — Required environment variables")
    lines.append("- `Makefile` — All available make targets")
    if config.has_backend:
        lines.append("- `docker-compose.yml` — Infrastructure services")
    return "\n".join(lines)
