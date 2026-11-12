"""Point the root agent instructions at each component's own guidance.

Each component keeps its own ``AGENTS.md``. The root ``AGENTS.md`` lists those
files and the quality gate for each component. It does not copy their rules.
An entry appears only when its file or gate exists on disk.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from mattstack.config import ProjectConfig
from mattstack.templates.stack_facts import Toolchain

_JUST_RECIPE = re.compile(r"^gauntlet-quick\s*:", re.M)
_JUST_ROOT_RECIPE = re.compile(r"^backend-gauntlet-quick\s*:", re.M)


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


def backend_gate(directory: Path) -> tuple[list[str], str] | None:
    """Return the backend quick gate and its cwd, or None when it has none.

    A standalone boilerplate keeps its own justfile. A generated monorepo drops
    that file, so the gate is the root justfile's ``backend-`` prefixed recipe.
    """
    if _JUST_RECIPE.search(_read(directory / "justfile")):
        return ["just", "gauntlet-quick"], "backend"
    if _JUST_ROOT_RECIPE.search(_read(directory.parent / "justfile")):
        return ["just", "backend-gauntlet-quick"], "."
    return None


def frontend_gate_script(directory: Path, *, quick: bool) -> str | None:
    """Return the frontend gate script; ``quick`` prefers ``gauntlet:quick``."""
    scripts = package_scripts(directory)
    order = ("gauntlet:quick", "gauntlet") if quick else ("gauntlet",)
    return next((name for name in order if name in scripts), None)


def _quality_gate(name: str, directory: Path, tools: Toolchain) -> str | None:
    if name == "backend":
        gate = backend_gate(directory)
        if not gate:
            return None
        command, cwd = gate
        run = " ".join(command)
        return f"cd {cwd} && {run}" if cwd != "." else run
    script = frontend_gate_script(directory, quick=True)
    return f"cd frontend && {tools.js_run(script)}" if script else None


def _components(config: ProjectConfig) -> list[tuple[str, Path]]:
    components: list[tuple[str, Path]] = []
    if config.has_backend:
        components.append(("backend", config.backend_dir))
    if config.has_frontend:
        components.append(("frontend", config.frontend_dir))
    return components


def nested_guidance(config: ProjectConfig) -> str | None:
    """Return the "Nested files" section, or None when the project has no component."""
    lines: list[str] = []
    for name, directory in _components(config):
        if (directory / "AGENTS.md").is_file():
            lines.append(f"- `{name}/AGENTS.md`: {name} rules and commands.")
        else:
            lines.append(f"- `{name}/` has no `AGENTS.md`. Follow the rules in this file there.")
    if not lines:
        return None
    return (
        "## Nested files\n\n"
        "The nearest AGENTS.md wins when two files disagree. Read the nested file "
        "before you change its directory.\n\n" + "\n".join(lines)
    )


def component_gates(config: ProjectConfig, tools: Toolchain) -> list[str]:
    """Return one bullet per component that has a quick quality gate."""
    lines: list[str] = []
    for name, directory in _components(config):
        gate = _quality_gate(name, directory, tools)
        if gate:
            lines.append(f"- `{name}/`: run `{gate}` before you finish a change there.")
    return lines
