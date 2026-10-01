"""Dockerfile templates for the consolidated monorepo.

Dockerfiles are written to ``docker/backend/`` and ``docker/frontend/`` with the
repo root as build context, so each ``COPY`` path is prefixed with ``backend/``
or ``frontend/``.
"""

from __future__ import annotations

from mattstack.config import ProjectConfig
from mattstack.templates.frontend_runtime import (
    PROD_API_SERVICE,
    api_prefix,
    browser_env,
    service_origin,
)


def generate_dockerignore() -> str:
    """Keep secrets and host build artifacts outside the root build context."""
    return """\
**/.git
**/.venv
**/node_modules
**/__pycache__
**/*.pyc
**/.pytest_cache
**/.mypy_cache
**/.ruff_cache
**/.coverage*
**/htmlcov
**/.next
**/dist
**/staticfiles
**/.env
**/.env.*
**/.npmrc
**/.pypirc
**/.netrc
**/.ssh
"""


def generate_backend_dockerfile(config: ProjectConfig) -> str:
    """Generate ``docker/backend/Dockerfile`` with development + production targets."""
    if config.is_nestjs_backend:
        return _nestjs_backend(config)
    if config.is_fastapi_backend:
        return _fastapi_backend(config)
    return _django_backend(config)


def generate_frontend_dockerfile(config: ProjectConfig) -> str:
    """Generate ``docker/frontend/Dockerfile`` (production)."""
    if config.is_nextjs:
        return _nextjs_frontend(config)
    return _static_frontend(config)


def generate_frontend_dev_dockerfile(config: ProjectConfig) -> str:
    """Generate ``docker/frontend/Dockerfile.dev`` (development).

    The dev server must listen on all interfaces to be reachable through the
    published port. Next.js spells the flag ``-H``; Vite and Rsbuild ``--host``.
    """
    host_flag = '"-H", "0.0.0.0"' if config.is_nextjs else '"--host", "0.0.0.0"'
    return f"""\
FROM oven/bun:1
WORKDIR /app
COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile
COPY frontend/ .
EXPOSE 3000
CMD ["bun", "run", "dev", {host_flag}]
"""


def generate_frontend_nginx_conf() -> str:
    """Generate the nginx template that serves the SPA and proxies the API.

    The official nginx image renders ``/etc/nginx/templates/*.template`` with
    the container environment at startup, substituting only ``${NAME}`` forms
    of defined variables, so nginx's own ``$uri`` and ``$host`` stay intact.
    The production Dockerfile sets ``API_PREFIX`` and ``API_UPSTREAM``.
    """
    return """\
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # The SPA calls the API through a relative prefix, as in development.
    location ^~ ${API_PREFIX}/ {
        proxy_pass ${API_UPSTREAM};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
"""


def _django_backend(config: ProjectConfig) -> str:
    port = config.backend_api_port
    build_packages = "build-essential libpq-dev" + (" git" if config.is_django_matt else "")
    # Ninja settings also read ENVIRONMENT for logging and the S3 media branch.
    production_env = "DJANGO_ENVIRONMENT=production" + (
        "" if config.is_django_matt else " ENVIRONMENT=production"
    )
    if config.is_django_matt:
        production_command = (
            f'CMD ["granian", "--interface", "asgi", "{config.wsgi_app}.asgi:application", '
            f'"--host", "0.0.0.0", "--port", "{port}", "--workers", "3"]'
        )
    else:
        production_command = (
            f'CMD ["gunicorn", "{config.wsgi_app}.wsgi:application", '
            f'"--bind", "0.0.0.0:{port}", "--workers", "3"]'
        )
    return f"""\
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    UV_PROJECT_ENVIRONMENT=/opt/venv \\
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \\
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends {build_packages} \\
    && curl -LsSf https://astral.sh/uv/install.sh | sh \\
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.local/bin:$PATH"
# Pin the interpreter to the image's Python. The backend allows >=3.13, so
# without this uv provisions the newest release and some wheels, such as
# pydantic-core, have no build for it.
ENV UV_PYTHON=3.13
COPY backend/ .
# UV_PROJECT_ENVIRONMENT puts the environment at /opt/venv. Without it, uv
# creates /app/.venv and the runtime stages below copy an empty directory.
RUN uv sync --no-dev

FROM base AS development
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /root/.local/bin/uv /usr/local/bin/uv
COPY backend/ .
EXPOSE {port}
CMD ["python", "manage.py", "runserver", "0.0.0.0:{port}"]

FROM base AS production
ENV {production_env} DEBUG=false
COPY --from=builder /opt/venv /opt/venv
COPY backend/ .
# Use transient build keys for settings validation, never runtime credentials.
RUN SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" \\
    NINJA_JWT_SIGNING_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" \\
    CENTRIFUGO_TOKEN_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" \\
    python manage.py collectstatic --noinput
EXPOSE {port}
{production_command}
"""


def _fastapi_backend(config: ProjectConfig) -> str:
    port = config.backend_api_port
    return f"""\
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    UV_PROJECT_ENVIRONMENT=/opt/venv \\
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \\
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev \\
    && curl -LsSf https://astral.sh/uv/install.sh | sh \\
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.local/bin:$PATH"
# Pin the interpreter to the image's Python. A permissive requires-python
# makes uv provision the newest release, which may have no wheel.
ENV UV_PYTHON=3.13
COPY backend/ .
# UV_PROJECT_ENVIRONMENT puts the environment at /opt/venv. Without it, uv
# creates /app/.venv and the runtime stages below copy an empty directory.
RUN uv sync --no-dev

FROM base AS development
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /root/.local/bin/uv /usr/local/bin/uv
COPY backend/ .
EXPOSE {port}
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "{port}", "--reload"]

FROM base AS production
COPY --from=builder /opt/venv /opt/venv
COPY backend/ .
EXPOSE {port}
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "{port}", "--workers", "4"]
"""


def _nestjs_backend(config: ProjectConfig) -> str:
    port = config.backend_api_port
    return f"""\
FROM oven/bun:1 AS base
WORKDIR /app
COPY backend/package.json backend/bun.lock* ./
RUN bun install --frozen-lockfile

FROM base AS development
COPY backend/ .
EXPOSE {port}
CMD ["bun", "run", "start:dev"]

FROM base AS production
COPY backend/ .
RUN bun run build
EXPOSE {port}
CMD ["bun", "run", "start"]
"""


def _browser_build_env(config: ProjectConfig) -> str:
    """Return ARG/ENV lines that fix the browser's API base at build time.

    The bundler inlines these values. Do not rely on ``frontend/.env``: the
    root ``.gitignore`` excludes it, so a fresh clone builds without it and
    the app falls back to the boilerplate's absolute localhost URL. Compose
    passes the same names as build args, so one override changes both.
    """
    if not config.has_backend:
        return ""
    env = browser_env(config)
    args = "".join(f"ARG {key}={value}\n" for key, value in env.items())
    exports = " \\\n    ".join(f"{key}=${key}" for key in env)
    return f"{args}ENV {exports}\n"


def _static_frontend(config: ProjectConfig) -> str:
    upstream = service_origin(config, PROD_API_SERVICE)
    return f"""\
FROM oven/bun:1 AS build
WORKDIR /app
COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile
COPY frontend/ .
{_browser_build_env(config)}RUN bun run build

FROM nginx:alpine AS production
# nginx renders the template into conf.d/default.conf at startup.
ENV API_PREFIX={api_prefix(config)} \\
    API_UPSTREAM={upstream}
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/templates/default.conf.template
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
"""


def _nextjs_frontend(config: ProjectConfig) -> str:
    upstream = service_origin(config, PROD_API_SERVICE)
    return f"""\
FROM oven/bun:1 AS build
WORKDIR /app
# next.config.ts reads INTERNAL_API_URL for its API rewrite during the build.
ARG INTERNAL_API_URL={upstream}
ENV INTERNAL_API_URL=$INTERNAL_API_URL
COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile
COPY frontend/ .
{_browser_build_env(config)}RUN bun run build

FROM oven/bun:1 AS production
WORKDIR /app
ARG INTERNAL_API_URL={upstream}
ENV NODE_ENV=production \\
    INTERNAL_API_URL=$INTERNAL_API_URL
COPY --from=build /app ./
EXPOSE 3000
CMD ["bun", "run", "start"]
"""
