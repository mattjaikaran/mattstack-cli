"""Root Makefile template for generated projects."""

from __future__ import annotations

from mattstack.config import ProjectConfig
from mattstack.templates.frontend_commands import frontend_commands


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

# Load the root .env so host commands such as `make backend-migrate` see the
# same settings the containers get. Django reads DB_* and it looks for .env
# next to manage.py, which does not exist in a monorepo.
ifneq (,$(wildcard ./.env))
include .env
export
endif"""


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


def _setup_fullstack(config: ProjectConfig) -> str:
    ios_setup = "\n\t@echo 'iOS setup: open ios/ in Xcode'" if config.include_ios else ""
    backend_install = "bun install" if config.is_nestjs_backend else "uv sync --extra dev"
    return f"""
.PHONY: setup
setup: ## Install all dependencies
\t@echo 'Setting up backend...'
\tcd backend && {backend_install}
\t@echo 'Setting up frontend...'
\tcd frontend && bun install{ios_setup}
\t@echo 'Copying .env.example to .env (if needed)...'
\t@test -f .env || cp .env.example .env
\t@echo 'Setup complete!'"""


def _setup_backend(config: ProjectConfig) -> str:
    install_cmd = "bun install" if config.is_nestjs_backend else "uv sync --extra dev"
    return f"""
.PHONY: setup
setup: ## Install backend dependencies
\t@echo 'Setting up backend...'
\tcd backend && {install_cmd}
\t@test -f .env || cp .env.example .env
\t@echo 'Setup complete!'"""


def _setup_frontend(config: ProjectConfig) -> str:
    install_cmd = "bun install"
    return f"""
.PHONY: setup
setup: ## Install frontend dependencies
\t@echo 'Setting up frontend...'
\tcd frontend && {install_cmd}
\t@echo 'Setup complete!'"""


def _docker_targets(config: ProjectConfig) -> str:
    return """
.PHONY: up up-celery down logs restart
up: ## Start all services (Docker)
\tdocker compose up -d

up-celery: ## Start all services + Celery workers
\tdocker compose --profile celery up -d

down: ## Stop all services
\tdocker compose down

logs: ## Tail service logs
\tdocker compose logs -f

restart: ## Restart all services
\tdocker compose restart"""


def _backend_targets(config: ProjectConfig) -> str:
    if config.is_nestjs_backend:
        return _nestjs_backend_targets(config)
    if config.is_fastapi_backend:
        return _fastapi_backend_targets(config)
    return _django_backend_targets()


def _django_backend_targets() -> str:
    return """
.PHONY: backend-setup backend-dev backend-test backend-lint
.PHONY: backend-migrate backend-shell backend-makemigrations backend-superuser
backend-setup: ## Install backend deps
\tcd backend && uv sync

backend-dev: ## Run backend dev server
\tcd backend && uv run python manage.py runserver

backend-test: ## Run backend tests
\tcd backend && uv run pytest -v

backend-lint: ## Lint backend
\tcd backend && uv run ruff check .

backend-migrate: ## Run Django migrations
\tcd backend && uv run python manage.py migrate

backend-makemigrations: ## Create Django migrations
\tcd backend && uv run python manage.py makemigrations

backend-shell: ## Django shell
\tcd backend && uv run python manage.py shell

backend-superuser: ## Create Django superuser
\tcd backend && uv run python manage.py createsuperuser"""


def _fastapi_backend_targets(config: ProjectConfig) -> str:
    return """
.PHONY: backend-setup backend-dev backend-test backend-lint
.PHONY: backend-migrate backend-shell backend-worker backend-beat
backend-setup: ## Install backend deps
\tcd backend && uv sync --extra dev

backend-dev: ## Run FastAPI dev server (port 8000)
\tcd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

backend-test: ## Run backend tests (pytest)
\tcd backend && uv run pytest -v

backend-lint: ## Lint backend (ruff)
\tcd backend && uv run ruff check .

backend-migrate: ## Run Alembic migrations
\tcd backend && uv run alembic upgrade head

backend-makemigrations: ## Create a new Alembic migration
\tcd backend && uv run alembic revision --autogenerate -m "$(MSG)"

backend-shell: ## Open Python shell
\tcd backend && uv run python

backend-worker: ## Run Celery worker
\tcd backend && uv run celery -A app.workers.celery_app worker --loglevel=info

backend-beat: ## Run Celery beat scheduler
\tcd backend && uv run celery -A app.workers.celery_app beat --loglevel=info"""


def _nestjs_backend_targets(config: ProjectConfig) -> str:
    port = config.backend_api_port
    return f"""
.PHONY: backend-setup backend-dev backend-build backend-test backend-lint
.PHONY: backend-migrate backend-seed backend-studio
backend-setup: ## Install backend deps
\tcd backend && bun install

backend-dev: ## Run NestJS dev server (port {port})
\tcd backend && PORT={port} bun run start:dev

backend-build: ## Build NestJS for production
\tcd backend && bun run build

backend-test: ## Run backend tests (Jest)
\tcd backend && bun run test

backend-test-cov: ## Run tests with coverage
\tcd backend && bun run test:cov

backend-lint: ## Lint backend (Biome)
\tcd backend && bun run lint

backend-migrate: ## Run Drizzle migrations
\tcd backend && bun run db:migrate

backend-seed: ## Seed the database
\tcd backend && bun run db:seed

backend-studio: ## Open Drizzle Studio
\tcd backend && bun run db:studio"""


def _frontend_targets(config: ProjectConfig) -> str:
    cmds = frontend_commands(config)
    test_comment = "Run frontend tests" if cmds.test else "Frontend has no test script"
    test_recipe = (
        f"\tcd frontend && {cmds.test}"
        if cmds.test
        else "\t@echo 'This frontend has no test script; see frontend/package.json'"
    )
    typecheck_comment = "Type-check frontend" if cmds.typecheck else "No type-check script"
    typecheck_recipe = (
        f"\tcd frontend && {cmds.typecheck}"
        if cmds.typecheck
        else "\t@echo 'This frontend has no type-check script'"
    )
    return f"""
.PHONY: frontend-setup frontend-dev frontend-build frontend-test frontend-lint frontend-typecheck
frontend-setup: ## Install frontend deps
\tcd frontend && bun install

frontend-dev: ## Run frontend dev server
\tcd frontend && bun run dev

frontend-build: ## Build frontend
\tcd frontend && bun run build

frontend-test: ## {test_comment}
{test_recipe}

frontend-typecheck: ## {typecheck_comment}
{typecheck_recipe}

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
    if config.is_nestjs_backend:
        return _combined_targets_nestjs(config)
    return _combined_targets_django(config)


def _combined_targets_django(config: ProjectConfig) -> str:
    cmds = frontend_commands(config)
    frontend_format = cmds.format or "echo 'No frontend format script'"
    frontend_check = cmds.typecheck or "echo 'No frontend type-check script'"
    frontend_test = cmds.test or "echo 'No frontend test script'"
    return f"""
.PHONY: test lint typecheck format sync-types gauntlet clean
test: ## Run backend tests and the frontend test suite
\t@echo 'Running backend tests...'
\tcd backend && uv run pytest -v
\t@echo 'Running frontend tests...'
\tcd frontend && {frontend_test}

lint: ## Lint all code
\tcd backend && uv run ruff check . && uv run ruff format --check .
\tcd frontend && {cmds.lint}

typecheck: ## Type-check the frontend
\tcd frontend && {frontend_check}

format: ## Format all code
\tcd backend && uv run ruff format .
\tcd frontend && {frontend_format}

sync-types: ## Sync backend types to frontend TypeScript
\tmattstack sync types

gauntlet: ## Run the verification gate
\tmattstack audit

clean: ## Clean all build artifacts
\tdocker compose down -v
\trm -rf backend/.pytest_cache backend/__pycache__
\trm -rf frontend/node_modules frontend/dist"""


def _combined_targets_nestjs(config: ProjectConfig) -> str:
    cmds = frontend_commands(config)
    return f"""
.PHONY: test lint format gauntlet clean
test: ## Run all tests
\t@echo 'Running backend tests...'
\tcd backend && bun run test
\t@echo 'Running frontend tests...'
\tcd frontend && {cmds.test or "echo 'No frontend test script'"}

lint: ## Lint all code
\tcd backend && bun run lint
\tcd frontend && {cmds.lint}

format: ## Format all code
\tcd backend && bun run format
\tcd frontend && {cmds.format or "echo 'No frontend format script'"}

gauntlet: ## Run the verification gate
\tmattstack audit

clean: ## Clean all build artifacts
\tdocker compose down -v
\trm -rf backend/dist backend/node_modules
\trm -rf frontend/node_modules frontend/dist"""


def _prod_targets() -> str:
    return """
.PHONY: prod-build prod-up prod-down
prod-build: ## Build production images
\tdocker compose -f docker-compose.prod.yml build

prod-up: ## Start production (uses .env.production)
\tdocker compose -f docker-compose.prod.yml --env-file .env.production up -d --build

prod-down: ## Stop production
\tdocker compose -f docker-compose.prod.yml down"""
