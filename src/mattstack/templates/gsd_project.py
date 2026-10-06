"""GSD (get-shit-done) compatible templates for the .planning/ directory."""

from __future__ import annotations

import json

from mattstack.config import FrontendFramework, ProjectConfig
from mattstack.templates.compose_env import service_major
from mattstack.templates.stack_facts import BackendFacts, Toolchain, backend_facts

_FRONTEND_LABELS: dict[FrontendFramework, str] = {
    FrontendFramework.REACT_VITE: "React + Vite",
    FrontendFramework.REACT_VITE_STARTER: "React + Vite",
    FrontendFramework.REACT_RSBUILD: "React + Rsbuild",
    FrontendFramework.REACT_RSBUILD_KIBO: "React + Rsbuild + Kibo UI",
    FrontendFramework.NEXTJS: "Next.js",
}


def generate_gsd_project_md(config: ProjectConfig, tools: Toolchain | None = None) -> str:
    """Generate PROJECT.md for the GSD workflow."""
    tools = tools or Toolchain()
    backend = backend_facts(config.backend_framework, tools)
    sections = [
        f"# {config.display_name}",
        _gsd_vision(config),
        _gsd_stack(config, backend, tools),
        _gsd_conventions(config, backend, tools),
        _gsd_structure(config, backend),
        _gsd_commands(config),
    ]
    return "\n\n".join(sections) + "\n"


def _gsd_vision(config: ProjectConfig) -> str:
    project_type = config.project_type.value.replace("-", " ")
    return f"## Vision\n{project_type}-based application scaffolded with mattstack."


def _frontend_label(config: ProjectConfig) -> str:
    return _FRONTEND_LABELS[config.frontend_framework]


def _gsd_stack(config: ProjectConfig, backend: BackendFacts, tools: Toolchain) -> str:
    lines = ["## Stack"]
    if config.has_backend:
        runtime = f"{backend.language}, {backend.package_manager}"
        lines.append(f"- Backend: {backend.framework} ({runtime})")
        lines.append(f"- Database: PostgreSQL {service_major(config, 'postgres')} (Docker)")
        if config.use_redis:
            lines.append(f"- Cache: Valkey {service_major(config, 'valkey/valkey')} (Docker)")
    if config.has_frontend:
        lines.append(f"- Frontend: {_frontend_label(config)} + TypeScript ({tools.js_pm})")
    return "\n".join(lines)


def _package_managers(config: ProjectConfig, backend: BackendFacts, tools: Toolchain) -> str:
    if config.has_backend and backend.is_python:
        return f"- Package managers: {tools.python_pm} (Python), {tools.js_pm} (JavaScript)"
    return f"- Package manager: {tools.js_pm} (JavaScript)"


def _gsd_conventions(config: ProjectConfig, backend: BackendFacts, tools: Toolchain) -> str:
    lines = ["## Conventions"]
    lines.append(_package_managers(config, backend, tools))
    if config.has_backend:
        lines.append(f"- Backend lint: `{backend.lint}`; backend tests: `{backend.test}`")
        lines.append(f"- API style: {backend.api_rule}")
    if config.has_frontend:
        lines.append(
            f"- Frontend lint: `{tools.js_run('lint')}`; frontend tests: `{tools.js_run('test')}`"
        )
    lines.append("- Type safety: Python type hints, strict TypeScript")
    return "\n".join(lines)


def _gsd_structure(config: ProjectConfig, backend: BackendFacts) -> str:
    lines = ["## Project Structure"]
    if config.has_backend:
        lines.append(f"- `backend/` — {backend.structure}")
    if config.has_frontend:
        lines.append(f"- `frontend/` — {_frontend_label(config)} app")
    if config.has_backend:
        lines.append("- `docker-compose.yml` — Infrastructure")
    lines.append("- `Makefile` — All commands")
    lines.append("- `CLAUDE.md` — AI agent context")
    return "\n".join(lines)


def _gsd_commands(config: ProjectConfig) -> str:
    lines = ["## Key Commands", "", "```bash"]
    if config.has_backend:
        lines.append("make setup && make up && make backend-migrate")
    else:
        lines.append("make setup")
    lines.append("mattstack dev    # Start everything")
    lines.append("mattstack test   # Run all tests")
    lines.append("mattstack audit  # Static analysis")
    lines.append("```")
    return "\n".join(lines)


def generate_gsd_state_md(config: ProjectConfig, tools: Toolchain | None = None) -> str:
    """Generate the initial STATE.md for the GSD workflow."""
    tools = tools or Toolchain()
    backend = backend_facts(config.backend_framework, tools)
    sections = [
        "# Project State",
        "",
        "## Current Phase",
        "Initial setup complete. Project scaffolded with mattstack.",
        "",
        "## Decisions",
    ]
    sections.append(_package_managers(config, backend, tools))
    if config.has_backend:
        sections.append(f"- API framework: {config.backend_framework.value}")
    if config.has_frontend:
        sections.append(f"- Frontend framework: {config.frontend_framework.value}")
    sections.extend(["", "## Blockers", "None."])
    return "\n".join(sections) + "\n"


def generate_gsd_config_json() -> str:
    """Generate .planning/config.json for GSD settings."""
    data = {
        "mode": "interactive",
        "depth": "standard",
        "profile": "balanced",
        "parallelization": {"enabled": True},
        "planning": {"commit_docs": True},
        "workflow": {
            "research": True,
            "plan_check": True,
            "verifier": True,
            "auto_advance": False,
        },
        "git": {
            "branching_strategy": "none",
        },
    }
    return json.dumps(data, indent=2) + "\n"
