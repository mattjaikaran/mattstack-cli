"""Root ``make gauntlet``: every local gate, because the project runs no CI.

Each component keeps its own gate: the backend's ``just gauntlet`` and the
frontend's ``gauntlet`` script. A component without one runs its lint and
test targets instead, which fail when a script is missing. A fullstack
Python project then checks that the committed OpenAPI client matches the
backend schema, and the mattstack audit runs last.
"""

from __future__ import annotations

import re

from mattstack.config import ProjectConfig
from mattstack.templates.component_guidance import frontend_gate_script

_JUST_GAUNTLET = re.compile(r"^gauntlet\s*:", re.M)


def _backend_gate(config: ProjectConfig) -> str:
    try:
        justfile = (config.backend_dir / "justfile").read_text(encoding="utf-8")
    except OSError:
        justfile = ""
    if _JUST_GAUNTLET.search(justfile):
        return "cd backend && uv run --extra dev just gauntlet"
    return "$(MAKE) backend-lint backend-test"


def _frontend_gate(config: ProjectConfig) -> str:
    if frontend_gate_script(config.frontend_dir, quick=False):
        return "cd frontend && bun run gauntlet"
    return "$(MAKE) frontend-lint frontend-typecheck frontend-test"


def gauntlet_target(config: ProjectConfig) -> str:
    """Return the ``gauntlet`` target for the selected components."""
    steps: list[str] = []
    if config.has_backend:
        steps.append(_backend_gate(config))
    if config.has_frontend:
        steps.append(_frontend_gate(config))
    if config.is_fullstack and not config.is_nestjs_backend:
        steps.append("mattstack sync check")
    steps.append("mattstack audit --no-todo")
    recipe = "\n".join(f"\t{step}" for step in steps)
    return f"""
.PHONY: gauntlet
gauntlet: ## Run every local gate (no CI): component gauntlets, API drift, audit
{recipe}"""
