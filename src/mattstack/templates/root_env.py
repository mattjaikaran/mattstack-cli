"""Root .env.example template for generated projects."""

from __future__ import annotations

from mattstack.config import ProjectConfig


def generate_env_example(config: ProjectConfig) -> str:
    """Generate .env.example with combined backend + frontend vars."""
    lines: list[str] = ["# Project: " + config.display_name, ""]
    api_port = config.backend_api_port
    api_base = f"http://localhost:{api_port}/api/v1"

    if config.has_backend:
        if config.is_nestjs_backend:
            lines.extend(
                [
                    "# === Backend (NestJS) ===",
                    "NODE_ENV=development",
                    f"PORT={api_port}",
                    "HOST=0.0.0.0",
                    f"APP_NAME={config.display_name}",
                    f"APP_URL=http://localhost:{api_port}",
                    "",
                    f"POSTGRES_DB={config.python_package_name}",
                    "POSTGRES_USER=postgres",
                    "POSTGRES_PASSWORD=postgres",
                    f"DATABASE_URL=postgresql://postgres:postgres@localhost:5432/{config.python_package_name}",
                    "",
                    "JWT_SECRET=change-me-jwt-secret-at-least-32-chars",
                    "JWT_REFRESH_SECRET=change-me-refresh-secret-at-least-32-chars",
                    "JWT_ACCESS_EXPIRY=15m",
                    "JWT_REFRESH_EXPIRY=7d",
                    "",
                    "CORS_ORIGINS=http://localhost:3000,http://localhost:5173",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "# === Backend (Django) ===",
                    "DEBUG=true",
                    f"SECRET_KEY=change-me-{config.name}-secret",
                    # POSTGRES_* configures the postgres image.
                    f"POSTGRES_DB={config.python_package_name}",
                    "POSTGRES_USER=postgres",
                    "POSTGRES_PASSWORD=postgres",
                    # DB_* is what the Django settings read. Without these,
                    # settings.DATABASES has an empty NAME.
                    f"DB_NAME={config.python_package_name}",
                    "DB_USER=postgres",
                    "DB_PASSWORD=postgres",
                    "DB_HOST=localhost",
                    "DB_PORT=5432",
                    f"DATABASE_URL=postgres://postgres:postgres@localhost:5432/{config.python_package_name}",
                    "ALLOWED_HOSTS=localhost,127.0.0.1",
                    "CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173",
                    "",
                ]
            )

        if config.use_redis:
            redis_url = (
                "redis://localhost:6379/0" if config.is_django_backend else "redis://localhost:6379"
            )
            lines.extend(
                [
                    "# Redis",
                    f"REDIS_URL={redis_url}",
                    "",
                ]
            )

        if config.use_celery:
            lines.extend(
                [
                    "# Celery",
                    "CELERY_BROKER_URL=redis://localhost:6379/0",
                    "CELERY_RESULT_BACKEND=redis://localhost:6379/0",
                    "",
                ]
            )

    if config.has_frontend:
        if config.is_nextjs:
            lines.extend(
                [
                    "# === Frontend (Next.js) ===",
                    f"NEXT_PUBLIC_API_BASE_URL={api_base}",
                    "NEXT_PUBLIC_AUTH_TOKEN_KEY=access_token",
                    "NEXT_PUBLIC_REFRESH_TOKEN_KEY=refresh_token",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "# === Frontend ===",
                    f"VITE_API_BASE_URL={api_base}",
                    "VITE_AUTH_TOKEN_KEY=access_token",
                    "VITE_REFRESH_TOKEN_KEY=refresh_token",
                    "",
                ]
            )

    lines.extend(
        [
            "# === Ports ===",
            f"API_PORT={api_port}",
            "FRONTEND_PORT=3000",
            "DB_PORT=5432",
            "REDIS_PORT=6379",
        ]
    )

    return "\n".join(lines) + "\n"


def generate_env_production_example(config: ProjectConfig) -> str:
    """Generate .env.production.example with production values."""
    lines: list[str] = [f"# Project: {config.display_name} (production)", ""]
    api_port = config.backend_api_port
    origin = "https://your-domain.com"

    if config.has_backend:
        if config.is_nestjs_backend:
            lines.extend(
                [
                    "# === Backend (NestJS) ===",
                    "NODE_ENV=production",
                    f"PORT={api_port}",
                    f"APP_NAME={config.display_name}",
                    f"APP_URL={origin}",
                    "",
                    f"POSTGRES_DB={config.python_package_name}",
                    "POSTGRES_USER=postgres",
                    "POSTGRES_PASSWORD=change-me-strong-password",
                    f"DATABASE_URL=postgresql://postgres:change-me-strong-password@db:5432/{config.python_package_name}",
                    "",
                    "JWT_SECRET=change-me-jwt-secret-at-least-32-chars",
                    "JWT_REFRESH_SECRET=change-me-refresh-secret-at-least-32-chars",
                    "",
                    f"CORS_ORIGINS={origin}",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "# === Backend (Django) ===",
                    "DEBUG=false",
                    "SECRET_KEY=change-me-strong-secret-key",
                    f"POSTGRES_DB={config.python_package_name}",
                    "POSTGRES_USER=postgres",
                    "POSTGRES_PASSWORD=change-me-strong-password",
                    # DB_* is what the Django settings read in every
                    # environment. DATABASE_URL alone leaves DATABASES empty.
                    f"DB_NAME={config.python_package_name}",
                    "DB_USER=postgres",
                    "DB_PASSWORD=change-me-strong-password",
                    "DB_HOST=db",
                    "DB_PORT=5432",
                    f"DATABASE_URL=postgres://postgres:change-me-strong-password@db:5432/{config.python_package_name}",
                    f"ALLOWED_HOSTS={origin.removeprefix('https://')}",
                    f"CORS_ALLOWED_ORIGINS={origin}",
                    "",
                ]
            )

        if config.use_redis:
            lines.extend(
                [
                    "# Redis",
                    "REDIS_URL=redis://redis:6379/0",
                    "",
                ]
            )

        if config.use_celery:
            lines.extend(
                [
                    "# Celery",
                    "CELERY_BROKER_URL=redis://redis:6379/0",
                    "CELERY_RESULT_BACKEND=redis://redis:6379/0",
                    "",
                ]
            )

    if config.has_frontend:
        api_base = f"{origin}/api/v1"
        if config.is_nextjs:
            lines.extend(
                [
                    "# === Frontend (Next.js) ===",
                    f"NEXT_PUBLIC_API_BASE_URL={api_base}",
                    "NEXT_PUBLIC_AUTH_TOKEN_KEY=access_token",
                    "NEXT_PUBLIC_REFRESH_TOKEN_KEY=refresh_token",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "# === Frontend ===",
                    f"VITE_API_BASE_URL={api_base}",
                    "VITE_AUTH_TOKEN_KEY=access_token",
                    "VITE_REFRESH_TOKEN_KEY=refresh_token",
                    "",
                ]
            )

    lines.extend(
        [
            "# === Ports ===",
            f"API_PORT={api_port}",
            "FRONTEND_PORT=80",
            "DB_PORT=5432",
            "REDIS_PORT=6379",
        ]
    )

    return "\n".join(lines) + "\n"
