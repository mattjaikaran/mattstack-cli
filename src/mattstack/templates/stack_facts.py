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

    structure: str
    framework: str
    language: str
    is_python: bool
    package_manager: str
    api_rule: str
    test: str
    lint: str
    # Extra arguments for `uv sync` in CI. FastAPI keeps pytest in the
    # `dev` extra, so a plain sync cannot run the tests.
    ci_sync_args: str = ""
    # FastAPI builds an async SQLAlchemy engine, which needs the asyncpg driver.
    database_scheme: str = "postgresql"
    # The Django boilerplates build DATABASES from DB_NAME, DB_USER,
    # DB_PASSWORD, DB_HOST, and DB_PORT and ignore DATABASE_URL.
    db_env_parts: bool = False


class PythonCommands(TypedDict):
    test: str
    lint: str


def _python_tools(tools: Toolchain) -> PythonCommands:
    return {
        "test": tools.python_run("pytest -v"),
        "lint": tools.python_run("ruff check ."),
    }


def _django(tools: Toolchain, *, flavour: str, api_rule: str) -> BackendFacts:
    return BackendFacts(
        structure=f"Django API ({flavour}, Python 3.12+)",
        framework=f"Django + {flavour}",
        language="Python 3.12+",
        is_python=True,
        package_manager=tools.python_pm,
        api_rule=api_rule,
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
        )
    if framework == BackendFramework.DJANGO_MATT:
        return _django(
            tools,
            flavour="django-matt",
            api_rule="Backend uses django-matt (`DjangoMattAPI` and `APIController` classes "
            "with Pydantic schemas). NEVER use Django REST Framework serializers or "
            "django-ninja routers.",
        )
    if framework == BackendFramework.FASTAPI:
        return BackendFacts(
            structure="FastAPI API (SQLAlchemy async, Alembic, Python 3.12+)",
            framework="FastAPI + SQLAlchemy + Alembic",
            language="Python 3.12+",
            is_python=True,
            package_manager=tools.python_pm,
            api_rule="Backend uses FastAPI routers with Pydantic schemas and SQLAlchemy "
            "models. NEVER add Django code.",
            ci_sync_args=" --extra dev",
            database_scheme="postgresql+asyncpg",
            **_python_tools(tools),
        )
    return BackendFacts(
        structure="NestJS API (TypeScript, Fastify, Drizzle ORM)",
        framework="NestJS v11 + Fastify",
        language="TypeScript (strict)",
        is_python=False,
        package_manager=tools.js_pm,
        api_rule="Backend uses Drizzle ORM (NOT TypeORM, Prisma, or Sequelize).",
        test=tools.js_run("test"),
        lint=tools.js_run("lint"),
    )
