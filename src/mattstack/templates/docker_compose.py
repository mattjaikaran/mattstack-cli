"""Docker Compose dev template for generated projects."""

from __future__ import annotations

from mattstack.config import ProjectConfig
from mattstack.runtime_profiles import TaskProcess, task_processes, task_profile, uv_run
from mattstack.templates.compose_env import (
    ai_services,
    backend_build,
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
from mattstack.templates.realtime_compose import centrifugo_service


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
            services.append(redis_service(config, production=False))
            volumes.append("  redis_data:")

        services.append(_api_dev_service(config))
        # Task workers and Centrifugo start only with their profile, so a
        # plain `docker compose up` keeps the same services.
        dev_processes = task_processes(config, production=False)
        services.extend(_task_service(config, process) for process in dev_processes)
        if config.use_realtime:
            services.append(centrifugo_service(production=False))
        extra_services = ai_services(config)
        services.extend(extra_services)
        volumes.extend(
            f"  {name}_data:"
            for name in ("qdrant", "neo4j")
            if any(service.startswith(f"  {name}:") for service in extra_services)
        )

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
        extra = {}
        volumes = "      - ./backend:/app"
    else:
        command = f"{uv_run(config)} python manage.py runserver 0.0.0.0:{port}"
        extra = {"CORS_ALLOWED_ORIGINS": cors}
        volumes = "      - ./backend:/app"
    return f"""\
  {DEV_API_SERVICE}:
{backend_build(config, "development")}
    command: {command}
    ports:
      - "127.0.0.1:${{API_PORT:-{port}}}:{port}"
    volumes:
{volumes}
{service_environment(extra)}
{depends_block(config)}"""


def _task_service(config: ProjectConfig, process: TaskProcess) -> str:
    """Render a task worker on the backend's Compose profile (celery, huey, ...)."""
    return f"""\
  {process.service}:
{backend_build(config, "development")}
    command: {uv_run(config)} {process.command}
    volumes:
      - ./backend:/app
{service_environment({})}
{depends_block(config)}
    profiles:
      - {task_profile(config)}"""


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
        f'      - "127.0.0.1:${{FRONTEND_PORT:-{FRONTEND_PORT}}}:{FRONTEND_PORT}"',
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
