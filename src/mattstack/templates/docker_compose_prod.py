"""Docker Compose production template for generated projects.

Run it with ``--env-file .env.production``. Secrets have no default: Compose
refuses to start when one is missing instead of shipping a placeholder.
"""

from __future__ import annotations

from mattstack.config import ProjectConfig
from mattstack.runtime_profiles import TaskProcess, task_processes
from mattstack.templates.compose_env import (
    backend_build,
    backend_env,
    db_service,
    depends_block,
    redis_service,
    render_anchor,
    render_mapping,
    required,
    service_environment,
)
from mattstack.templates.frontend_runtime import (
    FRONTEND_PORT,
    PROD_API_SERVICE,
    api_prefix,
    browser_env,
    service_origin,
)
from mattstack.templates.realtime_compose import centrifugo_service

_ENV_FILE = ".env.production"


def generate_docker_compose_prod(config: ProjectConfig) -> str:
    """Generate docker-compose.prod.yml."""
    services: list[str] = []
    volumes: list[str] = []
    header = ""

    if config.has_backend:
        header = render_anchor(backend_env(config, production=True)) + "\n\n"
        services.append(db_service(config, production=True))
        volumes.append("  postgres_data:")

        if config.use_redis:
            services.append(redis_service(config, production=True))
            volumes.append("  redis_data:")

        services.append(_api_service(config))

        # Production runs the selected queue's consumers without a profile.
        prod_processes = task_processes(config, production=True)
        services.extend(_task_service(config, process) for process in prod_processes)
        if config.use_realtime:
            services.append(centrifugo_service(production=True))

    if config.has_frontend:
        services.append(_frontend_service(config))

    result = header + "services:\n" + "\n\n".join(services)
    if volumes:
        result += "\n\nvolumes:\n" + "\n".join(volumes)
    return result + "\n"


def _api_service(config: ProjectConfig) -> str:
    port = config.backend_api_port
    origin = f"http://localhost:${{FRONTEND_PORT:-{FRONTEND_PORT}}}"
    extra: dict[str, str] = {}
    if config.is_django_backend:
        extra = {
            "ALLOWED_HOSTS": required("ALLOWED_HOSTS", _ENV_FILE),
            # prod.py reads these with an empty default, and only keys listed
            # under `environment:` reach the container.
            "CORS_ALLOWED_ORIGINS": f"${{CORS_ALLOWED_ORIGINS:-{origin}}}",
            "CSRF_TRUSTED_ORIGINS": f"${{CSRF_TRUSTED_ORIGINS:-{origin}}}",
        }
    return f"""\
  {PROD_API_SERVICE}:
{backend_build(config, "production")}
    ports:
      - "${{API_PORT:-{port}}}:{port}"
{service_environment(extra)}
{depends_block(config)}
    restart: unless-stopped"""


def _task_service(config: ProjectConfig, process: TaskProcess) -> str:
    return f"""\
  {process.service}:
{backend_build(config, "production")}
    command: {process.command}
{service_environment({})}
{depends_block(config)}
    restart: unless-stopped"""


def _frontend_service(config: ProjectConfig) -> str:
    """Next.js serves on 3000; the static frontends serve through nginx on 80."""
    internal_port = FRONTEND_PORT if config.is_nextjs else 80
    lines = [
        "  frontend:",
        "    build:",
        "      context: .",
        "      dockerfile: docker/frontend/Dockerfile",
    ]
    env: dict[str, str] = {}
    if config.has_backend:
        upstream = service_origin(config, PROD_API_SERVICE)
        # The bundler inlines the browser variables, so they are build args.
        # Each one is relative and can be overridden from .env.production.
        args = {key: f"${{{key}:-{value}}}" for key, value in browser_env(config).items()}
        if config.is_nextjs:
            # next.config.ts bakes the server-side rewrite target at build time.
            args["INTERNAL_API_URL"] = upstream
            env = {"INTERNAL_API_URL": upstream}
        else:
            env = {"API_UPSTREAM": upstream, "API_PREFIX": api_prefix(config)}
        lines.extend(["      args:", render_mapping(args, indent=8)])
    lines.extend(["    ports:", f'      - "${{FRONTEND_PORT:-{FRONTEND_PORT}}}:{internal_port}"'])
    if env:
        lines.extend(["    environment:", render_mapping(env, indent=6)])
    if config.has_backend:
        lines.extend(["    depends_on:", f"      - {PROD_API_SERVICE}"])
    lines.append("    restart: unless-stopped")
    return "\n".join(lines)
