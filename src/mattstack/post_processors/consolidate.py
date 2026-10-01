"""Consolidate cloned boilerplates into a single-root monorepo.

When a boilerplate is cloned into ``backend/`` or ``frontend/`` it carries its own
standalone-project root files (``Makefile``, ``docker-compose*.yml``, ``.env*``,
``Dockerfile``, agent adapters, deployment dirs). In a generated monorepo
those live once at the project root, so this module removes the per-subdirectory
copies. Removal is defensive: missing paths are tolerated.

Agent guidance follows one rule: canonical, component-scoped sources stay, and
per-harness adapters go. ``AGENTS.md``, ``SKILLS.md``, ``.agents/skills/``,
``.omp/`` (rules, ``APPEND_SYSTEM.md``, skills), and ``.context/`` stay in the
component: the Ninja gauntlet's cross-stack rules check and
``scripts/export_rules.py`` read ``.omp/``, and ``AGENTS.md`` points at the
rest. ``CLAUDE.md``, ``.cursorrules``, and the ``.claude/``, ``.cursor/``,
``.windsurf/``, ``.kiro/``, and ``.continue/`` adapters go: they copy the
canonical sources, and the generated root ``CLAUDE.md`` and ``.cursorrules``
replace them.

Removing the backend Compose file also orphans one published Ninja test,
``test_prod_django_behind_nginx_trusts_one_proxy``, which only read
``backend/docker-compose.yml`` as text. Consolidation deletes that function
and the imports only it used; the throttle behaviour tests stay.
"""

from __future__ import annotations

import re
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
    "docker-compose*.yml",
    "docker-compose*.yaml",
    "Dockerfile*",
    ".env*",
    "CLAUDE.md",
    ".cursorrules",
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
    "CLAUDE.md",
    ".gitignore",
    ".dockerignore",
    "DEPLOYMENT.md",
    "nginx.conf",
]

# Per-harness adapters and editor settings, removed from either side.
_EDITOR_DIRS: list[str] = [
    ".claude",
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

_FRONTEND_DIRS: list[str] = [
    *_EDITOR_DIRS,
    "nginx",
    "docs",
    "dist",
]

# The published Ninja boilerplate tests its own docker-compose.yml as source
# text. Match only that top-level function: its def line, indented or blank
# body lines, and the blank lines that separate it from the next block.
_THROTTLE_TESTS = Path("core/tests/test_throttling.py")
_COMPOSE_WIRING_TEST = re.compile(
    r"^def test_prod_django_behind_nginx_trusts_one_proxy\(\):\n(?:[ \t]+[^\n]*\n|\n)*",
    re.MULTILINE,
)
# Imports used only by that test, each with the usage that keeps it.
_COMPOSE_WIRING_IMPORTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("from pathlib import Path\n", re.compile(r"\bPath\b")),
    ("import yaml\n", re.compile(r"\byaml\.")),
    ("from django.conf import settings\n", re.compile(r"(?<![\w.])settings\.")),
)


def consolidate_backend(config: ProjectConfig) -> None:
    """Remove standalone-project files from the cloned backend directory."""
    dirs = [name for name in _BACKEND_DIRS if not (config.use_realtime and name == "deploy")]
    _consolidate(config.backend_dir, _BACKEND_GLOBS, dirs)
    _remove_compose_wiring_test(config.backend_dir / _THROTTLE_TESTS)
    if config.use_realtime:
        deploy = config.backend_dir / "deploy"
        if deploy.is_dir() and not _is_django_app(deploy):
            for path in deploy.iterdir():
                if path.name != "centrifugo":
                    _remove(path)


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


def _remove_compose_wiring_test(path: Path) -> None:
    """Delete the test that reads the removed backend docker-compose.yml."""
    if not path.is_file():
        return
    content = path.read_text()
    updated = _COMPOSE_WIRING_TEST.sub("", content, count=1)
    if updated == content:
        return
    for line, usage in _COMPOSE_WIRING_IMPORTS:
        rest = updated.replace(line, "", 1)
        if line in updated and not usage.search(rest):
            updated = rest
    path.write_text(updated)


def _is_django_app(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink() and (path / "apps.py").is_file()


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists() or path.is_symlink():
        path.unlink(missing_ok=True)
