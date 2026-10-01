"""Tests for ProjectConfig validation logic (Phase 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mattstack.config import BackendFramework, MediaStorage, ProjectConfig, ProjectType, TaskBackend


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
        task_backend=TaskBackend.HUEY,
        use_redis=True,
        include_ios=True,
    )
    assert config.task_backend == TaskBackend.NONE
    assert config.use_redis is False
    assert config.include_ios is False


@pytest.mark.parametrize("backend", [TaskBackend.CELERY, TaskBackend.DRAMATIQ])
def test_task_backend_auto_enables_redis(backend: TaskBackend) -> None:
    config = ProjectConfig(
        name="test",
        path=Path("/tmp/test"),
        backend_framework=BackendFramework.FASTAPI
        if backend == TaskBackend.CELERY
        else BackendFramework.DJANGO_NINJA,
        task_backend=backend,
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
        task_backend=TaskBackend.NONE,
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


def test_nestjs_maps_legacy_celery_default_to_its_own_queue() -> None:
    config = ProjectConfig(
        name="test", path=Path("/tmp/test"), backend_framework=BackendFramework.NESTJS
    )
    assert config.task_backend == TaskBackend.NONE
    assert config.use_celery is False


@pytest.mark.parametrize(
    ("backend", "task_backend"),
    [
        (BackendFramework.FASTAPI, TaskBackend.HUEY),
        (BackendFramework.DJANGO_MATT, TaskBackend.DRAMATIQ),
        (BackendFramework.NESTJS, TaskBackend.DJANGO_RQ),
    ],
)
def test_task_backend_outside_ninja_names_valid_choices(
    backend: BackendFramework, task_backend: TaskBackend
) -> None:
    with pytest.raises(ValueError, match="--task-backend with one of"):
        ProjectConfig(
            name="test",
            path=Path("/tmp/test"),
            backend_framework=backend,
            task_backend=task_backend,
        )


@pytest.mark.parametrize("backend", [BackendFramework.FASTAPI, BackendFramework.NESTJS])
def test_realtime_and_s3_require_ninja(backend: BackendFramework) -> None:
    with pytest.raises(ValueError, match="Remove --realtime"):
        ProjectConfig(
            name="test", path=Path("/tmp/test"), backend_framework=backend, use_realtime=True
        )
    with pytest.raises(ValueError, match="--media-storage local"):
        ProjectConfig(
            name="test",
            path=Path("/tmp/test"),
            backend_framework=backend,
            media_storage=MediaStorage.S3,
        )
