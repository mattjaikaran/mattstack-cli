"""Configuration dataclasses and constants."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ProjectType(StrEnum):
    FULLSTACK = "fullstack"
    BACKEND_ONLY = "backend-only"
    FRONTEND_ONLY = "frontend-only"


class Variant(StrEnum):
    STARTER = "starter"
    B2B = "b2b"


class BackendFramework(StrEnum):
    DJANGO_NINJA = "django-ninja"
    DJANGO_MATT = "django-matt"
    FASTAPI = "fastapi"
    NESTJS = "nestjs"


class FrontendFramework(StrEnum):
    REACT_VITE = "react-vite"
    REACT_VITE_STARTER = "react-vite-starter"
    REACT_RSBUILD = "react-rsbuild"
    REACT_RSBUILD_KIBO = "react-rsbuild-kibo"
    NEXTJS = "nextjs"


class DeploymentTarget(StrEnum):
    DOCKER = "docker"
    RAILWAY = "railway"
    RENDER = "render"
    FLY_IO = "fly-io"
    CLOUDFLARE = "cloudflare"
    DIGITAL_OCEAN = "digital-ocean"
    AWS = "aws"
    GCP = "gcp"
    HETZNER = "hetzner"
    SELF_HOSTED = "self-hosted"


class TaskBackend(StrEnum):
    """Background task backend; values match the Ninja ``TASK_BACKEND`` setting."""

    CELERY = "celery"
    HUEY = "huey"
    DJANGO_Q = "django_q"
    DJANGO_RQ = "django_rq"
    DRAMATIQ = "dramatiq"
    NONE = "none"


class MediaStorage(StrEnum):
    """Where the production backend stores user-uploaded media."""

    LOCAL = "local"
    S3 = "s3"


def supported_task_backends(
    backend: BackendFramework, project_type: ProjectType
) -> tuple[TaskBackend, ...]:
    """Return the task backends the chosen backend boilerplate implements.

    Only django-ninja ships the pluggable ``api.tasks`` facade. The other
    Python backends ship Celery, and NestJS uses its built-in Bull queues.
    """
    if project_type == ProjectType.FRONTEND_ONLY or backend == BackendFramework.NESTJS:
        return (TaskBackend.NONE,)
    if backend == BackendFramework.DJANGO_NINJA:
        return tuple(TaskBackend)
    return (TaskBackend.CELERY, TaskBackend.NONE)


REPO_URLS: dict[str, str] = {
    # Python backends
    "django-ninja": "https://github.com/mattjaikaran/django-ninja-boilerplate.git",
    "django-matt": "https://github.com/mattjaikaran/django-matt-starter.git",
    "fastapi": "https://github.com/mattjaikaran/fastapi-boilerplate.git",
    # Node.js / TypeScript backends
    "nestjs": "https://github.com/mattjaikaran/nestjs-boilerplate.git",
    # React frontends
    "react-vite": "https://github.com/mattjaikaran/react-vite-boilerplate.git",
    "react-vite-starter": "https://github.com/mattjaikaran/react-vite-starter.git",
    "react-rsbuild": "https://github.com/mattjaikaran/react-rsbuild-boilerplate.git",
    "react-rsbuild-kibo": "https://github.com/mattjaikaran/react-rsbuild-kibo-boilerplate.git",
    "nextjs": "https://github.com/mattjaikaran/nextjs-starter.git",
    # Mobile
    "swift-ios": "https://github.com/mattjaikaran/swift-ios-starter.git",
}


def get_repo_urls() -> dict[str, str]:
    """Get repo URLs merged with user config overrides."""
    from mattstack.user_config import get_user_repos

    urls = dict(REPO_URLS)
    urls.update(get_user_repos())  # type: ignore[arg-type]
    return urls


def normalize_name(name: str) -> str:
    """Normalize project name: lowercase, hyphens, no special chars."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")


def to_python_package(name: str) -> str:
    """Convert project name to valid Python package name."""
    return normalize_name(name).replace("-", "_")


@dataclass
class ProjectConfig:
    """Full configuration for a project scaffold."""

    name: str
    path: Path
    project_type: ProjectType = ProjectType.FULLSTACK
    variant: Variant = Variant.STARTER
    frontend_framework: FrontendFramework = FrontendFramework.REACT_VITE
    backend_framework: BackendFramework = BackendFramework.DJANGO_NINJA
    include_ios: bool = False
    # Legacy ``use_celery`` maps to CELERY (True) or NONE (False). Read
    # ``use_celery`` as a property; this field is the single source of truth.
    task_backend: TaskBackend = TaskBackend.CELERY
    # Opt-in Centrifugo service (django-ninja only).
    use_realtime: bool = False
    media_storage: MediaStorage = MediaStorage.LOCAL
    use_redis: bool = True
    deployment: DeploymentTarget = DeploymentTarget.DOCKER
    init_git: bool = True
    author_name: str = ""
    author_email: str = ""
    dry_run: bool = False
    # URL prefix where the backend API is mounted. The Django boilerplates
    # mount the API with ``path("api/", api.urls)``.
    api_prefix: str = "/api"

    def __post_init__(self) -> None:
        self.name = normalize_name(self.name)
        if not self.name:
            raise ValueError("Project name cannot be empty")
        if isinstance(self.path, str):
            self.path = Path(self.path)
        self.task_backend = TaskBackend(self.task_backend)
        self.media_storage = MediaStorage(self.media_storage)
        # Frontend-only projects don't need backend features
        if self.project_type == ProjectType.FRONTEND_ONLY:
            self.task_backend = TaskBackend.NONE
            self.use_redis = False
            self.include_ios = False
            self.use_realtime = False
            self.media_storage = MediaStorage.LOCAL
        # NestJS uses Bull (Redis-based queues) not Celery; Redis still needed.
        # The legacy default (Celery on) means "the backend's own queue".
        if self.backend_framework == BackendFramework.NESTJS:
            if self.task_backend == TaskBackend.CELERY:
                self.task_backend = TaskBackend.NONE
            self.use_redis = True
        self._validate_runtime()
        # The django-ninja settings always use a Valkey/Redis cache, and the
        # cache backs sessions, throttles, and readiness. Every Ninja task
        # backend and Centrifugo use the same Redis.
        if (
            self.backend_framework == BackendFramework.DJANGO_NINJA
            and self.project_type != ProjectType.FRONTEND_ONLY
        ):
            self.use_redis = True
        # Celery (FastAPI, django-matt) requires Redis
        if self.task_backend != TaskBackend.NONE:
            self.use_redis = True

    def _validate_runtime(self) -> None:
        """Reject a task, realtime, or media choice the backend cannot run."""
        backend = self.backend_framework.value
        supported = supported_task_backends(self.backend_framework, self.project_type)
        if self.task_backend not in supported:
            valid = ", ".join(choice.value for choice in supported)
            raise ValueError(
                f"task_backend '{self.task_backend.value}' is not supported by the "
                f"{backend} boilerplate. Use --task-backend with one of: {valid}"
            )
        ninja = self.backend_framework == BackendFramework.DJANGO_NINJA
        if self.use_realtime and not (ninja and self.has_backend):
            raise ValueError(
                f"realtime needs the django-ninja backend (api/centrifugo.py); "
                f"{backend} has no Centrifugo integration. Remove --realtime"
            )
        if self.media_storage == MediaStorage.S3 and not (ninja and self.has_backend):
            raise ValueError(
                f"media_storage 's3' needs the django-ninja backend; {backend} has no "
                "S3 media settings. Use --media-storage local"
            )

    @property
    def use_celery(self) -> bool:
        """Whether Celery runs the background tasks (derived from task_backend)."""
        return self.task_backend == TaskBackend.CELERY

    @property
    def is_ninja_backend(self) -> bool:
        return self.backend_framework == BackendFramework.DJANGO_NINJA

    @property
    def python_package_name(self) -> str:
        return to_python_package(self.name)

    @property
    def django_package(self) -> str:
        """Return the import package inside `backend/`.

        The django-ninja boilerplate keeps `api` as its settings, WSGI, and
        Celery module. `mattstack init` renames the distribution and the
        PostgreSQL database to the project name, so `python_package_name`
        differs from the importable package. Celery, gunicorn, and
        DJANGO_SETTINGS_MODULE must all use this value.

        Detect it from the cloned backend rather than assume, so a
        boilerplate that uses a different module still works. Detection
        reads the filesystem, so it does not depend on the order of the
        generator steps.

        The FastAPI boilerplate uses `app` and defines its Celery instance
        in `app/workers/celery_app.py`, so `celery -A app` cannot load it.
        """
        if self.is_fastapi_backend:
            return "app.workers.celery_app"
        backend = self.backend_dir
        from mattstack.stack_detection import settings_module_from_manage

        settings_module = settings_module_from_manage(backend)
        if settings_module:
            package = settings_module.rsplit(".", 1)[0]
            if (backend.joinpath(*package.split(".")) / "wsgi.py").is_file():
                return package
        for candidate in ("api", "app", "config"):
            if (backend / candidate).is_dir():
                return candidate
        return "api"

    @property
    def wsgi_app(self) -> str:
        """Return the WSGI or settings module root, without the submodule."""
        if self.is_fastapi_backend:
            return "app"
        return self.django_package

    @property
    def display_name(self) -> str:
        return self.name.replace("-", " ").title()

    @property
    def has_backend(self) -> bool:
        return self.project_type in (ProjectType.FULLSTACK, ProjectType.BACKEND_ONLY)

    @property
    def has_frontend(self) -> bool:
        return self.project_type in (ProjectType.FULLSTACK, ProjectType.FRONTEND_ONLY)

    @property
    def is_fullstack(self) -> bool:
        return self.project_type == ProjectType.FULLSTACK

    @property
    def is_b2b(self) -> bool:
        return self.variant == Variant.B2B

    @property
    def backend_dir(self) -> Path:
        return self.path / "backend"

    @property
    def frontend_dir(self) -> Path:
        return self.path / "frontend"

    @property
    def ios_dir(self) -> Path:
        return self.path / "ios"

    @property
    def is_nextjs(self) -> bool:
        return self.frontend_framework == FrontendFramework.NEXTJS

    @property
    def is_django_matt(self) -> bool:
        return self.backend_framework == BackendFramework.DJANGO_MATT

    @property
    def is_fastapi_backend(self) -> bool:
        return self.backend_framework == BackendFramework.FASTAPI

    @property
    def is_nestjs_backend(self) -> bool:
        return self.backend_framework == BackendFramework.NESTJS

    @property
    def is_django_backend(self) -> bool:
        return self.backend_framework in (
            BackendFramework.DJANGO_NINJA,
            BackendFramework.DJANGO_MATT,
        )

    @property
    def backend_api_port(self) -> int:
        """Backend API port. NestJS uses 4000 in monorepo to avoid conflicts."""
        return 4000 if self.is_nestjs_backend else 8000

    @property
    def backend_repo_key(self) -> str:
        return self.backend_framework.value

    @property
    def frontend_repo_key(self) -> str:
        return self.frontend_framework.value
