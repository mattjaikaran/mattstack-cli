"""Test fixtures for mattstack."""

from __future__ import annotations

from pathlib import Path

import pytest

from mattstack.config import ProjectConfig, ProjectType, TaskBackend, Variant


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def starter_fullstack_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="test-project",
        path=tmp_path / "test-project",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
    )


@pytest.fixture
def b2b_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="test-b2b",
        path=tmp_path / "test-b2b",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.B2B,
    )


@pytest.fixture
def backend_only_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="test-api",
        path=tmp_path / "test-api",
        project_type=ProjectType.BACKEND_ONLY,
        variant=Variant.STARTER,
    )


@pytest.fixture
def frontend_only_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="test-frontend",
        path=tmp_path / "test-frontend",
        project_type=ProjectType.FRONTEND_ONLY,
        variant=Variant.STARTER,
        task_backend=TaskBackend.NONE,
        use_redis=False,
    )
