"""Root and component agent files for generated projects and `mattstack rules`.

``AGENTS.md`` is the root source. ``CLAUDE.md`` imports it and ``.cursorrules``
points at it, so no harness gets a second copy. Components keep their own
``AGENTS.md``; agents that follow the AGENTS.md standard read the nearest one.
``.claude/settings.json`` denies `git push` and `rm -rf`; mattstack never
writes ``settings.local.json``, which belongs to each developer.
``.mcp.json`` lists only the MCP servers every component declares the same way.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mattstack.config import ProjectConfig
from mattstack.templates.root_agents_md import generate_agents_md
from mattstack.templates.stack_facts import Toolchain

# Claude Code expands `@path` imports in CLAUDE.md.
CLAUDE_POINTER = "@AGENTS.md\n"

CURSOR_ADAPTER = (
    "# Cursor adapter\n\n"
    "Read and follow `AGENTS.md` at the repository root. It lists each "
    "component's own rules. Do not add rules to this file.\n"
)

DENIED_COMMANDS: tuple[str, ...] = (
    "Bash(git push)",
    "Bash(git push *)",
    "Bash(rm -rf *)",
    "Bash(rm -fr *)",
)


def claude_settings() -> str:
    """Return the shared Claude Code project settings."""
    settings = {
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "permissions": {"deny": list(DENIED_COMMANDS)},
    }
    return json.dumps(settings, indent=2) + "\n"


def _mcp_servers(directory: Path) -> dict[str, Any] | None:
    try:
        data = json.loads((directory / ".mcp.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    return servers if isinstance(servers, dict) else None


def shared_mcp_servers(component_dirs: list[Path]) -> dict[str, Any]:
    """Return servers that every component's ``.mcp.json`` declares identically."""
    declared = [_mcp_servers(directory) for directory in component_dirs]
    if not declared or any(servers is None for servers in declared):
        return {}
    first, *rest = [servers for servers in declared if servers is not None]
    return {
        name: spec
        for name, spec in sorted(first.items())
        if all(other.get(name) == spec for other in rest)
    }


def component_dirs(config: ProjectConfig) -> list[Path]:
    """Return the cloned component directories the project has."""
    dirs: list[Path] = []
    if config.has_backend:
        dirs.append(config.backend_dir)
    if config.has_frontend:
        dirs.append(config.frontend_dir)
    return dirs


def agent_files(config: ProjectConfig, tools: Toolchain | None = None) -> dict[str, str]:
    """Return root and component agent files, keyed by path relative to the project root."""
    files = {
        "AGENTS.md": generate_agents_md(config, tools),
        "CLAUDE.md": CLAUDE_POINTER,
        ".cursorrules": CURSOR_ADAPTER,
        ".claude/settings.json": claude_settings(),
    }
    servers = shared_mcp_servers(component_dirs(config))
    if servers:
        files[".mcp.json"] = json.dumps({"mcpServers": servers}, indent=2) + "\n"
    return files
