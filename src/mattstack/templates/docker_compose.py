"""Docker Compose dev template for generated projects."""

from __future__ import annotations

from mattstack.config import ProjectConfig
from mattstack.templates.compose_env import (
    backend_env,
    db_service,
    depends_block,
    redis_service,
    render_anchor,
    render_mapping,
    service_environment,
)
from mattstack.templates.frontend_runtime import (
    DEV_API_SERVICE,
    FRONTEND_PORT,
    browser_env,
    proxy_target_env_var,
    service_origin,
)


def generate_docker_compose(config: ProjectConfig) -> str:
    """Generate docker-compose.yml for development."""
    services: list[str] = []
    volumes: list[str] = []
    header = ""

    if config.has_backend:
        header = render_anchor(backend_env(config, production=False)) + "\n\n"
        services.append(db_service(config, production=False))
        volumes.append("  postgres_data:")

        if config.use_redis:
            services.append(redis_service(production=False))
            volumes.append("  redis_data:")

        services.append(_api_dev_service(config))
        if config.use_celery:
            services.append(_celery_service(config, "worker"))
            services.append(_celery_service(config, "beat"))

    if config.has_frontend:
        services.append(_frontend_dev_service(config))

    result = header + "services:\n" + "\n\n".join(services)
    if volumes:
        result += "\n\nvolumes:\n" + "\n".join(volumes)
    return result + "\n"


def _api_dev_service(config: ProjectConfig) -> str:
    port = config.backend_api_port
    cors = f"http://localhost:${{FRONTEND_PORT:-{FRONTEND_PORT}}}"
    if config.is_nestjs_backend:
        command = 'sh -c "bun run db:migrate && bun run start:dev"'
        extra: dict[str, str] = {}
        volumes = "      - ./backend:/app\n      - /app/node_modules"
    elif config.is_fastapi_backend:
        command = f"uv run uvicorn app.main:app --host 0.0.0.0 --port {port} --reload"
        extra = {"CORS_ORIGINS": cors}
        volumes = "      - ./backend:/app"
    else:
        command = f"uv run python manage.py runserver 0.0.0.0:{port}"
        extra = {"CORS_ALLOWED_ORIGINS": cors}
        volumes = "      - ./backend:/app"
    return f"""\
  {DEV_API_SERVICE}:
    build:
      context: .
      dockerfile: docker/backend/Dockerfile
      target: development
    command: {command}
    ports:
      - "${{API_PORT:-{port}}}:{port}"
    volumes:
{volumes}
{service_environment(extra)}
{depends_block(config)}"""


def _celery_service(config: ProjectConfig, role: str) -> str:
    return f"""\
  celery-{role}:
    build:
      context: .
      dockerfile: docker/backend/Dockerfile
      target: development
    command: uv run celery -A {config.django_package} {role} -l info
    volumes:
      - ./backend:/app
{service_environment({})}
{depends_block(config)}
    profiles:
      - celery"""


def _frontend_dev_service(config: ProjectConfig) -> str:
    """Render ``frontend-dev``; the dev server listens on 3000 in every framework."""
    volumes = ["./frontend:/app", "/app/node_modules"]
    if config.is_nextjs:
        volumes.append("/app/.next")
        command = "bun run dev -H 0.0.0.0"
    else:
        command = "bun run dev --host 0.0.0.0"

    lines = [
        "  frontend-dev:",
        "    build:",
        "      context: .",
        "      dockerfile: docker/frontend/Dockerfile.dev",
        f"    command: {command}",
        "    ports:",
        f'      - "${{FRONTEND_PORT:-{FRONTEND_PORT}}}:{FRONTEND_PORT}"',
        "    volumes:",
        *(f"      - {volume}" for volume in volumes),
    ]
    if config.has_backend:
        # The browser calls the relative API prefix; the dev server forwards it
        # to the api-dev service, never to the container's own localhost.
        env = browser_env(config)
        env[proxy_target_env_var(config)] = service_origin(config, DEV_API_SERVICE)
        lines.extend(["    environment:", render_mapping(env, indent=6)])
        lines.extend(["    depends_on:", f"      - {DEV_API_SERVICE}"])
    return "\n".join(lines)
