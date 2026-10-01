"""Backend environment shared by the dev and production Compose files.

Every backend service reads its database credentials from one place: the
``POSTGRES_*`` variables that also configure the ``db`` service. The rendered
file defines them once in an ``x-backend-env`` anchor, and each service merges
it, so the API and the Celery workers cannot disagree with the database.
"""

from __future__ import annotations

import json

from mattstack.config import MediaStorage, ProjectConfig
from mattstack.runtime_profiles import (
    CENTRIFUGO_CONTAINER_PORT,
    CENTRIFUGO_SERVICE,
    REALTIME_SECRETS,
    task_backend_env,
)
from mattstack.templates.frontend_runtime import FRONTEND_PORT

ANCHOR = "backend-env"


def required(name: str, env_file: str) -> str:
    """Return a Compose reference that fails when ``name`` is unset or empty."""
    return f"${{{name}:?Set {name} in {env_file}}}"


def db_credentials(config: ProjectConfig, *, production: bool) -> tuple[str, str, str]:
    """Return the Compose references for (database, user, password)."""
    password = (
        required("POSTGRES_PASSWORD", ".env.production")
        if production
        else "${POSTGRES_PASSWORD:-postgres}"
    )
    return (
        f"${{POSTGRES_DB:-{config.python_package_name}}}",
        "${POSTGRES_USER:-postgres}",
        password,
    )


def db_service(config: ProjectConfig, *, production: bool) -> str:
    """Render the ``db`` service; dev publishes ${DB_PORT}, production does not."""
    name, user, password = db_credentials(config, production=production)
    ports = "" if production else '\n    ports:\n      - "127.0.0.1:${DB_PORT:-5432}:5432"'
    restart = "\n    restart: unless-stopped" if production else ""
    # Check over TCP with the configured user and database. During first
    # boot the init scripts run against a socket-only server, so a socket
    # check reports ready before the database accepts connections.
    return f"""\
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: "{name}"
      POSTGRES_USER: "{user}"
      POSTGRES_PASSWORD: "{password}"{ports}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U $${{POSTGRES_USER}} -d $${{POSTGRES_DB}}"]
      interval: 5s
      timeout: 5s
      retries: 10{restart}"""


def redis_service(*, production: bool) -> str:
    ports = "" if production else '\n    ports:\n      - "127.0.0.1:${REDIS_PORT:-6379}:6379"'
    restart = "\n    restart: unless-stopped" if production else ""
    return f"""\
  redis:
    image: redis:7-alpine{ports}
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5{restart}"""


def backend_env(config: ProjectConfig, *, production: bool) -> dict[str, str]:
    """Return the environment every backend service shares."""
    name, user, password = db_credentials(config, production=production)
    env_file = ".env.production"

    def secret(key: str, dev_default: str) -> str:
        return required(key, env_file) if production else f"${{{key}:-{dev_default}}}"

    frontend_origin = f"http://localhost:${{FRONTEND_PORT:-{FRONTEND_PORT}}}"
    if config.is_nestjs_backend:
        env = {
            "NODE_ENV": "production" if production else "development",
            "PORT": str(config.backend_api_port),
            "HOST": "0.0.0.0",  # nosec B104 # Container listener; host publishing is separate.
            "DATABASE_URL": f"postgresql://{user}:{password}@db:5432/{name}",
            "JWT_SECRET": secret("JWT_SECRET", "change-me-jwt-secret-at-least-32-chars"),
            "JWT_REFRESH_SECRET": secret(
                "JWT_REFRESH_SECRET", "change-me-refresh-secret-at-least-32-chars"
            ),
            "CORS_ORIGINS": f"${{CORS_ORIGINS:-{frontend_origin}}}",
        }
        if config.use_redis:
            env["REDIS_URL"] = "redis://redis:6379"
        return env

    scheme = "postgresql+asyncpg" if config.is_fastapi_backend else "postgres"
    env = {
        "DEBUG": "false" if production else "true",
        "DATABASE_URL": f"{scheme}://{user}:{password}@db:5432/{name}",
        "SECRET_KEY": secret(
            "SECRET_KEY",
            "change-me-dev-secret-key-at-least-32-characters"
            if config.is_fastapi_backend
            else "change-me-in-production",
        ),
    }
    if config.is_fastapi_backend:
        env.update(
            {
                "APP_ENV": "production" if production else "development",
                "APP_DEBUG": "false" if production else "true",
                "JWT_SECRET_KEY": secret(
                    "JWT_SECRET_KEY", "change-me-dev-jwt-key-at-least-32-characters"
                ),
                "CORS_ORIGINS": (
                    required("CORS_ORIGINS", env_file)
                    if production
                    else "${CORS_ORIGINS:-" + json.dumps([frontend_origin]) + "}"
                ),
                "ALLOWED_HOSTS": "${ALLOWED_HOSTS:-" + json.dumps(["localhost", "127.0.0.1"]) + "}",
            }
        )
        if production:
            env.update(
                {key: required(key, env_file) for key in ("WEBAUTHN_RP_ID", "WEBAUTHN_ORIGIN")}
            )
    if config.is_django_backend:
        # The Django settings read discrete DB_* variables, not DATABASE_URL.
        env.update(
            {
                "DJANGO_ENVIRONMENT": "production" if production else "development",
                "DB_NAME": name,
                "DB_USER": user,
                "DB_PASSWORD": password,
                "DB_HOST": "db",
                "DB_PORT": "5432",
            }
        )
        if not config.is_django_matt:
            # Ninja settings read ENVIRONMENT for logging and the S3 media branch.
            env["ENVIRONMENT"] = "production" if production else "development"
            if production:
                env["NINJA_JWT_SIGNING_KEY"] = secret("NINJA_JWT_SIGNING_KEY", "")
                env["CENTRIFUGO_TOKEN_SECRET"] = secret("CENTRIFUGO_TOKEN_SECRET", "")
    if config.use_redis:
        env["REDIS_URL"] = "redis://redis:6379/0"
        if config.is_fastapi_backend and config.use_celery:
            env["CELERY_BROKER_URL"] = "redis://redis:6379/1"
            env["CELERY_RESULT_BACKEND"] = "redis://redis:6379/2"
    env.update(task_backend_env(config))
    env.update(_optional_service_env(config, production=production))
    return env


def _optional_service_env(config: ProjectConfig, *, production: bool) -> dict[str, str]:
    """Return Centrifugo and S3 keys for the opt-in realtime and media choices.

    Realtime secrets have no default anywhere: Compose refuses to start until
    the env file sets them, so Django and Centrifugo cannot disagree.
    """
    env_file = ".env.production" if production else ".env"
    env: dict[str, str] = {}
    if config.use_realtime:
        env["CENTRIFUGO_URL"] = f"http://{CENTRIFUGO_SERVICE}:{CENTRIFUGO_CONTAINER_PORT}"
        env.update({key: required(key, env_file) for key in REALTIME_SECRETS})
    if production and config.media_storage == MediaStorage.S3:
        # Ninja enables S3 media only in production; static files stay local.
        for key in ("AWS_STORAGE_BUCKET_NAME", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
            env[key] = required(key, env_file)
        env["AWS_S3_REGION_NAME"] = "${AWS_S3_REGION_NAME:-us-east-1}"
    return env


def render_anchor(env: dict[str, str]) -> str:
    """Render the ``x-backend-env`` extension field."""
    return f"x-{ANCHOR}: &{ANCHOR}\n" + render_mapping(env, indent=2)


def render_mapping(env: dict[str, str], *, indent: int) -> str:
    pad = " " * indent
    return "\n".join(f"{pad}{key}: {json.dumps(value)}" for key, value in env.items())


def service_environment(extra: dict[str, str]) -> str:
    """Render an ``environment:`` block that merges the shared anchor."""
    lines = ["    environment:", f"      <<: *{ANCHOR}"]
    if extra:
        lines.append(render_mapping(extra, indent=6))
    return "\n".join(lines)


def depends_block(config: ProjectConfig) -> str:
    deps = ["db", "redis"] if config.use_redis else ["db"]
    lines = ["    depends_on:"]
    for dep in deps:
        lines.extend([f"      {dep}:", "        condition: service_healthy"])
    return "\n".join(lines)
