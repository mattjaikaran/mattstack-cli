"""Root .env templates for generated projects.

The ports come first and the ``POSTGRES_*`` credentials come next, because
later keys refer to them with ``${NAME}``. ``make`` sources the file in a
shell, Compose interpolates it, and mattstack expands earlier keys, so each
credential has a single source on the host and in the containers.
"""

from __future__ import annotations

import json
import secrets

from mattstack.config import MediaStorage, ProjectConfig
from mattstack.runtime_profiles import (
    CENTRIFUGO_PORT,
    REALTIME_SECRETS,
    celery_env,
    task_backend_env,
)
from mattstack.templates.frontend_runtime import (
    FRONTEND_PORT,
    PROD_API_SERVICE,
    browser_env,
    service_origin,
)

_DB = "${POSTGRES_DB}"
_USER = "${POSTGRES_USER}"
_PASSWORD = "${POSTGRES_PASSWORD}"  # nosec B105 # Environment reference, not a credential.


def generate_env_example(
    config: ProjectConfig, *, realtime_secrets: dict[str, str] | None = None
) -> str:
    """Generate .env.example; ``realtime_secrets`` fills the Centrifugo keys for .env."""
    frontend_origin = "http://localhost:${FRONTEND_PORT}"
    lines: list[str] = [
        f"# Project: {config.display_name}",
        "",
        "# === Ports (host side; Compose publishes these) ===",
        f"API_PORT={config.backend_api_port}",
        f"FRONTEND_PORT={FRONTEND_PORT}",
    ]
    if config.has_backend:
        lines.append("DB_PORT=5432")
        if config.use_redis:
            lines.append("REDIS_PORT=6379")
        if config.use_realtime:
            lines.append(f"CENTRIFUGO_PORT={CENTRIFUGO_PORT}")
    lines.append("")

    if config.has_backend:
        lines.extend(_database_lines(config, password="postgres"))  # nosec B106 # Local-only development database example.
        db_url = f"{_USER}:{_PASSWORD}@localhost:${{DB_PORT}}/{_DB}"
        redis = "redis://localhost:${REDIS_PORT}"
        if config.is_nestjs_backend:
            lines.extend(
                [
                    "# === Backend (NestJS) ===",
                    "NODE_ENV=development",
                    "PORT=${API_PORT}",
                    "HOST=0.0.0.0",
                    f'APP_NAME="{config.display_name}"',
                    "APP_URL=http://localhost:${API_PORT}",
                    f"DATABASE_URL=postgresql://{db_url}",
                    "JWT_SECRET=change-me-jwt-secret-at-least-32-chars",
                    "JWT_REFRESH_SECRET=change-me-refresh-secret-at-least-32-chars",
                    "JWT_ACCESS_EXPIRY=15m",
                    "JWT_REFRESH_EXPIRY=7d",
                    f"CORS_ORIGINS={frontend_origin}",
                ]
            )
            if config.use_redis:
                lines.append(f"REDIS_URL={redis}")
        else:
            label = "FastAPI" if config.is_fastapi_backend else "Django"
            scheme = "postgresql+asyncpg" if config.is_fastapi_backend else "postgres"
            lines.extend(
                [
                    f"# === Backend ({label}) ===",
                    "DEBUG=true",
                    f"SECRET_KEY=change-me-dev-{config.name}-secret-key-at-least-32-chars"
                    if config.is_fastapi_backend
                    else f"SECRET_KEY=change-me-{config.name}-secret",
                    f"DATABASE_URL={scheme}://{db_url}",
                ]
            )
            if config.is_django_backend:
                # DB_* is what the Django settings read; DATABASE_URL alone
                # leaves settings.DATABASES with an empty NAME.
                # DB_PORT is already set above: the host reaches the published port.
                lines.extend(_django_db_lines(host="localhost", port=None))
                if not config.is_django_matt:
                    lines.extend(["DJANGO_ENVIRONMENT=development", "ENVIRONMENT=development"])
                lines.extend(
                    [
                        "ALLOWED_HOSTS=localhost,127.0.0.1",
                        f"CORS_ALLOWED_ORIGINS={frontend_origin}",
                    ]
                )
            else:
                lines.extend(
                    [
                        "APP_ENV=development",
                        "APP_DEBUG=true",
                        f"JWT_SECRET_KEY=change-me-dev-{config.name}-jwt-key-at-least-32-chars",
                        _json_env("CORS_ORIGINS", [frontend_origin]),
                        _json_env("ALLOWED_HOSTS", ["localhost", "127.0.0.1"]),
                    ]
                )
            if config.use_redis:
                lines.append(f"REDIS_URL={redis}/0")
            lines.extend(f"{key}={value}" for key, value in celery_env(config, redis).items())
            lines.extend(_task_lines(config))
            if config.use_realtime:
                lines.extend(_realtime_lines(realtime_secrets or {}))
        lines.append("")

    if config.has_frontend:
        lines.extend(_frontend_lines(config, "http://localhost:${API_PORT}"))

    return "\n".join(lines).rstrip() + "\n"


def generate_env_file(config: ProjectConfig) -> str:
    """Generate the gitignored .env; realtime projects get fresh random secrets."""
    if not config.use_realtime:
        return generate_env_example(config)
    fresh = {key: secrets.token_hex(32) for key in REALTIME_SECRETS}
    return generate_env_example(config, realtime_secrets=fresh)


def _task_lines(config: ProjectConfig) -> list[str]:
    env = task_backend_env(config)
    if not env:
        return []
    comment = (
        "# TASK_BACKEND=none runs no worker: .delay() raises TaskDispatchDisabled"
        if env["TASK_BACKEND"] == "none"
        else "# Task backend; the worker runs under its Compose profile"
    )
    return [comment, f"TASK_BACKEND={env['TASK_BACKEND']}"]


def _realtime_lines(values: dict[str, str]) -> list[str]:
    """Centrifugo keys; Compose maps them onto the Centrifugo container too."""
    return [
        "",
        "# === Realtime (Centrifugo; start with: make up-realtime) ===",
        "# Never commit values. Generate each secret: openssl rand -hex 32",
        "CENTRIFUGO_URL=http://localhost:${CENTRIFUGO_PORT}",
        *(f"{key}={values.get(key, '')}" for key in REALTIME_SECRETS),
    ]


def generate_env_production_example(config: ProjectConfig) -> str:
    """Generate .env.production.example; Compose fails if a secret is missing."""
    origin = "https://your-domain.com"
    lines: list[str] = [
        f"# Project: {config.display_name} (production)",
        "# Used with: docker compose -f docker-compose.prod.yml --env-file .env.production",
        "",
        "# === Ports (host side) ===",
        f"API_PORT={config.backend_api_port}",
        "FRONTEND_PORT=80",
    ]
    if config.use_realtime:
        lines.append(f"CENTRIFUGO_PORT={CENTRIFUGO_PORT}")
    lines.append("")

    if config.has_backend:
        lines.extend(_database_lines(config, password="change-me-strong-password"))  # nosec B106 # Placeholder; replace in production.
        db_url = f"{_USER}:{_PASSWORD}@db:5432/{_DB}"
        if config.is_nestjs_backend:
            lines.extend(
                [
                    "# === Backend (NestJS) ===",
                    "NODE_ENV=production",
                    f"PORT={config.backend_api_port}",
                    f'APP_NAME="{config.display_name}"',
                    f"APP_URL={origin}",
                    f"DATABASE_URL=postgresql://{db_url}",
                    "JWT_SECRET=change-me-jwt-secret-at-least-32-chars",
                    "JWT_REFRESH_SECRET=change-me-refresh-secret-at-least-32-chars",
                    f"CORS_ORIGINS={origin}",
                ]
            )
            if config.use_redis:
                lines.append("REDIS_URL=redis://redis:6379")
        else:
            label = "FastAPI" if config.is_fastapi_backend else "Django"
            scheme = "postgresql+asyncpg" if config.is_fastapi_backend else "postgres"
            lines.extend(
                [
                    f"# === Backend ({label}) ===",
                    "DEBUG=false",
                    "SECRET_KEY=change-me-strong-secret-key",
                    f"DATABASE_URL={scheme}://{db_url}",
                ]
            )
            if config.is_django_backend:
                lines.append("DJANGO_ENVIRONMENT=production")
                if not config.is_django_matt:
                    lines.extend(
                        [
                            "ENVIRONMENT=production",
                            "NINJA_JWT_SIGNING_KEY=change-me-distinct-jwt-signing-key",
                            "CENTRIFUGO_TOKEN_SECRET=change-me-distinct-realtime-secret",
                        ]
                    )
                lines.extend(_django_db_lines(host="db", port="5432"))
                lines.extend(
                    [
                        f"ALLOWED_HOSTS={origin.removeprefix('https://')}",
                        f"CORS_ALLOWED_ORIGINS={origin}",
                        f"CSRF_TRUSTED_ORIGINS={origin}",
                    ]
                )
            else:
                lines.extend(
                    [
                        "APP_ENV=production",
                        "APP_DEBUG=false",
                        "JWT_SECRET_KEY=change-me-distinct-jwt-key-at-least-32-characters",
                        _json_env("CORS_ORIGINS", [origin]),
                        _json_env("ALLOWED_HOSTS", [origin.removeprefix("https://")]),
                        f"WEBAUTHN_RP_ID={origin.removeprefix('https://')}",
                        f"WEBAUTHN_ORIGIN={origin}",
                    ]
                )
            if config.use_redis:
                lines.append("REDIS_URL=redis://redis:6379/0")
            lines.extend(
                f"{key}={value}" for key, value in celery_env(config, "redis://redis:6379").items()
            )
            lines.extend(_task_lines(config))
            if config.use_realtime:
                lines.extend(
                    [
                        "",
                        "# === Realtime (Centrifugo) ===",
                        "# Generate: openssl rand -hex 32. Compose refuses to start while empty.",
                        "CENTRIFUGO_API_KEY=",
                        "# Browser origins allowed to open a WebSocket, space separated",
                        f"CENTRIFUGO_ALLOWED_ORIGINS={origin}",
                    ]
                )
            if config.media_storage == MediaStorage.S3:
                lines.extend(
                    [
                        "",
                        "# === Media storage (S3, opt-in; static files stay local) ===",
                        "AWS_STORAGE_BUCKET_NAME=",
                        "AWS_ACCESS_KEY_ID=",
                        "AWS_SECRET_ACCESS_KEY=",
                        "AWS_S3_REGION_NAME=us-east-1",
                    ]
                )
        lines.append("")

    if config.has_frontend:
        lines.extend(_frontend_lines(config, service_origin(config, PROD_API_SERVICE)))

    return "\n".join(lines).rstrip() + "\n"


def _database_lines(config: ProjectConfig, *, password: str) -> list[str]:
    return [
        "# === Database (single source; other keys refer to these) ===",
        f"POSTGRES_DB={config.python_package_name}",
        "POSTGRES_USER=postgres",
        f"POSTGRES_PASSWORD={password}",
        "",
    ]


def _django_db_lines(*, host: str, port: str | None) -> list[str]:
    lines = [
        f"DB_NAME={_DB}",
        f"DB_USER={_USER}",
        f"DB_PASSWORD={_PASSWORD}",
        f"DB_HOST={host}",
    ]
    return [*lines, f"DB_PORT={port}"] if port else lines


def _frontend_lines(config: ProjectConfig, backend_origin: str) -> list[str]:
    """The browser calls a relative prefix; the dev server or nginx proxies it.

    `make frontend-dev` and `make frontend-build` load these, so a fresh clone,
    which has no gitignored frontend/.env, still builds with the right values.
    """
    label = "Next.js" if config.is_nextjs else "Frontend"
    lines = [f"# === {label} ==="]
    if config.has_backend:
        lines.extend(f"{key}={value}" for key, value in browser_env(config).items())
        if config.is_nextjs:
            lines.append(f"INTERNAL_API_URL={backend_origin}")
    return [*lines, ""] if len(lines) > 1 else []


def _json_env(key: str, values: list[str]) -> str:
    """Quote JSON list settings so dotenv, Compose, and shell exports preserve them."""
    return f"{key}={json.dumps(json.dumps(values))}"
