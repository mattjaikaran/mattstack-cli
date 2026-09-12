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


REPO_URLS: dict[str, str] = {
    # Python backends
    "django-ninja": "https://github.com/mattjaikaran/django-ninja-boilerplate.git",
    "django-matt": "https://github.com/mattjaikaran/django-matt-boilerplate.git",
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

DEFAULT_BRANCH = "main"


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
    use_celery: bool = True
    use_redis: bool = True
    deployment: DeploymentTarget = DeploymentTarget.DOCKER
    init_git: bool = True
    author_name: str = ""
    author_email: str = ""
    dry_run: bool = False

    def __post_init__(self) -> None:
        self.name = normalize_name(self.name)
        if not self.name:
            raise ValueError("Project name cannot be empty")
        if isinstance(self.path, str):
            self.path = Path(self.path)
        # Frontend-only projects don't need backend features
        if self.project_type == ProjectType.FRONTEND_ONLY:
            self.use_celery = False
            self.use_redis = False
            self.include_ios = False
        # NestJS uses Bull (Redis-based queues) not Celery; Redis still needed
        if self.backend_framework == BackendFramework.NESTJS:
            self.use_celery = False
            self.use_redis = True
        # FastAPI uses Celery + Redis (same as Django)
        if self.backend_framework == BackendFramework.FASTAPI and self.use_celery:
            self.use_redis = True
        # Celery requires Redis
        if self.use_celery and not self.use_redis:
            self.use_redis = True

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
        for candidate in ("api", "app"):
            if (backend / candidate).is_dir():
                return candidate
        return "api"

    @property
    def wsgi_app(self) -> str:
        """Return the WSGI or settings module root, without the submodule."""
        if self.is_fastapi_backend:
            return "app"
        backend = self.backend_dir
        for candidate in ("api", "app"):
            if (backend / candidate).is_dir():
                return candidate
        return "api"

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
