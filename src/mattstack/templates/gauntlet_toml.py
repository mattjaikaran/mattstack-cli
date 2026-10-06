"""Root ``gauntlet.toml`` that wraps the project's existing local gates.

Gauntlet (a separate, language-agnostic verifier) runs each gate as a
declarative custom check: ``[checks.custom.<name>]`` with ``command``,
``args``, ``cwd``, ``scope``, ``match_files``, and ``timeout_ms``
(Gauntlet ``docs/spec/gauntlet-toml.md``, schema version 1). A gate is listed
only when the component on disk defines it.
"""

from __future__ import annotations

import json

from mattstack.config import ProjectConfig
from mattstack.templates.component_guidance import backend_gate, frontend_gate_script
from mattstack.templates.stack_facts import Toolchain

# Whole-suite gates run tests; Gauntlet's 30-second default is too short.
_TIMEOUT_MS = 900_000


def _check(name: str, command: list[str], cwd: str, match_files: list[str]) -> str:
    executable, *args = command
    return "\n".join(
        [
            f"[checks.custom.{name}]",
            f"command = {json.dumps(executable)}",
            f"args = {json.dumps(args)}",
            f"cwd = {json.dumps(cwd)}",
            'scope = "all"',
            f"match_files = {json.dumps(match_files)}",
            f"timeout_ms = {_TIMEOUT_MS}",
        ]
    )


def generate_gauntlet_toml(config: ProjectConfig, tools: Toolchain | None = None) -> str:
    """Return ``gauntlet.toml`` for the project's local gates."""
    tools = tools or Toolchain()
    checks: list[str] = []
    gate = backend_gate(config.backend_dir) if config.has_backend else None
    if gate:
        checks.append(_check("backend-gauntlet", gate, "backend", ["backend/**/*"]))
    script = frontend_gate_script(config.frontend_dir, quick=False) if config.has_frontend else None
    if script:
        command = [tools.js_pm, "run", script]
        checks.append(_check("frontend-gauntlet", command, "frontend", ["frontend/**/*"]))
    if config.is_fullstack and config.is_django_backend:
        checks.append(
            _check(
                "types-in-sync",
                ["mattstack", "sync", "check"],
                ".",
                ["backend/**/*.py", "frontend/src/**/*"],
            )
        )
    header = (
        "# Gauntlet wraps this project's local gates; nothing here runs in CI.\n"
        "# Run: gauntlet check. Schema: Gauntlet docs/spec/gauntlet-toml.md.\n\n"
        f"[project]\nname = {json.dumps(config.name)}\nschema_version = 1"
    )
    return "\n\n".join([header, *checks]) + "\n"
