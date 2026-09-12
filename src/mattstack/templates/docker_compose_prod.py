"""Docker Compose production template for generated projects."""

from __future__ import annotations

from mattstack.config import ProjectConfig


def generate_docker_compose_prod(config: ProjectConfig) -> str:
    """Generate docker-compose.prod.yml."""
    services: list[str] = []
    volumes: list[str] = []

    if config.has_backend:
        services.append(_db_service(config))
        volumes.append("  postgres_data:")

        if config.use_redis:
            services.append(_redis_service())
            volumes.append("  redis_data:")

        services.append(_api_service(config))

        if config.use_celery:
            services.append(_celery_worker_service(config))
            services.append(_celery_beat_service(config))

    if config.has_frontend:
        services.append(_frontend_service(config))

    services_block = "\n\n".join(services)
    volumes_block = "\n".join(volumes)

    result = f"""services:
{services_block}"""

    if volumes:
        result += f"""

volumes:
{volumes_block}"""

    return result


def _db_service(config: ProjectConfig) -> str:
    return f"""\
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: ${{POSTGRES_DB:-{config.python_package_name}}}
      POSTGRES_USER: ${{POSTGRES_USER:-postgres}}
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD}}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped"""


def _redis_service() -> str:
    return """\
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped"""


def _api_service(config: ProjectConfig) -> str:
    depends = ["db"]
    if config.use_redis:
        depends.append("redis")

    depends_block = "\n".join(
        f"      {dep}:\n        condition: service_healthy" for dep in depends
    )

    return f"""\
  api:
    build:
      context: .
      dockerfile: docker/backend/Dockerfile
      target: production
    ports:
      - "${{API_PORT:-8000}}:8000"
    environment:
      DEBUG: "false"
      DATABASE_URL: postgres://${{POSTGRES_USER:-postgres}}:${{POSTGRES_PASSWORD}}@db:5432/{config.python_package_name}
      DJANGO_SECRET_KEY: ${{DJANGO_SECRET_KEY}}
      REDIS_URL: redis://redis:6379/0
      ALLOWED_HOSTS: ${{ALLOWED_HOSTS:-*}}
    depends_on:
{depends_block}
    restart: unless-stopped"""


def _celery_worker_service(config: ProjectConfig) -> str:
    return f"""\
  celery-worker:
    build:
      context: .
      dockerfile: docker/backend/Dockerfile
      target: production
    command: celery -A {config.django_package} worker -l warning --concurrency=4
    environment:
      DATABASE_URL: postgres://${{POSTGRES_USER:-postgres}}:${{POSTGRES_PASSWORD}}@db:5432/{config.python_package_name}
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped"""


def _celery_beat_service(config: ProjectConfig) -> str:
    return f"""\
  celery-beat:
    build:
      context: .
      dockerfile: docker/backend/Dockerfile
      target: production
    command: celery -A {config.django_package} beat -l warning
    environment:
      DATABASE_URL: postgres://${{POSTGRES_USER:-postgres}}:${{POSTGRES_PASSWORD}}@db:5432/{config.python_package_name}
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped"""


def _frontend_service(config: ProjectConfig) -> str:
    lines = [
        "  frontend:",
        "    build:",
        "      context: .",
        "      dockerfile: docker/frontend/Dockerfile",
        "    ports:",
        '      - "${FRONTEND_PORT:-3000}:80"',
    ]

    if config.has_backend:
        lines.extend(
            [
                "    depends_on:",
                "      - api",
            ]
        )

    lines.append("    restart: unless-stopped")
    return "\n".join(lines)
