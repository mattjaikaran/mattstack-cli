"""Point the root agent instructions at each component's own guidance.

Consolidation keeps canonical component guidance (``AGENTS.md``, ``.omp/rules/``,
``.context/``, committed ``.claude/skills/``, and a ``CLAUDE.md`` that no
``AGENTS.md`` duplicates) and removes per-harness adapters. The root
``AGENTS.md`` names those files instead of copying them. Each entry is listed
only when it exists on disk.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from mattstack.config import ProjectConfig
from mattstack.templates.stack_facts import Toolchain

_GUIDANCE = ("AGENTS.md", "CLAUDE.md", ".omp/rules", ".context", ".claude/skills")
_JUST_RECIPE = re.compile(r"^gauntlet-quick\s*:", re.M)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def package_scripts(directory: Path) -> set[str]:
    """Return the script names in ``directory/package.json``; empty when unreadable."""
    try:
        scripts = json.loads(_read(directory / "package.json") or "{}").get("scripts", {})
    except (json.JSONDecodeError, AttributeError):
        return set()
    return set(scripts) if isinstance(scripts, dict) else set()


def backend_gate(directory: Path) -> list[str] | None:
    """Return the backend's quick gate command, or None when it has none."""
    if _JUST_RECIPE.search(_read(directory / "justfile")):
        return ["just", "gauntlet-quick"]
    return None


def frontend_gate_script(directory: Path, *, quick: bool) -> str | None:
    """Return the frontend gate script; ``quick`` prefers ``gauntlet:quick``."""
    scripts = package_scripts(directory)
    order = ("gauntlet:quick", "gauntlet") if quick else ("gauntlet",)
    return next((name for name in order if name in scripts), None)


def _quality_gate(name: str, directory: Path, tools: Toolchain) -> str | None:
    if name == "backend":
        gate = backend_gate(directory)
        return f"cd backend && {' '.join(gate)}" if gate else None
    script = frontend_gate_script(directory, quick=True)
    return f"cd frontend && {tools.js_run(script)}" if script else None


def component_guidance(config: ProjectConfig, tools: Toolchain) -> str | None:
    """Return the "Component guidance" section, or None when no component exists."""
    components: list[tuple[str, Path]] = []
    if config.has_backend:
        components.append(("backend", config.backend_dir))
    if config.has_frontend:
        components.append(("frontend", config.frontend_dir))
    lines: list[str] = []
    for name, directory in components:
        sources = [f"`{name}/{rel}`" for rel in _GUIDANCE if (directory / rel).exists()]
        if sources:
            lines.append(f"- `{name}/`: read {', '.join(sources)} before changing it.")
        else:
            lines.append(f"- `{name}/`: has no agent guidance; follow the rules below.")
        gate = _quality_gate(name, directory, tools)
        if gate:
            lines.append(f"- `{name}/`: run `{gate}` before you finish a change there.")
    if not lines:
        return None
    return "## Component guidance\n\n" + "\n".join(lines)
