"""Root Makefile template for generated projects."""

from __future__ import annotations

import json
import tomllib

from mattstack.config import BackendFramework, ProjectConfig
from mattstack.runtime_profiles import (
    REALTIME_PROFILE,
    task_backend_extra,
    task_processes,
    task_profile,
    uv_run,
)
from mattstack.templates.frontend_commands import frontend_commands
from mattstack.templates.frontend_runtime import FRONTEND_PORT

_PROD = "docker compose -f docker-compose.prod.yml --env-file .env.production"


def generate_makefile(config: ProjectConfig) -> str:
    """Generate root Makefile content."""
    sections = [_header(), _help_target()]

    if config.is_fullstack:
        sections.append(_setup_fullstack(config))
        sections.append(_docker_targets(config))
        sections.append(_backend_targets(config))
        sections.append(_frontend_targets(config))
        if config.include_ios:
            sections.append(_ios_targets(config))
        sections.append(_combined_targets(config))
        sections.append(_prod_targets())
    elif config.has_backend:
        sections.append(_setup_backend(config))
        sections.append(_docker_targets(config))
        sections.append(_backend_targets(config))
        sections.append(_prod_targets())
    elif config.has_frontend:
        sections.append(_setup_frontend(config))
        sections.append(_frontend_targets(config))

    return "\n".join(sections)


def _header() -> str:
    return """\
.DEFAULT_GOAL := help
SHELL := /bin/bash

# Host commands need the same settings the containers get. Do not use
# `include .env`: make treats # as a comment and $ as a variable, and a
# generated secret key can contain both, so a secret would silently
# truncate on the host while the container kept the full value. Source the
# file in the recipe shell instead.
LOAD_ENV := set -a && . ./.env && set +a &&"""


def _help_target() -> str:
    # Long awk line is required for Makefile help target
    grep_cmd = (
        "@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort"
        ' | awk \'BEGIN {FS = ":.*?## "}; '
        '{printf "\\033[36m%-20s\\033[0m %s\\n", $$1, $$2}\''
    )
    return f"""
.PHONY: help
help: ## Show this help
\t{grep_cmd}"""


def _backend_install(config: ProjectConfig) -> str:
    """Return the backend install command; request the dev extra only if it exists.

    `uv sync --extra dev` fails when the backend declares no `dev` extra. A
    `dev` dependency group needs no flag: `uv sync` installs it by default.
    """
    if config.is_nestjs_backend:
        return "bun install"
    task_extra = task_backend_extra(config)
    command = f"uv sync --extra {task_extra}" if task_extra else "uv sync"
    pyproject = config.backend_dir / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return command
    extras = data.get("project", {}).get("optional-dependencies", {})
    return f"{command} --extra dev" if "dev" in extras else command


def _setup_fullstack(config: ProjectConfig) -> str:
    ios_setup = "\n\t@echo 'iOS setup: open ios/ in Xcode'" if config.include_ios else ""
    return f"""
.PHONY: setup
setup: ## Install all dependencies and refresh lockfiles
\t@echo 'Setting up backend...'
\tcd backend && {_backend_install(config)}
\t@echo 'Setting up frontend...'
\tcd frontend && bun install{ios_setup}
\t@echo 'Copying .env.example to .env (if needed)...'
\t@test -f .env || cp .env.example .env
\t@echo 'Setup complete!'"""


def _setup_backend(config: ProjectConfig) -> str:
    return f"""
.PHONY: setup
setup: ## Install backend dependencies
\t@echo 'Setting up backend...'
\tcd backend && {_backend_install(config)}
\t@test -f .env || cp .env.example .env
\t@echo 'Setup complete!'"""


def _setup_frontend(config: ProjectConfig) -> str:
    return """
.PHONY: setup
setup: ## Install frontend dependencies and refresh the lockfile
\t@echo 'Setting up frontend...'
\tcd frontend && bun install
\t@echo 'Setup complete!'"""


def _docker_targets(config: ProjectConfig) -> str:
    profiles = [task_profile(config), REALTIME_PROFILE if config.use_realtime else None]
    targets = "".join(
        f"\n\nup-{profile}: ## Start all services + the {profile} profile"
        f"\n\tdocker compose --profile {profile} up -d"
        for profile in profiles
        if profile
    )
    phony = " ".join(f"up-{profile}" for profile in profiles if profile)
    return f"""
.PHONY: up {phony} down logs restart
up: ## Start all services (Docker)
\tdocker compose up -d{targets}

down: ## Stop all services
\tdocker compose down

logs: ## Tail service logs
\tdocker compose logs -f

restart: ## Restart all services
\tdocker compose restart"""


def _task_targets(config: ProjectConfig) -> str:
    """Host targets for the queue's consumers; .PHONY only names emitted recipes."""
    lines: list[str] = []
    for process in task_processes(config, production=False):
        target = "backend-beat" if process.role == "scheduler" else "backend-worker"
        lines.append(
            f"\n\n.PHONY: {target}"
            f"\n{target}: ## Run {process.service} (TASK_BACKEND={config.task_backend.value})"
            f"\n\t$(LOAD_ENV) cd backend && {uv_run(config)} {process.command}"
        )
    return "".join(lines)


def _backend_targets(config: ProjectConfig) -> str:
    if config.is_nestjs_backend:
        return _nestjs_backend_targets(config)
    if config.is_fastapi_backend:
        return _fastapi_backend_targets(config)
    return _django_backend_targets(config)


def _quality_run(config: ProjectConfig) -> str:
    """Return ``uv run`` with Ninja's ``dev`` extra, so pytest/ruff are the locked ones."""
    dev = config.backend_framework == BackendFramework.DJANGO_NINJA
    return "uv run --extra dev" if dev else "uv run"


def _django_backend_targets(config: ProjectConfig) -> str:
    port = config.backend_api_port
    return f"""
.PHONY: backend-setup backend-dev backend-test backend-lint
.PHONY: backend-migrate backend-shell backend-makemigrations backend-superuser
backend-setup: ## Install backend deps
\tcd backend && {_backend_install(config)}

backend-dev: ## Run Django dev server on API_PORT
\t$(LOAD_ENV) cd backend && {uv_run(config)} python manage.py runserver "$${{API_PORT:-{port}}}"

backend-test: ## Run backend tests
\t$(LOAD_ENV) cd backend && {_quality_run(config)} pytest -v

backend-lint: ## Lint backend
\tcd backend && {_quality_run(config)} ruff check .

backend-migrate: ## Run Django migrations
\t$(LOAD_ENV) cd backend && uv run python manage.py migrate

backend-makemigrations: ## Create Django migrations
\t$(LOAD_ENV) cd backend && uv run python manage.py makemigrations

backend-shell: ## Django shell
\t$(LOAD_ENV) cd backend && uv run python manage.py shell

backend-superuser: ## Create Django superuser
\t$(LOAD_ENV) cd backend && uv run python manage.py createsuperuser{_task_targets(config)}"""


def _fastapi_backend_targets(config: ProjectConfig) -> str:
    port = config.backend_api_port
    return f"""
.PHONY: backend-setup backend-dev backend-test backend-lint
.PHONY: backend-migrate backend-shell
backend-setup: ## Install backend deps
\tcd backend && {_backend_install(config)}

backend-dev: ## Run FastAPI dev server on API_PORT
\t$(LOAD_ENV) cd backend && uv run uvicorn app.main:app --host 127.0.0.1 \\
\t\t--port "$${{API_PORT:-{port}}}" --reload

backend-test: ## Run backend tests (pytest)
\t$(LOAD_ENV) cd backend && uv run pytest -v

backend-lint: ## Lint backend (ruff)
\tcd backend && uv run ruff check .

backend-migrate: ## Run Alembic migrations
\t$(LOAD_ENV) cd backend && uv run alembic upgrade head

backend-makemigrations: ## Create a new Alembic migration
\t$(LOAD_ENV) cd backend && uv run alembic revision --autogenerate -m "$(MSG)"

backend-shell: ## Open Python shell
\t$(LOAD_ENV) cd backend && uv run python{_task_targets(config)}"""


def _nestjs_backend_targets(config: ProjectConfig) -> str:
    return """
.PHONY: backend-setup backend-dev backend-build backend-test backend-test-cov backend-lint
.PHONY: backend-migrate backend-seed backend-studio
backend-setup: ## Install backend deps
\tcd backend && bun install

backend-dev: ## Run NestJS dev server on API_PORT
\t$(LOAD_ENV) cd backend && bun run start:dev

backend-build: ## Build NestJS for production
\tcd backend && bun run build

backend-test: ## Run backend tests (Jest)
\t$(LOAD_ENV) cd backend && bun run test

backend-test-cov: ## Run tests with coverage
\t$(LOAD_ENV) cd backend && bun run test:cov

backend-lint: ## Lint backend (Biome)
\tcd backend && bun run lint

backend-migrate: ## Run Drizzle migrations
\t$(LOAD_ENV) cd backend && bun run db:migrate

backend-seed: ## Seed the database
\t$(LOAD_ENV) cd backend && bun run db:seed

backend-studio: ## Open Drizzle Studio
\t$(LOAD_ENV) cd backend && bun run db:studio"""


def _frontend_scripts(config: ProjectConfig) -> set[str] | None:
    """Return the frontend's npm script names, or None when unknown."""
    try:
        data = json.loads((config.frontend_dir / "package.json").read_text())
    except (OSError, ValueError):
        return None
    scripts = data.get("scripts")
    return set(scripts) if isinstance(scripts, dict) else set()


def _resolved(config: ProjectConfig, command: str | None) -> str | None:
    """Drop a `bun run <script>` command whose script the frontend lacks."""
    if command is None or not command.startswith("bun run "):
        return command
    scripts = _frontend_scripts(config)
    script = command.removeprefix("bun run ").split()[0]
    return command if scripts is None or script in scripts else None


def _frontend_recipe(command: str | None, job: str) -> str:
    """Run the command, or fail: a missing check must not report success."""
    if command:
        return f"\tcd frontend && {command}"
    return f"\t@echo 'frontend/package.json defines no {job} script' >&2; exit 1"


def _frontend_targets(config: ProjectConfig) -> str:
    cmds = frontend_commands(config)
    test = _resolved(config, cmds.test)
    typecheck = _resolved(config, cmds.typecheck)
    # The root .env carries API_PORT and FRONTEND_PORT for the dev proxy.
    load_env = "$(LOAD_ENV) " if config.has_backend else ""
    dev = "bun run dev"
    if config.is_nextjs:
        # Next.js reads PORT, which a NestJS backend sets in the root .env.
        dev = f'bun run dev -p "$${{FRONTEND_PORT:-{FRONTEND_PORT}}}"'
    return f"""
.PHONY: frontend-setup frontend-dev frontend-build frontend-test frontend-lint frontend-typecheck
frontend-setup: ## Install frontend deps
\tcd frontend && bun install

frontend-dev: ## Run frontend dev server
\t{load_env}cd frontend && {dev}

frontend-build: ## Build frontend with the root .env browser API settings
\t{load_env}cd frontend && bun run build

frontend-test: ## Run frontend tests
{_frontend_recipe(test, "test")}

frontend-typecheck: ## Type-check frontend
{_frontend_recipe(typecheck, "type-check")}

frontend-lint: ## Lint frontend
\tcd frontend && {cmds.lint}"""


def _ios_targets(config: ProjectConfig) -> str:
    scheme = config.display_name.replace(" ", "")
    return f"""
.PHONY: ios-build ios-test
ios-build: ## Build iOS project
\tcd ios && xcodebuild -scheme {scheme} -sdk iphonesimulator build

ios-test: ## Run iOS tests
\tcd ios && xcodebuild -scheme {scheme} -sdk iphonesimulator test"""


def _combined_targets(config: ProjectConfig) -> str:
    cmds = frontend_commands(config)
    frontend_format = cmds.format or "echo 'No frontend format script'"
    if config.is_nestjs_backend:
        backend = {
            "test": "$(LOAD_ENV) cd backend && bun run test",
            "lint": "cd backend && bun run lint",
            "format": "cd backend && bun run format",
        }
    else:
        run = _quality_run(config)
        backend = {
            "test": f"$(LOAD_ENV) cd backend && {run} pytest -v",
            "lint": f"cd backend && {run} ruff check . && {run} ruff format --check .",
            "format": f"cd backend && {run} ruff format .",
        }
    sync_types = (
        ""
        if config.is_nestjs_backend
        else """

sync-types: ## Sync backend types to frontend TypeScript
\tmattstack sync types"""
    )
    return f"""
.PHONY: test lint typecheck format sync-types gauntlet clean clean-volumes
test: ## Run backend tests and the frontend test suite
\t@echo 'Running backend tests...'
\t{backend["test"]}
\t@echo 'Running frontend tests...'
\t$(MAKE) frontend-test

lint: ## Lint all code
\t{backend["lint"]}
\tcd frontend && {cmds.lint}

typecheck: ## Type-check the frontend
\t$(MAKE) frontend-typecheck

format: ## Format all code
\t{backend["format"]}
\tcd frontend && {frontend_format}{sync_types}

gauntlet: ## Run the verification gate (read-only)
\tmattstack audit --no-todo

clean: ## Remove build artifacts; keeps containers' data volumes
\tdocker compose down
\trm -rf backend/.pytest_cache backend/__pycache__ backend/dist
\trm -rf frontend/node_modules frontend/dist

clean-volumes: ## DESTRUCTIVE: delete the database and Redis volumes (CONFIRM=1)
\t@test "$(CONFIRM)" = 1 || {{ echo 'Deletes local data. Rerun with CONFIRM=1' >&2; exit 1; }}
\tdocker compose down -v"""


def _prod_targets() -> str:
    return f"""
.PHONY: prod-build prod-up prod-down
prod-build: ## Build production images (uses .env.production)
\t{_PROD} build

prod-up: ## Start production (uses .env.production)
\t{_PROD} up -d --build

prod-down: ## Stop production
\t{_PROD} down"""
