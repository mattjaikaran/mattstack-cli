"""Dockerfile templates for the consolidated monorepo.

Dockerfiles are written to ``docker/backend/`` and ``docker/frontend/`` with the
repo root as build context, so each ``COPY`` path is prefixed with ``backend/``
or ``frontend/``.
"""

from __future__ import annotations

from mattstack.config import ProjectConfig


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
        return _nextjs_frontend()
    return _static_frontend()


def generate_frontend_dev_dockerfile(config: ProjectConfig) -> str:
    """Generate ``docker/frontend/Dockerfile.dev`` (development)."""
    return """\
FROM oven/bun:1
WORKDIR /app
COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile
COPY frontend/ .
EXPOSE 3000
CMD ["bun", "run", "dev", "--host"]
"""


def generate_frontend_nginx_conf() -> str:
    """Generate the nginx config that serves the built SPA with client routing."""
    return """\
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

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
COPY --from=builder /opt/venv /opt/venv
COPY backend/ .
RUN python manage.py collectstatic --noinput 2>/dev/null || true
EXPOSE {port}
CMD ["gunicorn", "{config.wsgi_app}.wsgi:application", \\
     "--bind", "0.0.0.0:{port}", "--workers", "3"]
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


def _static_frontend() -> str:
    return """\
FROM oven/bun:1 AS build
WORKDIR /app
COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile
COPY frontend/ .
RUN bun run build

FROM nginx:alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
"""


def _nextjs_frontend() -> str:
    return """\
FROM oven/bun:1 AS build
WORKDIR /app
COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile
COPY frontend/ .
RUN bun run build

FROM oven/bun:1 AS production
WORKDIR /app
COPY --from=build /app ./
ENV NODE_ENV=production
EXPOSE 3000
CMD ["bun", "run", "start"]
"""
