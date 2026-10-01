"""Tests for ProjectConfig validation logic (Phase 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mattstack.config import BackendFramework, ProjectConfig, ProjectType


def test_empty_name_raises() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ProjectConfig(name="", path=Path("/tmp/test"))


def test_whitespace_only_name_raises() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ProjectConfig(name="   ", path=Path("/tmp/test"))


def test_special_chars_only_name_raises() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ProjectConfig(name="@#$%", path=Path("/tmp/test"))


def test_frontend_only_forces_no_backend_features() -> None:
    config = ProjectConfig(
        name="test",
        path=Path("/tmp/test"),
        project_type=ProjectType.FRONTEND_ONLY,
        use_celery=True,
        use_redis=True,
        include_ios=True,
    )
    assert config.use_celery is False
    assert config.use_redis is False
    assert config.include_ios is False


def test_celery_auto_enables_redis() -> None:
    config = ProjectConfig(
        name="test",
        path=Path("/tmp/test"),
        use_celery=True,
        use_redis=False,
    )
    assert config.use_redis is True


@pytest.mark.parametrize(
    ("backend", "expected"),
    [
        (BackendFramework.DJANGO_NINJA, True),  # cache, sessions, and throttles need it
        (BackendFramework.DJANGO_MATT, False),
        (BackendFramework.FASTAPI, False),
    ],
)
def test_redis_without_celery_follows_backend(backend: BackendFramework, expected: bool) -> None:
    config = ProjectConfig(
        name="test",
        path=Path("/tmp/test"),
        backend_framework=backend,
        use_celery=False,
        use_redis=False,
    )
    assert config.use_redis is expected
    assert config.use_celery is False


def test_path_string_converted() -> None:
    config = ProjectConfig(name="test", path="/tmp/test")  # type: ignore[arg-type]
    assert isinstance(config.path, Path)


def test_name_normalization_in_post_init() -> None:
    config = ProjectConfig(name="My Cool App", path=Path("/tmp/test"))
    assert config.name == "my-cool-app"
