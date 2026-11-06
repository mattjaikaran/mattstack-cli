"""Backend recipes for the generated root justfile."""

from __future__ import annotations

import shlex

from mattstack.config import BackendFramework, ProjectConfig
from mattstack.runtime_profiles import (
    REALTIME_PROFILE,
    backend_sync_args,
    task_backend_extra,
    task_processes,
    task_profile,
    uv_run,
)


def backend_install(config: ProjectConfig) -> str:
    """Request the dev extra only when the backend declares it."""
    if config.is_nestjs_backend:
        return "bun install"
    try:
        return shlex.join(backend_sync_args(config, config.backend_dir))
    except (OSError, ValueError):
        task_extra = task_backend_extra(config)
        return f"uv sync --extra {task_extra}" if task_extra else "uv sync"


def quality_run(config: ProjectConfig) -> str:
    """Use Ninja's dev extra so pytest/ruff are the locked versions."""
    dev = config.backend_framework == BackendFramework.DJANGO_NINJA
    return "uv run --extra dev" if dev else "uv run"


def backend_test(config: ProjectConfig) -> str:
    if config.is_nestjs_backend:
        return "cd backend && bun run test"
    return f"cd backend && {quality_run(config)} pytest -v"


def backend_lint(config: ProjectConfig) -> str:
    if config.is_nestjs_backend:
        return "cd backend && bun run lint"
    run = quality_run(config)
    return f"cd backend && {run} ruff check . && {run} ruff format --check ."


def _task_recipes(config: ProjectConfig) -> str:
    lines: list[str] = []
    for process in task_processes(config, production=False):
        target = "backend-beat" if process.role == "scheduler" else "backend-worker"
        lines += [
            "",
            f"# Run {process.service} (TASK_BACKEND={config.task_backend.value})",
            f"{target}:",
            f"    cd backend && {uv_run(config)} {process.command}",
        ]
    return "\n" + "\n".join(lines) if lines else ""


def backend_recipes(config: ProjectConfig) -> str:
    """Return the backend host recipes plus the uv-only tooling recipes."""
    if config.is_nestjs_backend:
        body = _nestjs_recipes(config)
    elif config.is_fastapi_backend:
        body = _fastapi_recipes(config)
    else:
        body = _django_recipes(config)
    tooling = _tooling_recipes(config) if config.is_ninja_backend else ""
    return body + ("\n" + tooling if tooling else "")


def _django_recipes(config: ProjectConfig) -> str:
    port, run = config.backend_api_port, quality_run(config)
    return f"""\
# Install backend deps
backend-setup:
    cd backend && {backend_install(config)}

# Run Django dev server on API_PORT
backend-dev:
    cd backend && {uv_run(config)} python manage.py runserver "${{API_PORT:-{port}}}"

# Run backend tests
backend-test:
    cd backend && {run} pytest -v

# Lint backend
backend-lint:
    cd backend && {run} ruff check . && {run} ruff format --check .

# Run Django migrations on the host
backend-migrate:
    cd backend && uv run python manage.py migrate

# Create Django migrations
backend-makemigrations:
    cd backend && uv run python manage.py makemigrations

# Open the Django shell
backend-shell:
    cd backend && uv run python manage.py shell{_task_recipes(config)}"""


def _fastapi_recipes(config: ProjectConfig) -> str:
    port, run = config.backend_api_port, uv_run(config)
    return f"""\
# Install backend deps
backend-setup:
    cd backend && {backend_install(config)}

# Run FastAPI dev server on API_PORT
backend-dev:
    cd backend && {run} uvicorn app.main:app --host 127.0.0.1 \\
        --port "${{API_PORT:-{port}}}" --reload

# Run backend tests (pytest)
backend-test:
    cd backend && {run} pytest -v

# Lint backend (ruff)
backend-lint:
    cd backend && {run} ruff check . && {run} ruff format --check .

# Run Alembic migrations on the host
backend-migrate:
    cd backend && uv run alembic upgrade head

# Create a new Alembic migration
backend-makemigrations message="migration":
    cd backend && uv run alembic revision --autogenerate -m "{{{{ message }}}}"

# Open a Python shell
backend-shell:
    cd backend && uv run python{_task_recipes(config)}"""


def _nestjs_recipes(config: ProjectConfig) -> str:
    return f"""\
# Install backend deps
backend-setup:
    cd backend && bun install

# Run NestJS dev server on API_PORT
backend-dev:
    cd backend && bun run start:dev

# Build NestJS for production
backend-build:
    cd backend && bun run build

# Run backend tests (Jest)
backend-test:
    cd backend && bun run test

# Lint backend (Biome)
backend-lint:
    cd backend && bun run lint

# Run Drizzle migrations
backend-migrate:
    cd backend && bun run db:migrate

# Seed the database
backend-seed:
    cd backend && bun run db:seed{_task_recipes(config)}"""


def _tooling_recipes(config: ProjectConfig) -> str:
    settings = f"{config.django_package}.settings.test"
    return f"""\

# Type-check the backend
backend-typecheck:
    cd backend && uv run --extra dev mypy .

# Run every backend gauntlet gate
backend-gauntlet:
    cd backend && uv run --extra dev python scripts/gauntlet.py --verbose

# Run the backend quick gauntlet (skips audit and docker)
backend-gauntlet-quick:
    cd backend && uv run --extra dev python scripts/gauntlet.py --quick --verbose

# Export the OpenAPI contract to backend/docs/openapi/openapi.json
backend-openapi:
    cd backend && DJANGO_SETTINGS_MODULE={settings} SECRET_KEY=openapi-export-not-a-secret \\
        uv run python manage.py export_openapi

# Fail if the committed OpenAPI contract is stale, then check schema parity
backend-openapi-check:
    cd backend && DJANGO_SETTINGS_MODULE={settings} SECRET_KEY=openapi-export-not-a-secret \\
        uv run python manage.py export_openapi --check
    cd backend && uv run python scripts/check_schema_parity.py

# Audit every locked backend package with pip-audit
backend-audit:
    cd backend && uv run --extra dev python scripts/audit_dependencies.py

# Run the backend security scan (bandit)
backend-security-scan:
    cd backend && uv run --extra dev bandit -c pyproject.toml -r .

# Check backend code conventions
backend-check-conventions:
    cd backend && uv run python scripts/check_conventions.py"""


def profile_args(config: ProjectConfig) -> str:
    profiles = [task_profile(config), REALTIME_PROFILE if config.use_realtime else None]
    return "".join(f" --profile {profile}" for profile in profiles if profile)


def _migrate_command(config: ProjectConfig) -> str:
    if config.is_nestjs_backend:
        return "bun run db:migrate"
    if config.is_fastapi_backend:
        return "alembic upgrade head"
    return "python manage.py migrate"


def _superuser_recipes(config: ProjectConfig) -> str:
    if config.is_ninja_backend:
        check = (
            "    @for v in SUPERUSER_EMAIL SUPERUSER_USERNAME SUPERUSER_PASSWORD "
            'SUPERUSER_FIRST_NAME SUPERUSER_LAST_NAME; do test -n "${!v:-}" || '
            '{ echo "$v is unset. Set all SUPERUSER_* in the root .env (see .env.example)." '
            ">&2; exit 1; }; done\n"
        )
        envs = (
            "-e SUPERUSER_EMAIL -e SUPERUSER_USERNAME -e SUPERUSER_PASSWORD "
            "-e SUPERUSER_FIRST_NAME -e SUPERUSER_LAST_NAME "
        )
        container = (
            f"{check}    docker compose exec {envs}api-dev python manage.py create_superuser\n"
        )
        host = f"{check}    cd backend && uv run python manage.py create_superuser"
    else:
        container = "    docker compose exec api-dev python manage.py createsuperuser"
        host = "    cd backend && uv run python manage.py createsuperuser"
    return f"""\

# Create the Django superuser in the api-dev container
[no-exit-message]
superuser:
{container}

# Create the Django superuser on the host
[no-exit-message]
superuser-host:
{host}

alias backend-superuser := superuser"""


def container_recipes(config: ProjectConfig) -> str:
    """Container-bound recipes against the monorepo's ``api-dev`` service."""
    superuser = _superuser_recipes(config) if config.is_django_backend else ""
    scheduler = next(
        (
            process.service
            for process in task_processes(config, production=False)
            if process.role == "scheduler"
        ),
        None,
    )
    restart = f"\n    docker compose restart {scheduler}" if scheduler else ""
    bootstrap_superuser = "\n    just superuser" if config.is_django_backend else ""
    migrate = _migrate_command(config)
    return f"""\

# Run migrations in the api-dev container
migrate:
    docker compose exec -T api-dev {migrate}

# Start the stack, migrate, and create the superuser from .env
bootstrap:
    docker compose{profile_args(config)} up -d --wait
    docker compose exec -T api-dev {migrate}{restart}{bootstrap_superuser}{superuser}"""
