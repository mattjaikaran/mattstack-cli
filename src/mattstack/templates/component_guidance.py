"""Point the root agent instructions at each component's own guidance.

Consolidation keeps canonical component guidance (``AGENTS.md``, ``.omp/rules/``,
``.context/``) and removes per-harness adapters. Claude Code reads ``CLAUDE.md``
but not ``AGENTS.md``, so the root ``CLAUDE.md`` names those files instead of
copying them. Each entry is listed only when it exists on disk.
"""

from __future__ import annotations

import re
from pathlib import Path

from mattstack.config import ProjectConfig
from mattstack.templates.stack_facts import Toolchain

_GUIDANCE = ("AGENTS.md", ".omp/rules", ".context")
_JUST_RECIPE = re.compile(r"^gauntlet-quick\s*:", re.M)
_PACKAGE_SCRIPT = re.compile(r'"gauntlet:quick"\s*:')


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _quality_gate(name: str, directory: Path, tools: Toolchain) -> str | None:
    if _JUST_RECIPE.search(_read(directory / "justfile")):
        return f"cd {name} && just gauntlet-quick"
    if _PACKAGE_SCRIPT.search(_read(directory / "package.json")):
        return f"cd {name} && {tools.js_run('gauntlet:quick')}"
    return None


def component_guidance(config: ProjectConfig, tools: Toolchain) -> str | None:
    """Return the "Component guidance" section, or None when no component has any."""
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
        gate = _quality_gate(name, directory, tools)
        if gate:
            lines.append(f"- `{name}/`: run `{gate}` before you finish a change there.")
    if not lines:
        return None
    return "## Component guidance\n\n" + "\n".join(lines)
