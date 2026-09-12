"""Docker Compose dev template for generated projects."""

from __future__ import annotations

from mattstack.config import ProjectConfig


def generate_docker_compose(config: ProjectConfig) -> str:
    """Generate docker-compose.yml for development."""
    services: list[str] = []
    volumes: list[str] = []

    if config.has_backend:
        services.append(_db_service(config))
        volumes.append("  postgres_data:")

        if config.use_redis:
            services.append(_redis_service())
            volumes.append("  redis_data:")

        if config.is_nestjs_backend:
            services.append(_nestjs_api_dev_service(config))
        elif config.is_fastapi_backend:
            services.append(_fastapi_api_dev_service(config))
            if config.use_celery:
                services.append(_celery_worker_service(config))
                services.append(_celery_beat_service(config))
        else:
            services.append(_api_dev_service(config))
            if config.use_celery:
                services.append(_celery_worker_service(config))
                services.append(_celery_beat_service(config))

    if config.has_frontend:
        services.append(_frontend_dev_service(config))

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
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:-postgres}}
    ports:
      - "${{DB_PORT:-5432}}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5"""


def _redis_service() -> str:
    return """\
  redis:
    image: redis:7-alpine
    ports:
      - "${REDIS_PORT:-6379}:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5"""


def _api_dev_service(config: ProjectConfig) -> str:
    depends = ["db"]
    if config.use_redis:
        depends.append("redis")

    depends_block = "\n".join(
        f"      {dep}:\n        condition: service_healthy" for dep in depends
    )

    env_lines = [
        '      DEBUG: "true"',
        f"      DATABASE_URL: postgres://postgres:postgres@db:5432/{config.python_package_name}",
        # The boilerplate's settings read discrete DB_* variables, not
        # DATABASE_URL. Without these, settings.DATABASES has an empty NAME
        # and every management command fails on connect.
        f"      DB_NAME: {config.python_package_name}",
        "      DB_USER: postgres",
        "      DB_PASSWORD: postgres",
        "      DB_HOST: db",
        "      DB_PORT: 5432",
        "      SECRET_KEY: ${SECRET_KEY:-change-me-in-production}",
    ]
    if config.use_redis:
        env_lines.append("      REDIS_URL: redis://redis:6379/0")
    env_lines.append("      CORS_ALLOWED_ORIGINS: http://localhost:3000,http://localhost:5173")

    env_block = "\n".join(env_lines)

    port = config.backend_api_port
    return f"""\
  api-dev:
    build:
      context: .
      dockerfile: docker/backend/Dockerfile
      target: development
    command: uv run python manage.py runserver 0.0.0.0:{port}
    ports:
      - "${{API_PORT:-{port}}}:{port}"
    volumes:
      - ./backend:/app
    environment:
{env_block}
    depends_on:
{depends_block}"""


def _nestjs_api_dev_service(config: ProjectConfig) -> str:
    port = config.backend_api_port
    db_name = config.python_package_name
    return f"""\
  api-dev:
    build:
      context: .
      dockerfile: docker/backend/Dockerfile
      target: development
    command: sh -c "bun run db:migrate && bun run start:dev"
    ports:
      - "${{API_PORT:-{port}}}:{port}"
    volumes:
      - ./backend:/app
      - /app/node_modules
    environment:
      NODE_ENV: development
      PORT: {port}
      HOST: 0.0.0.0
      DATABASE_URL: postgresql://postgres:postgres@db:5432/{db_name}
      REDIS_URL: redis://redis:6379
      CORS_ORIGINS: http://localhost:3000,http://localhost:5173
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy"""


def _fastapi_api_dev_service(config: ProjectConfig) -> str:
    port = config.backend_api_port
    db_name = config.python_package_name
    return f"""\
  api-dev:
    build:
      context: .
      dockerfile: docker/backend/Dockerfile
      target: development
    command: uv run uvicorn app.main:app --host 0.0.0.0 --port {port} --reload
    ports:
      - "${{API_PORT:-{port}}}:{port}"
    volumes:
      - ./backend:/app
    environment:
      DEBUG: "true"
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@db:5432/{db_name}
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: ${{SECRET_KEY:-change-me-in-production}}
      CORS_ORIGINS: http://localhost:3000,http://localhost:5173
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy"""


def _celery_worker_service(config: ProjectConfig) -> str:
    return f"""\
  celery-worker:
    build:
      context: .
      dockerfile: docker/backend/Dockerfile
      target: development
    command: uv run celery -A {config.django_package} worker -l info
    volumes:
      - ./backend:/app
    environment:
      DATABASE_URL: postgres://postgres:postgres@db:5432/{config.python_package_name}
      DB_NAME: {config.python_package_name}
      DB_USER: postgres
      DB_PASSWORD: postgres
      DB_HOST: db
      DB_PORT: 5432
      SECRET_KEY: ${{SECRET_KEY:-change-me-in-production}}
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    profiles:
      - celery"""


def _celery_beat_service(config: ProjectConfig) -> str:
    return f"""\
  celery-beat:
    build:
      context: .
      dockerfile: docker/backend/Dockerfile
      target: development
    command: uv run celery -A {config.django_package} beat -l info
    volumes:
      - ./backend:/app
    environment:
      DATABASE_URL: postgres://postgres:postgres@db:5432/{config.python_package_name}
      DB_NAME: {config.python_package_name}
      DB_USER: postgres
      DB_PASSWORD: postgres
      DB_HOST: db
      DB_PORT: 5432
      SECRET_KEY: ${{SECRET_KEY:-change-me-in-production}}
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    profiles:
      - celery"""


def _frontend_dev_service(config: ProjectConfig) -> str:
    depends = ""
    if config.has_backend:
        depends = """
    depends_on:
      - api-dev"""

    api_url = f"http://localhost:{config.backend_api_port}/api/v1" if config.has_backend else ""

    if config.is_nextjs:
        env_block = ""
        if config.has_backend:
            env_block = f"""
    environment:
      NEXT_PUBLIC_API_BASE_URL: {api_url}"""
        return f"""\
  frontend-dev:
    build:
      context: .
      dockerfile: docker/frontend/Dockerfile.dev
    command: bun run dev
    ports:
      - "${{FRONTEND_PORT:-3000}}:3000"
    volumes:
      - ./frontend:/app
      - /app/node_modules
      - /app/.next{env_block}{depends}"""

    vite_env = f"VITE_API_BASE_URL: {api_url}"
    if config.is_django_backend:
        vite_env += "\n      VITE_MODE: django-spa"

    return f"""\
  frontend-dev:
    build:
      context: .
      dockerfile: docker/frontend/Dockerfile.dev
    command: bun run dev --host
    ports:
      - "${{FRONTEND_PORT:-3000}}:3000"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    environment:
      {vite_env}{depends}"""
