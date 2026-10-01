"""Add the disabled task backend to a cloned django-ninja backend.

The published boilerplate's ``api/tasks/loader.py`` lists celery, huey,
django_q, django_rq, and dramatiq. ``TASK_BACKEND=none`` needs a loader entry
and an adapter whose ``.delay()`` raises instead of queueing a job that no
worker consumes. When the clone lacks the entry, apply the same change the
boilerplate source makes. Parsers use regex anchors on the observed source;
a missing anchor fails with the file to fix instead of guessing.
"""

from __future__ import annotations

import re
from pathlib import Path

from mattstack.config import BackendFramework, ProjectConfig, TaskBackend
from mattstack.post_processors.tls_health import ensure_health_redirect_exempt
from mattstack.runtime_profiles import runtime_prerequisite_errors
from mattstack.templates.deploy_runtime import tls_env
from mattstack.utils.console import print_error, print_info

_NONE_ENTRY = re.compile(r"""^\s*["']none["']\s*:""", re.MULTILINE)
_BACKENDS_END = re.compile(r"(_BACKENDS: dict\[[^\n]*\] = \{\n(?:[^\n]*\n)*?)(\}\n)")
_MAX_RETRIES = re.compile(r'(class TaskMaxRetriesExceeded\(RuntimeError\):\n    """[^\n]*"""\n)')
_ALL_CONTEXT = re.compile(r'(__all__ = \[\n(?:[^\n]*\n)*?    "TaskContext",\n)')
_IMPORT_CONTEXT = re.compile(r"(from api\.tasks\.contract import \(\n    TaskContext,\n)")

_LOADER_ENTRY = """\
    # No worker: tasks run only when called directly; .delay() raises
    # TaskDispatchDisabled instead of queueing a job nothing consumes.
    "none": (
        "api.tasks.backends.disabled_backend",
        "disabled_task",
        "api",
    ),
"""

_EXCEPTION = '''

class TaskDispatchDisabled(RuntimeError):
    """Raised when code enqueues a task while ``TASK_BACKEND=none``.

    The disabled mode runs no worker, so an accepted message would never run.
    Dispatch fails instead of dropping the job.
    """
'''

DISABLED_BACKEND = '''\
"""Disabled task backend: ``TASK_BACKEND=none`` runs no worker.

Tasks still register and run synchronously when called directly. Enqueueing
raises ``TaskDispatchDisabled``, because no consumer would ever run the
message.
"""

from __future__ import annotations

from typing import Any

from api.tasks.contract import (
    TaskDispatchDisabled,
    TaskHandle,
    register_task,
    task_name,
)

_BACKENDS = "celery, huey, django_q, django_rq, dramatiq"


def disabled_task(
    func,
    *,
    name: str | None = None,
    bind: bool = False,
    max_retries: int = 3,
    **options: Any,
) -> TaskHandle:
    """Wrap a function whose dispatch fails while no task backend runs."""
    del options  # Queue options have no meaning without a queue.
    resolved_name = task_name(func, name)

    def enqueue(
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        countdown: float,
        attempt: int,
    ) -> Any:
        del args, kwargs, countdown, attempt
        raise TaskDispatchDisabled(
            f"Cannot enqueue task '{resolved_name}': TASK_BACKEND='none' runs no "
            f"worker, so the job would never run. Set TASK_BACKEND to one of "
            f"{_BACKENDS} in .env and start its worker profile "
            f"(docs/TASK_BACKENDS.md), or call the task directly to run it "
            f"in this process."
        )

    return register_task(
        TaskHandle(
            name=resolved_name,
            func=func,
            enqueue=enqueue,
            bind=bind,
            max_retries=max_retries,
        )
    )


__all__ = ["disabled_task"]
'''


def _insert(path: Path, text: str, pattern: re.Pattern[str], addition: str, *, after: bool) -> str:
    match = pattern.search(text)
    if match is None:
        raise ValueError(
            f"backend/{path.as_posix()} does not have the layout mattstack patches "
            f"(anchor: {pattern.pattern!r}), so TASK_BACKEND=none cannot be added. "
            f"Add the 'none' backend by hand (see django-ninja-boilerplate "
            f"docs/TASK_BACKENDS.md) or choose another --task-backend. "
            f"Verify: grep -n '\"none\"' backend/api/tasks/loader.py"
        )
    position = match.end(1) if after else match.start(2)
    return text[:position] + addition + text[position:]


def ensure_disabled_task_backend(config: ProjectConfig) -> list[str]:
    """Add ``TASK_BACKEND=none`` to the cloned backend; return the changed files.

    Does nothing unless the project is django-ninja with no task worker, or
    when the loader already defines ``none``. Raises ValueError naming the
    file whose layout does not match.
    """
    if (
        config.backend_framework != BackendFramework.DJANGO_NINJA
        or config.task_backend != TaskBackend.NONE
        or not config.has_backend
    ):
        return []
    tasks = config.backend_dir / "api" / "tasks"
    loader = tasks / "loader.py"
    if not loader.is_file():
        raise ValueError(
            "backend/api/tasks/loader.py is missing, so TASK_BACKEND=none has no "
            "loader to register with. Use a django-ninja-boilerplate with the "
            "api.tasks facade. Verify: test -f backend/api/tasks/loader.py"
        )
    loader_text = loader.read_text(encoding="utf-8")
    if _NONE_ENTRY.search(loader_text):
        return []

    rel = Path("api/tasks")
    contract = tasks / "contract.py"
    package = tasks / "__init__.py"
    contract_text = contract.read_text(encoding="utf-8") if contract.is_file() else ""
    package_text = package.read_text(encoding="utf-8") if package.is_file() else ""
    updates: dict[Path, str] = {
        loader: _insert(rel / "loader.py", loader_text, _BACKENDS_END, _LOADER_ENTRY, after=False)
    }
    if "class TaskDispatchDisabled" not in contract_text:
        contract_text = _insert(
            rel / "contract.py", contract_text, _MAX_RETRIES, _EXCEPTION, after=True
        )
        updates[contract] = _insert(
            rel / "contract.py",
            contract_text,
            _ALL_CONTEXT,
            '    "TaskDispatchDisabled",\n',
            after=True,
        )
    if "TaskDispatchDisabled" not in package_text:
        package_text = _insert(
            rel / "__init__.py",
            package_text,
            _IMPORT_CONTEXT,
            "    TaskDispatchDisabled,\n",
            after=True,
        )
        updates[package] = _insert(
            rel / "__init__.py",
            package_text,
            _ALL_CONTEXT,
            '    "TaskDispatchDisabled",\n',
            after=True,
        )
    updates[tasks / "backends" / "disabled_backend.py"] = DISABLED_BACKEND

    # Validate every anchor before writing, so a mismatch leaves no partial edit.
    for path, text in updates.items():
        path.write_text(text, encoding="utf-8")
    changed = [path.relative_to(config.path).as_posix() for path in updates]
    print_info("Added TASK_BACKEND=none (dispatch raises TaskDispatchDisabled)")
    return changed


def prepare_runtime(
    config: ProjectConfig, *, dry_run: bool, existing_project: bool = False
) -> bool:
    """Add TASK_BACKEND=none when selected, then check runtime prerequisites.

    An existing backend without ``api/tasks/loader.py`` predates the task
    facade and reads no TASK_BACKEND, so ``existing_project`` skips the task
    checks there instead of failing an unrelated ``mattstack add``. New
    projects on HTTPS-edge targets get the USE_TLS health-route exemption.
    Prints each problem with its fix and returns False when any remain.
    """
    if dry_run:
        print_info("[dry-run] Would check the task backend and realtime prerequisites")
        return True
    has_facade = (config.backend_dir / "api" / "tasks" / "loader.py").is_file()
    task_checks = has_facade or not existing_project
    try:
        if task_checks:
            ensure_disabled_task_backend(config)
        if not existing_project and tls_env(config):
            ensure_health_redirect_exempt(config)
    except (OSError, ValueError) as patch_error:
        print_error(str(patch_error))
        return False
    errors = runtime_prerequisite_errors(config, task_checks=task_checks)
    for error in errors:
        print_error(error)
    return not errors
