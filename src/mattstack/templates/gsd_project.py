"""GSD (get-shit-done) compatible templates for .planning/ directory."""

from __future__ import annotations

import json

from mattstack.config import ProjectConfig
from mattstack.detected import DetectedProject


def generate_gsd_project_md(config: ProjectConfig) -> str:
    """Generate PROJECT.md for GSD workflow."""
    sections = [
        _gsd_header(config),
        _gsd_vision(config),
        _gsd_stack(config),
        _gsd_conventions(config),
        _gsd_structure(config),
        _gsd_commands(config),
    ]
    return "\n\n".join(sections) + "\n"


def _gsd_header(config: ProjectConfig) -> str:
    return f"# {config.display_name}"


def _gsd_vision(config: ProjectConfig) -> str:
    project_type = config.project_type.value.replace("-", " ")
    return f"## Vision\n{project_type}-based application scaffolded with mattstack."


def _gsd_stack(config: ProjectConfig) -> str:
    lines = ["## Stack"]
    if config.has_backend:
        lines.append("- Backend: Django + django-ninja (Python 3.12+, uv)")
        lines.append("- Database: PostgreSQL 17 (Docker)")
        if config.use_redis:
            lines.append("- Cache: Redis 7 (Docker)")
    if config.has_frontend:
        if config.is_nextjs:
            lines.append("- Frontend: Next.js + TypeScript (bun)")
        else:
            lines.append("- Frontend: React + Vite + TypeScript (bun)")
    return "\n".join(lines)


def _gsd_conventions(config: ProjectConfig) -> str:
    lines = [
        "## Conventions",
        "- Package managers: uv (Python), bun (JavaScript)",
        "- Linting: ruff (Python), eslint (JavaScript)",
        "- Testing: pytest (Python), vitest (JavaScript)",
    ]
    if config.has_backend:
        lines.append("- API style: django-ninja (Pydantic schemas, NOT DRF)")
    lines.append("- Type safety: Python type hints, strict TypeScript")
    return "\n".join(lines)


def _gsd_structure(config: ProjectConfig) -> str:
    lines = ["## Project Structure"]
    if config.has_backend:
        lines.append("- `backend/` — Django API")
    if config.has_frontend:
        desc = "React SPA" if not config.is_nextjs else "Next.js app"
        lines.append(f"- `frontend/` — {desc}")
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
    lines.append("mattstack audit  # Run the Gauntlet gate")
    lines.append("```")
    return "\n".join(lines)


def generate_gsd_state_md(config: ProjectConfig) -> str:
    """Generate initial STATE.md for GSD workflow."""
    sections = [
        "# Project State",
        "",
        "## Current Phase",
        "Initial setup complete. Project scaffolded with mattstack.",
        "",
        "## Decisions",
        "- Package managers: uv (Python), bun (JavaScript)",
    ]
    if config.has_backend:
        sections.append("- API framework: django-ninja")
    if config.has_frontend:
        fw = "Next.js" if config.is_nextjs else "React Vite"
        sections.append(f"- Frontend framework: {fw}")
    sections.extend(["", "## Blockers", "None."])
    return "\n".join(sections) + "\n"


def generate_gsd_project_md_from_detected(project: DetectedProject) -> str:
    """Generate PROJECT.md from detected project state (for rules command)."""
    sections = [
        f"# {project.display_name}",
        _gsd_vision_from_detected(project),
        _gsd_stack_from_detected(project),
        _gsd_conventions_from_detected(project),
        _gsd_structure_from_detected(project),
        _gsd_commands_from_detected(project),
    ]
    return "\n\n".join(sections) + "\n"


def _gsd_vision_from_detected(project: DetectedProject) -> str:
    parts = []
    if project.has_backend:
        parts.append("backend")
    if project.has_frontend:
        parts.append("frontend")
    if project.has_ios:
        parts.append("iOS")
    stack_desc = "+".join(parts) if parts else "application"
    return f"## Vision\n{stack_desc}-based application."


def _gsd_stack_from_detected(project: DetectedProject) -> str:
    lines = ["## Stack"]
    if project.has_backend:
        lines.append(f"- Backend: {project.backend_framework} (Python, {project.python_pm})")
        lines.append("- Database: PostgreSQL (Docker)")
        if project.use_redis:
            lines.append("- Cache: Redis (Docker)")
    if project.has_frontend:
        fw = "Next.js" if project.is_nextjs else project.frontend_framework
        lines.append(f"- Frontend: {fw} + TypeScript ({project.js_pm})")
    return "\n".join(lines)


def _gsd_conventions_from_detected(project: DetectedProject) -> str:
    lines = [
        "## Conventions",
        f"- Package managers: {project.python_pm} (Python), {project.js_pm} (JavaScript)",
        "- Linting: ruff (Python), eslint (JavaScript)",
        "- Testing: pytest (Python), vitest (JavaScript)",
    ]
    if project.has_backend:
        lines.append("- API style: django-ninja (Pydantic schemas, NOT DRF)")
    lines.append("- Type safety: Python type hints, strict TypeScript")
    return "\n".join(lines)


def _gsd_structure_from_detected(project: DetectedProject) -> str:
    lines = ["## Project Structure"]
    if project.has_backend:
        lines.append("- `backend/` — Django API")
    if project.has_frontend:
        desc = "React SPA" if not project.is_nextjs else "Next.js app"
        lines.append(f"- `frontend/` — {desc}")
    if project.has_docker:
        lines.append("- `docker-compose.yml` — Infrastructure")
    lines.extend(["- `Makefile` — All commands", "- `CLAUDE.md` — AI agent context"])
    return "\n".join(lines)


def _gsd_commands_from_detected(project: DetectedProject) -> str:
    lines = ["## Key Commands", "", "```bash"]
    if project.has_backend:
        lines.append("make setup && make up && make backend-migrate")
    else:
        lines.append("make setup")
    lines.extend(
        [
            "mattstack dev    # Start everything",
            "mattstack test   # Run all tests",
            "mattstack audit  # Run the Gauntlet gate",
            "```",
        ]
    )
    return "\n".join(lines)


def generate_gsd_state_md_from_detected(project: DetectedProject) -> str:
    """Generate initial STATE.md from detected project state (for rules command)."""
    sections = [
        "# Project State",
        "",
        "## Current Phase",
        "Initial setup complete. Project detected by mattstack rules.",
        "",
        "## Decisions",
        f"- Package managers: {project.python_pm} (Python), {project.js_pm} (JavaScript)",
    ]
    if project.has_backend:
        sections.append(f"- API framework: {project.backend_framework}")
    if project.has_frontend:
        fw = "Next.js" if project.is_nextjs else project.frontend_framework
        sections.append(f"- Frontend framework: {fw}")
    sections.extend(["", "## Blockers", "None."])
    return "\n".join(sections) + "\n"


def generate_gsd_config_json_static() -> str:
    """Generate .planning/config.json for GSD settings (no project config needed)."""
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


def generate_gsd_config_json(config: ProjectConfig) -> str:
    """Generate .planning/config.json for GSD settings."""
    _ = config  # Reserved for future config-specific overrides
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
