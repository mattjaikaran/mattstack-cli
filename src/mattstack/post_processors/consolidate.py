"""Consolidate cloned boilerplates into a single-root monorepo.

When a boilerplate is cloned into ``backend/`` or ``frontend/`` it carries its own
standalone-project root files (``Makefile``, ``docker-compose*.yml``, ``.env*``,
``Dockerfile``, ``README``, agent configs, deployment dirs). In a generated monorepo
those live once at the project root, so this module removes the per-subdirectory
copies. Removal is defensive: missing paths are tolerated.
"""

from __future__ import annotations

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
    "CLAUDE.md",
    ".gitignore",
    ".dockerignore",
    "DEPLOYMENT.md",
    "nginx.conf",
]

# Editor/agent directories removed from either side.
_EDITOR_DIRS: list[str] = [
    ".claude",
    ".cursor",
    ".vscode",
    ".omp",
    ".agents",
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


def consolidate_backend(config: ProjectConfig) -> None:
    """Remove standalone-project files from the cloned backend directory."""
    _consolidate(config.backend_dir, _BACKEND_GLOBS, _BACKEND_DIRS)


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
        _remove(root / name)


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists() or path.is_symlink():
        path.unlink(missing_ok=True)
