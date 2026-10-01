"""Per-backend facts for generated agent instructions and CI workflows.

`mattstack init`, `mattstack rules`, and `mattstack workflow` all describe
the backend stack. They read the facts in this module, so none of them can
tell an agent to use django-ninja or `manage.py` in a FastAPI or NestJS
project.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from mattstack.config import BackendFramework


@dataclass(frozen=True)
class Toolchain:
    """Package managers that the generated instructions must name."""

    python_pm: str = "uv"
    js_pm: str = "bun"

    def python_run(self, command: str) -> str:
        return f"{self.python_pm} run {command}"

    def js_run(self, script: str) -> str:
        return f"{self.js_pm} run {script}"

    def python_alternatives(self) -> str:
        """Return the Python package managers an agent must not use."""
        return _others(("uv", "pip", "poetry", "pipenv", "conda"), self.python_pm)

    def js_alternatives(self) -> str:
        """Return the JavaScript package managers an agent must not use."""
        return _others(("bun", "npm", "yarn", "pnpm"), self.js_pm)


def _others(names: tuple[str, ...], chosen: str) -> str:
    return ", ".join(f"`{name}`" for name in names if name != chosen)


@dataclass(frozen=True)
class BackendFacts:
    """What an agent must know about one backend framework."""

    service: str
    structure: str
    tech: str
    framework: str
    language: str
    is_python: bool
    package_manager: str
    api_rule: str
    migrate: str
    migrate_trigger: str
    dev: str
    test: str
    lint: str
    format: str
    details: tuple[str, ...]
    docs_path: str | None
    env_vars: str
    background: str | None
    # Extra arguments for `uv sync` in CI. FastAPI keeps pytest in the
    # `dev` extra, so a plain sync cannot run the tests.
    ci_sync_args: str = ""
    # FastAPI builds an async SQLAlchemy engine, which needs the asyncpg driver.
    database_scheme: str = "postgresql"
    # The Django boilerplates build DATABASES from DB_NAME, DB_USER,
    # DB_PASSWORD, DB_HOST, and DB_PORT and ignore DATABASE_URL.
    db_env_parts: bool = False


_DJANGO_ENV = "`DATABASE_URL`, `SECRET_KEY`, `REDIS_URL` (if Redis)"


class PythonCommands(TypedDict):
    test: str
    lint: str
    format: str


def _python_tools(tools: Toolchain) -> PythonCommands:
    return {
        "test": tools.python_run("pytest -v"),
        "lint": tools.python_run("ruff check ."),
        "format": tools.python_run("ruff format ."),
    }


def _django(tools: Toolchain, *, flavour: str, api_rule: str, docs: str | None) -> BackendFacts:
    manage = tools.python_run("python manage.py")
    return BackendFacts(
        service="Django API",
        structure=f"Django API ({flavour}, Python 3.12+)",
        tech=f"Python 3.12+, Django, {flavour}, PostgreSQL 17",
        framework=f"Django + {flavour}",
        language="Python 3.12+",
        is_python=True,
        package_manager=tools.python_pm,
        api_rule=api_rule,
        migrate=f"cd backend && {manage} makemigrations && {manage} migrate",
        migrate_trigger="model changes",
        dev=f"cd backend && {manage} runserver",
        details=("Testing: pytest", "Linting: ruff"),
        docs_path=docs,
        env_vars=_DJANGO_ENV,
        background="Celery + Redis",
        db_env_parts=True,
        **_python_tools(tools),
    )


def backend_facts(framework: BackendFramework, tools: Toolchain | None = None) -> BackendFacts:
    """Return the facts for ``framework``, with commands for ``tools``."""
    tools = tools or Toolchain()
    if framework == BackendFramework.DJANGO_NINJA:
        return _django(
            tools,
            flavour="django-ninja",
            api_rule="Backend uses django-ninja (Pydantic models, type-safe). "
            "NEVER use Django REST Framework serializers.",
            docs="/api/docs",
        )
    if framework == BackendFramework.DJANGO_MATT:
        return _django(
            tools,
            flavour="django-matt",
            api_rule="Backend uses django-matt (`DjangoMattAPI` and `APIController` classes "
            "with Pydantic schemas). NEVER use Django REST Framework serializers or "
            "django-ninja routers.",
            docs=None,
        )
    if framework == BackendFramework.FASTAPI:
        alembic = tools.python_run("alembic")
        return BackendFacts(
            service="FastAPI API",
            structure="FastAPI API (SQLAlchemy async, Alembic, Python 3.12+)",
            tech="Python 3.12+, FastAPI, SQLAlchemy (async), Alembic, PostgreSQL 17",
            framework="FastAPI + SQLAlchemy + Alembic",
            language="Python 3.12+",
            is_python=True,
            package_manager=tools.python_pm,
            api_rule="Backend uses FastAPI routers with Pydantic schemas and SQLAlchemy "
            "models. NEVER add Django code.",
            migrate=f'cd backend && {alembic} revision --autogenerate -m "<message>" '
            f"&& {alembic} upgrade head",
            migrate_trigger="model changes",
            dev=f"cd backend && {tools.python_run('uvicorn app.main:app --reload --port 8000')}",
            details=("Testing: pytest", "Linting: ruff", "Migrations: Alembic"),
            docs_path="/docs",
            env_vars=_DJANGO_ENV,
            background="Celery + Redis",
            ci_sync_args=" --extra dev",
            database_scheme="postgresql+asyncpg",
            **_python_tools(tools),
        )
    return BackendFacts(
        service="NestJS API",
        structure="NestJS API (TypeScript, Fastify, Drizzle ORM)",
        tech="TypeScript, NestJS v11, Fastify, Drizzle ORM, PostgreSQL 17",
        framework="NestJS v11 + Fastify",
        language="TypeScript (strict)",
        is_python=False,
        package_manager=tools.js_pm,
        api_rule="Backend uses Drizzle ORM (NOT TypeORM, Prisma, or Sequelize).",
        migrate=f"cd backend && {tools.js_run('db:migrate')}",
        migrate_trigger="schema changes",
        dev=f"cd backend && {tools.js_run('start:dev')}",
        test=tools.js_run("test"),
        lint=tools.js_run("lint"),
        format=tools.js_run("format"),
        details=(
            "ORM: Drizzle ORM",
            "Testing: Jest",
            "Linting/Formatting: Biome",
            "Auth: JWT (access + refresh) + Google/GitHub OAuth + WebAuthn",
        ),
        docs_path="/api/docs",
        env_vars="`DATABASE_URL`, `JWT_SECRET`, `JWT_REFRESH_SECRET`, `REDIS_URL`",
        background="Bull (Redis-based queues)",
    )
