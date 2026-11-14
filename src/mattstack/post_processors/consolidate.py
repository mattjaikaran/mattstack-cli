"""Consolidate cloned boilerplates into a single-root monorepo.

When a boilerplate is cloned into ``backend/`` or ``frontend/`` it carries its own
standalone-project root files (``Makefile``, ``Makefile.legacy``, ``justfile``,
``docker-compose*.yml``, ``.env*``,
``Dockerfile``, agent adapters, deployment dirs). In a generated monorepo
those live once at the project root, so this module removes the per-subdirectory
copies. Removal is defensive: missing paths are tolerated.

Agent guidance follows one rule: canonical, component-scoped sources stay, and
files that duplicate them go. ``AGENTS.md``, ``SKILLS.md``, ``.agents/skills/``,
``.omp/`` (rules, ``APPEND_SYSTEM.md``, skills), and ``.context/`` stay in the
component: the Ninja gauntlet's cross-stack rules check and
``scripts/export_rules.py`` read ``.omp/``, and ``AGENTS.md`` points at the
rest. Committed ``.claude/skills/<name>/`` stay unless ``.agents/skills/`` or
``.omp/skills/`` holds the same skill; everything else in ``.claude/`` (local
settings, worktrees) goes. ``CLAUDE.md`` and ``.cursorrules`` go only when the
component has an ``AGENTS.md`` they duplicate; without one they are the
canonical guidance and stay. The ``.cursor/``, ``.windsurf/``, ``.kiro/``, and
``.continue/`` adapters go; the generated root ``AGENTS.md`` replaces them.

The backend's standalone agent workflow (tickets, worker, nested ``AGENTS.md``
and ``CLAUDE.md``, recipe-citing docs) names a root the monorepo lacks, so
``_BACKEND_AGENT_PATHS`` removes it and ``_drop_backend_gates`` removes the
gauntlet gates that call what was removed.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

from mattstack.config import ProjectConfig

# Files removed by glob (patterns are relative to the cloned subdirectory).
#
# README* is deliberately absent. `backend/pyproject.toml` declares
# `readme = "README.md"`, so deleting it makes the package unbuildable and
# `uv sync` fails with "Readme file does not exist". Keep the boilerplate
# README in place; the monorepo root README does not replace it.
_BACKEND_GLOBS: list[str] = [
    "Makefile",
    "Makefile.legacy",
    "justfile",
    "docker-compose*.yml",
    "docker-compose*.yaml",
    "Dockerfile*",
    ".env*",
    ".gitignore",
    ".dockerignore",
    ".pre-commit-config.yaml",
    "CHANGELOG.md",
]

_FRONTEND_GLOBS: list[str] = [
    "Makefile",
    "docker-compose*.yml",
    "docker-compose*.yaml",
    "Dockerfile*",
    ".env*",
    "env.example",
    "env.monorepo.example",
    # Parallel bundler configs drift from the real one, which the generator
    # patches in place; `bun run dev` never loads these.
    "*.config.monorepo.*",
    ".gitignore",
    ".dockerignore",
    "DEPLOYMENT.md",
    "nginx.conf",
]

# Per-harness adapters and editor settings, removed from either side.
_EDITOR_DIRS: list[str] = [
    ".cursor",
    ".vscode",
    ".continue",
    ".kiro",
    ".windsurf",
    ".tanstack",
]

_BACKEND_DIRS: list[str] = [
    *_EDITOR_DIRS,
    "cli",
    "docker",
    "deploy",
    "nginx",
    "env",
    "media",
    "files",
]

# Standalone-backend agent workflow, removed from the cloned backend. Each doc
# cites backend-only `just` recipes; the ticket tooling and dev MCP server go
# with `scripts/tickets.py`, which they import, and their smoke tests go too.
_BACKEND_AGENT_PATHS: list[str] = [
    "AGENTS.md",
    "CLAUDE.md",
    "docs/tickets",
    "scripts/agent_status.py",
    "scripts/check_agent_docs.py",
    "scripts/run_dev_mcp.py",
    "scripts/tickets.py",
    "scripts/worker_once.py",
    "tests/smoke/test_dev_mcp.py",
    "tests/smoke/test_worker_once.py",
    "docs/ADOPTION_PROMPT.md",
    "docs/AGENT_HANDOFF.md",
    "docs/AI_LAYER.md",
    "docs/ARCHITECTURE.md",
    "docs/CONSTRAINT_TOOLS.md",
    "docs/DEEPSEC.md",
    "docs/MATTSTACK_INTEGRATION.md",
    "docs/MIGRATION.md",
    "docs/PORTABLE_GAUNTLET.md",
    "docs/REALTIME.md",
    "docs/TASK_BACKENDS.md",
    "docs/openapi/README.md",
    "docs/product/journeys.md",
]

# Gauntlet gates that run the files above, keyed by gate name.
_BACKEND_DROPPED_GATES: dict[str, str] = {
    "agent-docs": "_gate_agent_docs",  # runs scripts/check_agent_docs.py, which needs AGENTS.md
    "tickets": "_gate_tickets",  # runs scripts/tickets.py
    "cli-test": "_gate_cli_test",  # runs cli/tests; backend/cli is not copied
}

_FRONTEND_DIRS: list[str] = [
    *_EDITOR_DIRS,
    "nginx",
    "docs",
    "dist",
]


def consolidate_backend(config: ProjectConfig) -> None:
    """Remove standalone-project files from the cloned backend directory."""
    dirs = [name for name in _BACKEND_DIRS if not (config.use_realtime and name == "deploy")]
    _consolidate(config.backend_dir, _BACKEND_GLOBS, dirs)
    for relative in _BACKEND_AGENT_PATHS:
        _remove(config.backend_dir / relative)
    _drop_backend_gates(config.backend_dir)
    if config.use_realtime:
        deploy = config.backend_dir / "deploy"
        if deploy.is_dir() and not _is_django_app(deploy):
            for path in deploy.iterdir():
                if path.name != "centrifugo":
                    _remove(path)


def _drop_backend_gates(backend: Path) -> None:
    """Remove the gauntlet gates that call the files this module removed."""
    path = backend / "scripts" / "gauntlet.py"
    if not path.is_file():
        return
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    drop: set[int] = set()
    methods = set(_BACKEND_DROPPED_GATES.values())
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name in methods:
            start = min([node.lineno, *(dec.lineno for dec in node.decorator_list)])
            end = node.end_lineno or node.lineno
            drop.update(range(start - 1, end))
            # Drop the one blank line that separates this method from the next.
            if end < len(lines) and not lines[end].strip():
                drop.add(end)
    for name, method in _BACKEND_DROPPED_GATES.items():
        registration = f'gates["{name}"] = self.{method}'
        drop.update(i for i, line in enumerate(lines) if line.strip() == registration)
    if drop:
        kept = (line for i, line in enumerate(lines) if i not in drop)
        path.write_text("".join(kept), encoding="utf-8")


def consolidate_frontend(config: ProjectConfig) -> None:
    """Remove standalone-project files from the cloned frontend directory."""
    _consolidate(config.frontend_dir, _FRONTEND_GLOBS, _FRONTEND_DIRS)


def _consolidate(root: Path, globs: list[str], dirs: list[str]) -> None:
    if not root.exists():
        return
    for pattern in globs:
        for path in root.glob(pattern):
            _remove(path)
    for name in dirs:
        path = root / name
        # A name such as `files` can be a real, optional Django app.
        if _is_django_app(path):
            continue
        _remove(path)
    _drop_agent_duplicates(root)


def _drop_agent_duplicates(root: Path) -> None:
    if (root / "AGENTS.md").is_file():
        for name in ("CLAUDE.md", ".cursorrules"):
            _remove(root / name)
    claude = root / ".claude"
    if not claude.is_dir() or claude.is_symlink():
        _remove(claude)
        return
    for path in claude.iterdir():
        if path.name != "skills" or not path.is_dir():
            _remove(path)
    skills = claude / "skills"
    if skills.is_dir():
        for skill in skills.iterdir():
            if _skill_is_duplicate(root, skill.name):
                _remove(skill)
        if not any(skills.iterdir()):
            skills.rmdir()
    if not any(claude.iterdir()):
        claude.rmdir()


def _skill_is_duplicate(root: Path, name: str) -> bool:
    if (root / ".agents" / "skills" / name).is_dir():
        return True
    omp_skills = root / ".omp" / "skills"
    return omp_skills.is_dir() and any(path.is_dir() for path in omp_skills.rglob(name))


def _is_django_app(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink() and (path / "apps.py").is_file()


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists() or path.is_symlink():
        path.unlink(missing_ok=True)
