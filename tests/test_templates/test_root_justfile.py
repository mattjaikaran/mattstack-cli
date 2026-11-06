"""Contract tests for the generated root justfile.

The monorepo root owns every command. The backend boilerplate's own justfile
targets its standalone Compose stack (service ``django``, profile ``dev``), so
an init must drop it and generate one root file against the monorepo service
``api-dev`` instead.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mattstack.config import (
    BackendFramework,
    FrontendFramework,
    ProjectConfig,
    ProjectType,
    TaskBackend,
)
from mattstack.templates.root_justfile import generate_justfile

CROSS_STACK_RECIPES = (
    "setup",
    "up",
    "down",
    "migrate",
    "superuser",
    "bootstrap",
    "ci",
    "test",
    "lint",
    "typecheck",
    "format",
    "sync-api",
    "prod-build",
    "prod-up",
    "prod-down",
    "gauntlet",
)

# The uv-only backend recipes the standalone justfile used to provide.
BACKEND_RECIPES = (
    "backend-gauntlet",
    "backend-openapi",
    "backend-audit",
    "backend-security-scan",
    "backend-check-conventions",
)


def _config(
    tmp_path: Path,
    project_type: ProjectType,
    *,
    backend: BackendFramework = BackendFramework.DJANGO_NINJA,
    frontend: FrontendFramework = FrontendFramework.REACT_VITE,
) -> ProjectConfig:
    return ProjectConfig(
        name="shop",
        path=tmp_path / "shop",
        project_type=project_type,
        backend_framework=backend,
        frontend_framework=frontend,
        task_backend=TaskBackend.CELERY,
        use_redis=True,
        init_git=False,
    )


def _fullstack(tmp_path: Path) -> ProjectConfig:
    return _config(tmp_path, ProjectType.FULLSTACK)


def _backend_only(tmp_path: Path) -> ProjectConfig:
    return _config(tmp_path, ProjectType.BACKEND_ONLY)


def _frontend_only(tmp_path: Path) -> ProjectConfig:
    return _config(tmp_path, ProjectType.FRONTEND_ONLY)


def test_fullstack_emits_the_cross_stack_recipes(tmp_path: Path) -> None:
    content = generate_justfile(_fullstack(tmp_path))
    assert "set dotenv-load" in content
    for recipe in CROSS_STACK_RECIPES:
        assert f"\n{recipe}:" in content, f"missing {recipe} recipe"
    assert "api-dev" in content
    assert "Makefile" not in content
    # just 1.21 (Ubuntu 24.04) rejects [working-directory].
    assert "[working-directory" not in content


def test_backend_recipes_cd_into_backend(tmp_path: Path) -> None:
    content = generate_justfile(_fullstack(tmp_path))
    for recipe in BACKEND_RECIPES:
        assert f"\n{recipe}:" in content, f"missing {recipe} recipe"
    assert "cd backend &&" in content


def test_backend_only_skips_frontend_recipes(tmp_path: Path) -> None:
    content = generate_justfile(_backend_only(tmp_path))
    assert "backend-dev:" in content
    assert "frontend-dev:" not in content
    assert "sync-api:" not in content


def test_frontend_only_skips_backend_recipes(tmp_path: Path) -> None:
    content = generate_justfile(_frontend_only(tmp_path))
    assert "frontend-dev:" in content
    assert "backend-dev:" not in content
    assert "migrate:" not in content
    assert "docker compose exec" not in content


def test_fastapi_migrate_uses_alembic(tmp_path: Path) -> None:
    config = _config(tmp_path, ProjectType.FULLSTACK, backend=BackendFramework.FASTAPI)
    content = generate_justfile(config)
    assert "alembic upgrade head" in content
    assert "manage.py" not in content


@pytest.mark.skipif(shutil.which("just") is None, reason="just is not installed")
@pytest.mark.parametrize("factory", [_fullstack, _backend_only, _frontend_only])
def test_generated_justfile_parses(tmp_path: Path, factory) -> None:
    """A missing .env must not break `set dotenv-load` on just 1.21."""
    path = tmp_path / "justfile"
    path.write_text(generate_justfile(factory(tmp_path)), encoding="utf-8")
    result = subprocess.run(
        ["just", "--justfile", str(path), "--summary"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "setup" in result.stdout.split()
