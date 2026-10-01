"""Preset configurations for common project types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from mattstack.config import (
    BackendFramework,
    FrontendFramework,
    ProjectConfig,
    ProjectType,
    TaskBackend,
    Variant,
)
from mattstack.utils.console import print_warning

# NestJS is a Node.js/TypeScript backend — no Celery (uses Bull queues internally)


@dataclass
class Preset:
    """A named preset configuration."""

    name: str
    description: str
    project_type: ProjectType
    variant: Variant
    frontend_framework: FrontendFramework = FrontendFramework.REACT_VITE
    backend_framework: BackendFramework = BackendFramework.DJANGO_NINJA
    include_ios: bool = False
    # Legacy switch: True keeps the backend's default queue, False disables it.
    use_celery: bool = True
    # An explicit backend wins over ``use_celery``.
    task_backend: TaskBackend | None = None
    use_realtime: bool = False

    def to_config(self, project_name: str, path: Path) -> ProjectConfig:
        legacy = TaskBackend.CELERY if self.use_celery else TaskBackend.NONE
        return ProjectConfig(
            name=project_name,
            path=path,
            project_type=self.project_type,
            variant=self.variant,
            frontend_framework=self.frontend_framework,
            backend_framework=self.backend_framework,
            include_ios=self.include_ios,
            task_backend=self.task_backend or legacy,
            use_realtime=self.use_realtime,
        )


# B2B presets name their frontend source and router explicitly. They clone
# react-vite-boilerplate (TanStack Router), the same source as the starter
# presets; the B2B variant adds backend org/team/RBAC features only. The
# react-vite-b2b boilerplate (React Router, org switcher UI) is not a mattstack
# source because no backend serves its contract: it reads `access_token` and
# `refresh_token` and expects GET /organizations to return a bare array plus
# /teams and /invitations routes. django-ninja issues `token`/`refresh`, NestJS
# issues `accessToken` without a teams route, FastAPI returns a paginated
# `items` list without teams or invitations, and django-matt has no orgs.
# Never swap a preset's or user's router by variant.
PRESETS: dict[str, Preset] = {
    "starter-fullstack": Preset(
        name="starter-fullstack",
        description="Standard fullstack monorepo (Django + React Vite TanStack)",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
    ),
    "b2b-fullstack": Preset(
        name="b2b-fullstack",
        description=("B2B fullstack with orgs/teams/roles (Django + React Vite + TanStack Router)"),
        project_type=ProjectType.FULLSTACK,
        variant=Variant.B2B,
        frontend_framework=FrontendFramework.REACT_VITE,
    ),
    "starter-api": Preset(
        name="starter-api",
        description="Django API only (no frontend)",
        project_type=ProjectType.BACKEND_ONLY,
        variant=Variant.STARTER,
    ),
    "b2b-api": Preset(
        name="b2b-api",
        description="B2B Django API with orgs/teams/roles",
        project_type=ProjectType.BACKEND_ONLY,
        variant=Variant.B2B,
    ),
    "starter-frontend": Preset(
        name="starter-frontend",
        description="React Vite SPA with TanStack Router",
        project_type=ProjectType.FRONTEND_ONLY,
        variant=Variant.STARTER,
        use_celery=False,
    ),
    "simple-frontend": Preset(
        name="simple-frontend",
        description="Simpler React Vite SPA with React Router",
        project_type=ProjectType.FRONTEND_ONLY,
        variant=Variant.STARTER,
        frontend_framework=FrontendFramework.REACT_VITE_STARTER,
        use_celery=False,
    ),
    "rsbuild-fullstack": Preset(
        name="rsbuild-fullstack",
        description="Fullstack monorepo (Django API + React Rsbuild)",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        frontend_framework=FrontendFramework.REACT_RSBUILD,
    ),
    "rsbuild-frontend": Preset(
        name="rsbuild-frontend",
        description="React Rsbuild SPA with TanStack Router",
        project_type=ProjectType.FRONTEND_ONLY,
        variant=Variant.STARTER,
        frontend_framework=FrontendFramework.REACT_RSBUILD,
        use_celery=False,
    ),
    "kibo-fullstack": Preset(
        name="kibo-fullstack",
        description="Fullstack monorepo (Django API + React Rsbuild + Kibo UI)",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        frontend_framework=FrontendFramework.REACT_RSBUILD_KIBO,
    ),
    "kibo-frontend": Preset(
        name="kibo-frontend",
        description="React Rsbuild + Kibo UI SPA (dashboards, kanban, calendars)",
        project_type=ProjectType.FRONTEND_ONLY,
        variant=Variant.STARTER,
        frontend_framework=FrontendFramework.REACT_RSBUILD_KIBO,
        use_celery=False,
    ),
    "nextjs-fullstack": Preset(
        name="nextjs-fullstack",
        description="Fullstack monorepo (Django API + Next.js App Router)",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        frontend_framework=FrontendFramework.NEXTJS,
    ),
    "nextjs-frontend": Preset(
        name="nextjs-frontend",
        description="Next.js standalone (App Router, TypeScript, Tailwind)",
        project_type=ProjectType.FRONTEND_ONLY,
        variant=Variant.STARTER,
        frontend_framework=FrontendFramework.NEXTJS,
        use_celery=False,
    ),
    "matt-api": Preset(
        name="matt-api",
        description="django-matt API only (MattAPI controllers, CRUDService, Postgres)",
        project_type=ProjectType.BACKEND_ONLY,
        variant=Variant.STARTER,
        backend_framework=BackendFramework.DJANGO_MATT,
    ),
    "matt-fullstack": Preset(
        name="matt-fullstack",
        description="Fullstack monorepo (django-matt + React Vite)",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        backend_framework=BackendFramework.DJANGO_MATT,
    ),
    "matt-b2b-fullstack": Preset(
        name="matt-b2b-fullstack",
        description=(
            "B2B fullstack monorepo (django-matt + React Vite + TanStack Router, orgs/teams/roles)"
        ),
        project_type=ProjectType.FULLSTACK,
        variant=Variant.B2B,
        backend_framework=BackendFramework.DJANGO_MATT,
        frontend_framework=FrontendFramework.REACT_VITE,
    ),
    # FastAPI (Python/async) presets
    "fastapi-api": Preset(
        name="fastapi-api",
        description="FastAPI API only (SQLAlchemy + Alembic + Celery + Redis)",
        project_type=ProjectType.BACKEND_ONLY,
        variant=Variant.STARTER,
        backend_framework=BackendFramework.FASTAPI,
    ),
    "fastapi-fullstack": Preset(
        name="fastapi-fullstack",
        description="Fullstack monorepo (FastAPI + React Vite + TanStack Router)",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        backend_framework=BackendFramework.FASTAPI,
        frontend_framework=FrontendFramework.REACT_VITE,
    ),
    "fastapi-b2b-fullstack": Preset(
        name="fastapi-b2b-fullstack",
        description=(
            "B2B fullstack monorepo (FastAPI + React Vite + TanStack Router, orgs/teams/roles)"
        ),
        project_type=ProjectType.FULLSTACK,
        variant=Variant.B2B,
        backend_framework=BackendFramework.FASTAPI,
        frontend_framework=FrontendFramework.REACT_VITE,
    ),
    "fastapi-rsbuild-fullstack": Preset(
        name="fastapi-rsbuild-fullstack",
        description="Fullstack monorepo (FastAPI + React Rsbuild + TanStack Router)",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        backend_framework=BackendFramework.FASTAPI,
        frontend_framework=FrontendFramework.REACT_RSBUILD,
    ),
    "fastapi-nextjs-fullstack": Preset(
        name="fastapi-nextjs-fullstack",
        description="Fullstack monorepo (FastAPI + Next.js App Router)",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        backend_framework=BackendFramework.FASTAPI,
        frontend_framework=FrontendFramework.NEXTJS,
    ),
    # NestJS (Node.js/TypeScript) presets
    "nestjs-api": Preset(
        name="nestjs-api",
        description="NestJS API only (Fastify + Drizzle ORM + JWT/OAuth + Redis)",
        project_type=ProjectType.BACKEND_ONLY,
        variant=Variant.STARTER,
        backend_framework=BackendFramework.NESTJS,
        use_celery=False,
    ),
    "nestjs-fullstack": Preset(
        name="nestjs-fullstack",
        description="Fullstack monorepo (NestJS API + React Vite + TanStack Router)",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        backend_framework=BackendFramework.NESTJS,
        frontend_framework=FrontendFramework.REACT_VITE,
        use_celery=False,
    ),
    "nestjs-rsbuild-fullstack": Preset(
        name="nestjs-rsbuild-fullstack",
        description="Fullstack monorepo (NestJS API + React Rsbuild + TanStack Router)",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        backend_framework=BackendFramework.NESTJS,
        frontend_framework=FrontendFramework.REACT_RSBUILD,
        use_celery=False,
    ),
    "nestjs-nextjs-fullstack": Preset(
        name="nestjs-nextjs-fullstack",
        description="Fullstack monorepo (NestJS API + Next.js App Router)",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        backend_framework=BackendFramework.NESTJS,
        frontend_framework=FrontendFramework.NEXTJS,
        use_celery=False,
    ),
    # django-matt example app presets (blog, portfolio, ecommerce)
    "matt-blog": Preset(
        name="matt-blog",
        description="Blog fullstack (django-matt + React Vite): posts, comments, tags, RSS",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        backend_framework=BackendFramework.DJANGO_MATT,
        frontend_framework=FrontendFramework.REACT_VITE,
    ),
    "matt-portfolio": Preset(
        name="matt-portfolio",
        description="Portfolio fullstack (django-matt + React Vite): projects, skills, experience",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        backend_framework=BackendFramework.DJANGO_MATT,
        frontend_framework=FrontendFramework.REACT_VITE,
    ),
    "matt-ecommerce": Preset(
        name="matt-ecommerce",
        description="Ecommerce fullstack (django-matt + React Vite): products, cart, Stripe",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        backend_framework=BackendFramework.DJANGO_MATT,
        frontend_framework=FrontendFramework.REACT_VITE,
    ),
}


def get_preset(name: str) -> Preset | None:
    return PRESETS.get(name)


def list_presets() -> list[Preset]:
    return list(PRESETS.values())


def _choice(enum_type: type[StrEnum], data: dict[str, object], key: str, default: str) -> Any:
    value = data.get(key, default)
    try:
        if not isinstance(value, str):
            raise ValueError
        return enum_type(value)
    except ValueError:
        valid = ", ".join(item.value for item in enum_type)
        raise ValueError(f"{key}: '{value}' is invalid. Valid: {valid}") from None


def _flag(data: dict[str, object], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key}: '{value}' is invalid. Use true or false")
    return value


def _user_preset(name: str, data: dict[str, object]) -> Preset:
    """Build a user preset; raise ValueError naming the invalid field."""
    raw_backend = data.get("task_backend")
    preset = Preset(
        name=name,
        description=str(data.get("description", f"Custom preset: {name}")),
        project_type=_choice(ProjectType, data, "project_type", "fullstack"),
        variant=_choice(Variant, data, "variant", "starter"),
        frontend_framework=_choice(FrontendFramework, data, "frontend_framework", "react-vite"),
        backend_framework=_choice(BackendFramework, data, "backend_framework", "django-ninja"),
        include_ios=_flag(data, "include_ios", False),
        use_celery=_flag(data, "use_celery", True),
        task_backend=(
            None if raw_backend is None else _choice(TaskBackend, data, "task_backend", "")
        ),
        use_realtime=_flag(data, "use_realtime", False),
    )
    preset.to_config(name, Path(name))  # Reject unsupported combinations now.
    return preset


def get_all_presets() -> dict[str, Preset]:
    """Get all presets including user-defined ones; warn about invalid ones."""
    from mattstack.user_config import USER_CONFIG_PATH, get_user_presets

    all_presets = dict(PRESETS)
    for name, data in get_user_presets().items():
        if not isinstance(data, dict):
            print_warning(f"Skipped user preset '{name}' in {USER_CONFIG_PATH}: not a mapping")
            continue
        try:
            all_presets[name] = _user_preset(name, data)
        except ValueError as error:
            print_warning(
                f"Skipped user preset '{name}' in {USER_CONFIG_PATH}: {error}. "
                f"Fix the preset, then run: mattstack info"
            )
    return all_presets
