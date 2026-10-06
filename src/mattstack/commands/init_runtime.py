"""Task-backend, realtime, and media-storage choices for ``mattstack init``."""

from __future__ import annotations

from dataclasses import replace
from enum import StrEnum
from types import ModuleType
from typing import Any

import questionary
import typer

from mattstack.config import (
    AiStore,
    BackendFramework,
    GraphStore,
    MediaStorage,
    ProjectConfig,
    ProjectType,
    TaskBackend,
    supported_task_backends,
)
from mattstack.utils.console import print_error

_TASK_LABELS: dict[TaskBackend, str] = {
    TaskBackend.CELERY: "Celery (worker + beat scheduler, default)",
    TaskBackend.HUEY: "Huey",
    TaskBackend.DJANGO_Q: "django-q2",
    TaskBackend.DJANGO_RQ: "django-rq",
    TaskBackend.DRAMATIQ: "Dramatiq",
    TaskBackend.NONE: "None (no worker; enqueueing a task fails loudly)",
}


def _choice(enum_type: type[StrEnum], flag: str, value: str | None) -> Any:
    if value is None:
        return None
    try:
        return enum_type(value)
    except ValueError:
        valid = ", ".join(item.value for item in enum_type)
        print_error(f"{flag} '{value}' is invalid. Valid: {valid}")
        raise typer.Exit(code=2) from None


def runtime_overrides(
    task_backend: str | None,
    realtime: bool | None,
    media_storage: str | None,
    ai: str | None = None,
    graph: str | None = None,
) -> dict[str, Any]:
    """Parse the CLI flags into ProjectConfig overrides; exit 2 on a bad value."""
    overrides: dict[str, Any] = {}
    backend = _choice(TaskBackend, "--task-backend", task_backend)
    if backend is not None:
        overrides["task_backend"] = backend
    if realtime is not None:
        overrides["use_realtime"] = realtime
    media = _choice(MediaStorage, "--media-storage", media_storage)
    if media is not None:
        overrides["media_storage"] = media
    if graph == "age":
        print_error(
            "--graph age is not supported: the apache/age image has no pgvector "
            "(backend docs/AI_LAYER.md). Use --graph cte or --graph neo4j"
        )
        raise typer.Exit(code=2)
    for key, enum_type, flag, value in (
        ("ai_store", AiStore, "--ai", ai),
        ("graph_store", GraphStore, "--graph", graph),
    ):
        choice = _choice(enum_type, flag, value)
        if choice is not None:
            overrides[key] = choice
    return overrides


def apply_runtime_overrides(config: ProjectConfig, overrides: dict[str, Any]) -> ProjectConfig:
    """Apply explicit flags; exit 2 with the valid choices when one cannot run."""
    if not overrides:
        return config
    explicit = overrides.get("task_backend")
    supported = supported_task_backends(config.backend_framework, config.project_type)
    if explicit is not None and explicit not in supported:
        valid = ", ".join(choice.value for choice in supported)
        print_error(
            f"--task-backend {explicit.value} is not supported by the "
            f"{config.backend_framework.value} {config.project_type.value} project. "
            f"Valid: {valid}"
        )
        raise typer.Exit(code=2)
    try:
        return replace(config, **overrides)
    except ValueError as error:
        print_error(str(error))
        raise typer.Exit(code=2) from None


def ask_runtime(
    project_type: ProjectType,
    backend: BackendFramework,
    overrides: dict[str, Any],
    prompts: ModuleType,
    style: questionary.Style,
) -> dict[str, Any]:
    """Ask for the task backend and realtime choices the flags did not set.

    ``prompts`` is the caller's questionary module, so the wizard keeps one
    prompt seam.
    """
    answers = dict(overrides)
    supported = supported_task_backends(backend, project_type)
    if "task_backend" not in answers and len(supported) > 1:
        choice = prompts.select(
            "Background task backend:",
            style=style,
            choices=[prompts.Choice(_TASK_LABELS[item], value=item.value) for item in supported],
        ).ask()
        if not choice:
            raise KeyboardInterrupt
        answers["task_backend"] = TaskBackend(choice)
    ninja = backend == BackendFramework.DJANGO_NINJA and project_type != ProjectType.FRONTEND_ONLY
    if ninja and "use_realtime" not in answers:
        realtime = prompts.confirm(
            "Add the Centrifugo realtime service (opt-in profile)?",
            default=False,
            style=style,
        ).ask()
        if realtime is None:
            raise KeyboardInterrupt
        answers["use_realtime"] = realtime
    return answers
