"""TASK_BACKEND=none patching of a cloned django-ninja backend.

The fixtures keep the published boilerplate's anchor lines (django-ninja-boilerplate
api/tasks at v1.12.0) with minimal bodies, so the patched modules import without
Django.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from mattstack.config import BackendFramework, ProjectConfig, ProjectType, TaskBackend
from mattstack.post_processors.task_runtime import ensure_disabled_task_backend
from mattstack.runtime_profiles import runtime_prerequisite_errors

LOADER = '''\
"""Load the task decorator selected by ``TASK_BACKEND``."""

_BACKENDS: dict[str, tuple[str, str, str]] = {
    "celery": (
        "api.tasks.backends.celery_backend",
        "celery_task",
        "celery",
    ),
    "dramatiq": (
        "api.tasks.backends.dramatiq_backend",
        "dramatiq_task",
        "dramatiq[redis]",
    ),
}
'''

CONTRACT = '''\
"""Backend-neutral task contract and runtime registry."""

from __future__ import annotations


class TaskMaxRetriesExceeded(RuntimeError):
    """Raised when a task exceeds its declared retry limit."""


class TaskHandle:
    def __init__(self, *, name, func, enqueue, bind, max_retries):
        self.name, self.func, self._enqueue = name, func, enqueue

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def delay(self, *args, **kwargs):
        return self._enqueue(args, kwargs, 0, 0)


def register_task(handle):
    return handle


def task_name(func, explicit_name):
    return explicit_name or func.__name__


__all__ = [
    "TaskContext",
    "TaskHandle",
]
'''

PACKAGE = '''\
"""Backend-neutral task queue facade."""

from api.tasks.contract import (
    TaskContext,
    TaskHandle,
)

__all__ = [
    "TaskContext",
    "TaskHandle",
]
'''


def _project(tmp_path: Path, task_backend: TaskBackend) -> ProjectConfig:
    tasks = tmp_path / "app" / "backend" / "api" / "tasks"
    (tasks / "backends").mkdir(parents=True)
    (tasks / "loader.py").write_text(LOADER)
    (tasks / "contract.py").write_text(CONTRACT)
    (tasks / "__init__.py").write_text(PACKAGE)
    return ProjectConfig(
        name="app",
        path=tmp_path / "app",
        project_type=ProjectType.BACKEND_ONLY,
        task_backend=task_backend,
    )


def _load(name: str, path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def test_none_backend_is_added_and_rejects_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _project(tmp_path, TaskBackend.NONE)
    assert runtime_prerequisite_errors(config)  # the clone cannot load "none" yet

    changed = ensure_disabled_task_backend(config)

    assert sorted(changed) == [
        "backend/api/tasks/__init__.py",
        "backend/api/tasks/backends/disabled_backend.py",
        "backend/api/tasks/contract.py",
        "backend/api/tasks/loader.py",
    ]
    assert runtime_prerequisite_errors(config) == []
    tasks = config.backend_dir / "api" / "tasks"
    assert '"TaskDispatchDisabled"' in (tasks / "__init__.py").read_text()
    for name in ("api", "api.tasks", "api.tasks.backends"):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    contract = _load("api.tasks.contract", tasks / "contract.py", monkeypatch)
    backend = _load(
        "api.tasks.backends.disabled_backend",
        tasks / "backends" / "disabled_backend.py",
        monkeypatch,
    )

    task = backend.disabled_task(lambda left, right: left + right, name="jobs.add")
    assert task(2, 3) == 5  # a direct call still runs in process
    with pytest.raises(contract.TaskDispatchDisabled, match="'jobs.add'.*TASK_BACKEND='none'"):
        task.delay(2, 3)

    # Idempotent: a second scaffold pass changes nothing.
    assert ensure_disabled_task_backend(config) == []


def test_other_backends_leave_the_clone_untouched(tmp_path: Path) -> None:
    config = _project(tmp_path, TaskBackend.DRAMATIQ)
    assert ensure_disabled_task_backend(config) == []
    assert '"none"' not in (config.backend_dir / "api" / "tasks" / "loader.py").read_text()


def test_unknown_loader_layout_fails_before_writing(tmp_path: Path) -> None:
    config = _project(tmp_path, TaskBackend.NONE)
    loader = config.backend_dir / "api" / "tasks" / "loader.py"
    loader.write_text("BACKENDS = {}\n")
    contract_before = (config.backend_dir / "api" / "tasks" / "contract.py").read_text()

    with pytest.raises(ValueError, match="backend/api/tasks/loader.py.*--task-backend"):
        ensure_disabled_task_backend(config)

    assert (config.backend_dir / "api" / "tasks" / "contract.py").read_text() == contract_before
    assert not (config.backend_dir / "api" / "tasks" / "backends" / "disabled_backend.py").exists()


def test_prerequisites_name_missing_extra_and_realtime_files(tmp_path: Path) -> None:
    backend = tmp_path / "app" / "backend"
    (backend / "api" / "tasks").mkdir(parents=True)
    (backend / "api" / "tasks" / "loader.py").write_text('_BACKENDS = {\n    "huey": (),\n}\n')
    (backend / "pyproject.toml").write_text("[project.optional-dependencies]\ndev = []\n")
    config = ProjectConfig(
        name="app",
        path=tmp_path / "app",
        project_type=ProjectType.BACKEND_ONLY,
        backend_framework=BackendFramework.DJANGO_NINJA,
        task_backend=TaskBackend.HUEY,
        use_realtime=True,
    )

    errors = runtime_prerequisite_errors(config)

    assert any(
        "no 'huey' optional extra" in error and "uv sync --extra huey" in error for error in errors
    )
    assert any("backend/api/centrifugo.py is missing" in error for error in errors)
    assert any("backend/deploy/centrifugo/config.json is missing" in error for error in errors)
