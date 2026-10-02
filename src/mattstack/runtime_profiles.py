"""Task-queue and realtime runtime profiles for generated projects.

Every value mirrors the django-ninja boilerplate: the ``TASK_BACKEND`` names in
``api/tasks/loader.py``, the optional extras in ``pyproject.toml``, and the
worker profiles, commands, and Centrifugo service in ``docker-compose.yml``.
The other backends ship Celery only, and NestJS runs Bull inside the API.
"""

from __future__ import annotations

import re
import shlex
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from mattstack.config import BackendFramework, MediaStorage, ProjectConfig, TaskBackend
from mattstack.stack_detection import mentions_package

# Centrifugo: image, config file inside the backend, and ports from the
# boilerplate's ``realtime`` profile. The container listens on 8000.
CENTRIFUGO_SERVICE = "centrifugo"
CENTRIFUGO_IMAGE = "centrifugo/centrifugo:v5"
CENTRIFUGO_CONFIG = "deploy/centrifugo/config.json"
CENTRIFUGO_PORT = 8800
CENTRIFUGO_CONTAINER_PORT = 8000
REALTIME_PROFILE = "realtime"
REALTIME_SECRETS = ("CENTRIFUGO_API_KEY", "CENTRIFUGO_TOKEN_SECRET")

_PROFILES: dict[TaskBackend, str] = {
    TaskBackend.CELERY: "celery",
    TaskBackend.HUEY: "huey",
    TaskBackend.DJANGO_Q: "django-q",
    TaskBackend.DJANGO_RQ: "django-rq",
    TaskBackend.DRAMATIQ: "dramatiq",
}
_NINJA_EXTRAS: dict[TaskBackend, str] = {
    TaskBackend.HUEY: "huey",
    TaskBackend.DJANGO_Q: "django-q",
    TaskBackend.DJANGO_RQ: "django-rq",
    TaskBackend.DRAMATIQ: "dramatiq",
}
_NINJA_WORKERS: dict[TaskBackend, tuple[str, ...]] = {
    TaskBackend.HUEY: ("python", "manage.py", "run_huey"),
    TaskBackend.DJANGO_Q: ("python", "manage.py", "qcluster"),
    TaskBackend.DJANGO_RQ: ("python", "manage.py", "rqworker", "default", "high", "low"),
    TaskBackend.DRAMATIQ: (
        "dramatiq",
        "api.tasks.dramatiq_worker",
        "--processes",
        "1",
        "--threads",
        "4",
    ),
}


@dataclass(frozen=True)
class TaskProcess:
    """One long-running task process: a worker or the Celery beat scheduler."""

    service: str
    role: str  # "worker" | "scheduler"
    argv: tuple[str, ...]

    @property
    def command(self) -> str:
        return shlex.join(self.argv)


def _ninja(config: ProjectConfig) -> bool:
    return config.has_backend and config.backend_framework == BackendFramework.DJANGO_NINJA


def task_backend_extra(config: ProjectConfig) -> str | None:
    """Return the backend's optional extra for the task backend, if any.

    Celery is a base dependency of every Python boilerplate.
    """
    return _NINJA_EXTRAS.get(config.task_backend) if _ninja(config) else None


def task_backend_env(config: ProjectConfig) -> dict[str, str]:
    """Return ``TASK_BACKEND`` for Ninja; without it Ninja defaults to Celery."""
    return {"TASK_BACKEND": config.task_backend.value} if _ninja(config) else {}


def celery_env(config: ProjectConfig, redis_url: str) -> dict[str, str]:
    """Keep API producers and workers on the same broker and result databases."""
    if not config.has_backend or not config.use_celery:
        return {}
    broker_db, result_db = (1, 2) if config.is_fastapi_backend else (0, 0)
    return {
        "CELERY_BROKER_URL": f"{redis_url}/{broker_db}",
        "CELERY_RESULT_BACKEND": f"{redis_url}/{result_db}",
    }


def task_profile(config: ProjectConfig) -> str | None:
    """Return the dev Compose profile that starts the task processes."""
    return _PROFILES.get(config.task_backend) if config.has_backend else None


def task_processes(config: ProjectConfig, *, production: bool) -> tuple[TaskProcess, ...]:
    """Return the processes that consume the selected queue; empty without one."""
    backend = config.task_backend
    if not config.has_backend or backend == TaskBackend.NONE:
        return ()
    if backend == TaskBackend.CELERY:
        level = "warning" if production else "info"
        base = ("celery", "-A", config.django_package)
        concurrency = ("--concurrency=4",) if production else ()
        return (
            TaskProcess("celery-worker", "worker", (*base, "worker", "-l", level, *concurrency)),
            TaskProcess("celery-beat", "scheduler", (*base, "beat", "-l", level)),
        )
    return (TaskProcess(f"{_PROFILES[backend]}-worker", "worker", _NINJA_WORKERS[backend]),)


def uv_run(config: ProjectConfig) -> str:
    """Return ``uv run`` with the task backend's extra, for host and dev commands."""
    extra = task_backend_extra(config)
    return f"uv run --extra {extra}" if extra else "uv run"


def task_summary(config: ProjectConfig) -> str:
    """Return a one-line description of the background task runtime."""
    if config.task_backend == TaskBackend.NONE:
        if config.is_nestjs_backend:
            return "Bull queues inside the NestJS API"
        if _ninja(config):
            return "none (TASK_BACKEND=none: .delay() raises TaskDispatchDisabled)"
        return "none (no worker service runs; nothing consumes queued Celery tasks)"
    services = ", ".join(process.service for process in task_processes(config, production=False))
    return f"{config.task_backend.value} ({services}; profile: {task_profile(config)})"


def runtime_guidance(config: ProjectConfig) -> list[str]:
    """Return agent-facing bullets on how to run tasks and realtime locally."""
    lines: list[str] = []
    profile = task_profile(config)
    if profile and not config.is_nestjs_backend:
        lines.append(
            f"- Background jobs: {task_summary(config)}. Start: `make up-{profile}` (Docker) "
            "or `make backend-worker` (host)"
        )
    elif _ninja(config):
        lines.append(
            "- Background jobs: none. `TASK_BACKEND=none` makes `.delay()` raise "
            "`TaskDispatchDisabled`; choose another backend and run its worker to queue work"
        )
    if config.use_realtime:
        prefix = config.api_prefix
        lines.append(
            "- Realtime: Centrifugo. Start `make up-realtime`; check "
            f"`curl -fsS http://localhost:${{CENTRIFUGO_PORT:-{CENTRIFUGO_PORT}}}/health`; "
            f"JWT-authenticated tokens from `POST {prefix}/realtime/connection-token` and "
            f"`POST {prefix}/realtime/subscription-token`. Secrets: "
            "`CENTRIFUGO_API_KEY`, `CENTRIFUGO_TOKEN_SECRET` in `.env`"
        )
    return lines


def runtime_service_lines(config: ProjectConfig) -> list[str]:
    """Return Docker service bullets for task processes and Centrifugo."""
    profile = task_profile(config)
    lines = [
        f"- `{process.service}`: `{process.command}` (profile: {profile})"
        for process in task_processes(config, production=False)
    ]
    if config.use_realtime:
        lines.append(f"- `{CENTRIFUGO_SERVICE}`: Centrifugo (profile: {REALTIME_PROFILE})")
    return lines


def _metadata_choice(enum_type: type[StrEnum], source: str, value: object) -> Any:
    try:
        if not isinstance(value, str):
            raise ValueError
        return enum_type(value)
    except ValueError:
        valid = ", ".join(choice.value for choice in enum_type)
        raise ValueError(f"{source} is '{value}'. Set it to one of: {valid}") from None


def runtime_kwargs(
    backend_meta: dict[str, Any],
    backend: BackendFramework | None,
    env: dict[str, str],
    manifest: str,
    services: set[str],
) -> dict[str, Any]:
    """Return ProjectConfig runtime kwargs from mattstack.yml, .env, or the manifest.

    Task backend precedence: ``task_backend``, then Ninja's ``TASK_BACKEND``
    in .env (what Django actually loads), then the legacy ``celery`` flag (true
    keeps the backend's default queue, false means none), then a celery
    dependency in the manifest.
    Raises ValueError naming the invalid key and its valid values.
    """
    prefix = "mattstack.yml project.backend"
    raw = backend_meta.get("task_backend")
    legacy = backend_meta.get("celery")
    env_value = env.get("TASK_BACKEND") if backend == BackendFramework.DJANGO_NINJA else None
    if raw is not None:
        task_backend = _metadata_choice(TaskBackend, f"{prefix}.task_backend", raw)
    elif env_value:
        task_backend = _metadata_choice(TaskBackend, ".env TASK_BACKEND", env_value)
    elif isinstance(legacy, bool):
        task_backend = TaskBackend.CELERY if legacy else TaskBackend.NONE
    else:
        celery = mentions_package(manifest, "celery")
        task_backend = TaskBackend.CELERY if celery else TaskBackend.NONE
    realtime = backend_meta.get("realtime", False)
    if not isinstance(realtime, bool):
        raise ValueError(f"{prefix}.realtime is '{realtime}'. Set it to true or false")
    redis = backend_meta.get("redis")
    media = backend_meta.get("media_storage", MediaStorage.LOCAL.value)
    return {
        "task_backend": task_backend,
        "use_realtime": realtime,
        "media_storage": _metadata_choice(MediaStorage, f"{prefix}.media_storage", media),
        # Unchanged legacy rule: an explicit bool wins, else detect Redis.
        "use_redis": (
            redis
            if isinstance(redis, bool)
            else "redis" in services or task_backend != TaskBackend.NONE
        ),
    }


def apply_runtime_metadata(backend_meta: dict[str, Any], config: ProjectConfig) -> None:
    """Persist the task and realtime choices; drop the legacy ``celery`` flag."""
    backend_meta.pop("celery", None)
    backend_meta["task_backend"] = config.task_backend.value
    backend_meta["realtime"] = config.use_realtime
    backend_meta["media_storage"] = config.media_storage.value


def runtime_prerequisite_errors(config: ProjectConfig, *, task_checks: bool = True) -> list[str]:
    """Check the cloned backend implements the selected task and realtime modes.

    ``task_checks=False`` skips the loader and extra checks for an existing
    backend without the ``api.tasks`` facade, which reads no TASK_BACKEND.
    Each message names the missing file or value and the command that fixes
    or verifies it.
    """
    if not _ninja(config):
        return []
    backend = config.backend_dir
    errors: list[str] = []
    loader = backend / "api" / "tasks" / "loader.py"
    value = config.task_backend.value
    text = loader.read_text(encoding="utf-8") if loader.is_file() else ""
    pattern = rf"^\s*[\"']{re.escape(value)}[\"']\s*:"
    # Celery is the loader's default, so only another choice needs an entry.
    needs_entry = task_checks and config.task_backend != TaskBackend.CELERY
    if needs_entry and not re.search(pattern, text, re.MULTILINE):
        errors.append(
            f"backend/api/tasks/loader.py does not define TASK_BACKEND '{value}', so "
            f"Django would reject it at startup. Update django-ninja-boilerplate to a "
            f"version whose loader lists '{value}', or choose another --task-backend. "
            f"Verify: grep -n '\"{value}\"' backend/api/tasks/loader.py"
        )
    extra = task_backend_extra(config)
    if extra and task_checks:
        try:
            data = tomllib.loads((backend / "pyproject.toml").read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            data = {}
        if extra not in data.get("project", {}).get("optional-dependencies", {}):
            errors.append(
                f"backend/pyproject.toml has no '{extra}' optional extra for "
                f"TASK_BACKEND={value}. Add it, then verify: cd backend && uv sync --extra {extra}"
            )
    if config.use_realtime:
        for relative in ("api/centrifugo.py", CENTRIFUGO_CONFIG):
            if not (backend / relative).is_file():
                errors.append(
                    f"backend/{relative} is missing; --realtime needs the boilerplate's "
                    f"Centrifugo integration (docs/REALTIME.md). Restore it or remove "
                    f"--realtime. Verify: test -f backend/{relative}"
                )
    return errors
