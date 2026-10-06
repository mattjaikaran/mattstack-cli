"""Dockerfile templates for the consolidated monorepo.

Dockerfiles are written to ``docker/backend/`` and ``docker/frontend/`` with the
repo root as build context, so each ``COPY`` path is prefixed with ``backend/``
or ``frontend/``.

The backend ``production`` stage is the last stage, so providers that cannot
select a build target build it by default. It bakes the production mode
variables and starts through ``app-entrypoint``, which checks the runtime
contract (``deploy_runtime``) before any process starts.
"""

from __future__ import annotations

from pathlib import Path

from mattstack.config import ProjectConfig
from mattstack.runtime_profiles import task_backend_extra
from mattstack.templates.deploy_runtime import (
    ENTRYPOINT,
    ENTRYPOINT_FILE,
    ENTRYPOINT_PATH,
    production_mode_env,
)
from mattstack.templates.frontend_runtime import (
    PROD_API_SERVICE,
    api_prefix,
    browser_env,
    service_origin,
)
from mattstack.utils.versions import BUN_FALLBACK, UV_FALLBACK, bun_pin, read_versions

_PYTHON_FALLBACK = "3.13"  # When the cloned backend records no Python version.
_NGINX_IMAGE = "nginx:1.29-alpine"
# Bun's image has no curl or wget; a fetch exits 0 for any non-5xx response.
_NEXT_HEALTH = (
    '["bun", "-e", "fetch(\'http://127.0.0.1:3000/\')'
    '.then(r => process.exit(r.status < 500 ? 0 : 1), () => process.exit(1))"]'
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
FROM {bun_image(config.frontend_dir)}
WORKDIR /app
COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile
COPY frontend/ .
EXPOSE 3000
CMD ["bun", "run", "dev", {host_flag}]
"""


def generate_frontend_nginx_conf(config: ProjectConfig) -> str:
    """Generate the nginx template that serves the SPA and proxies the API.

    The official nginx image renders ``/etc/nginx/templates/*.template`` with
    the container environment at startup, substituting only ``${NAME}`` forms
    of defined variables, so nginx's own ``$uri`` and ``$host`` stay intact.
    With a backend, the production Dockerfile sets ``API_PREFIX`` and
    ``API_UPSTREAM``. A frontend-only project has no API to proxy.

    For Django, admin and uploaded media go to the API. ``/static/`` serves a
    bundle file when one exists (Rsbuild emits ``/static/js`` and
    ``/static/css``) and otherwise falls back to the API, where WhiteNoise
    serves the admin and app static files.
    """
    proxy = """\
        proxy_pass ${API_UPSTREAM};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $forwarded_proto;"""
    api_block = ""
    if config.has_backend:
        api_block = f"""
    # The SPA calls the API through a relative prefix, as in development.
    location ^~ ${{API_PREFIX}}/ {{
{proxy}
    }}
"""
    if config.has_backend and config.is_django_backend:
        api_block += f"""
    location = /admin {{
{proxy}
    }}

    location ^~ /admin/ {{
{proxy}
    }}

    location ^~ /media/ {{
{proxy}
    }}

    location ^~ /static/ {{
        try_files $uri @backend;
    }}

    location @backend {{
{proxy}
    }}
"""
    # Behind a TLS-terminating edge (Caddy, a platform router) nginx itself
    # receives HTTP; keep the edge's scheme so the backend sees https.
    forwarded = ""
    if config.has_backend:
        forwarded = """\
map $http_x_forwarded_proto $forwarded_proto {
    default $http_x_forwarded_proto;
    "" $scheme;
}

"""
    return f"""\
{forwarded}server {{
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;
{api_block}
    location / {{
        try_files $uri $uri/ /index.html;
    }}

    location /assets/ {{
        expires 1y;
        add_header Cache-Control "public, immutable";
    }}
}}
"""


def _uv_sync(config: ProjectConfig) -> str:
    """Install runtime dependencies, the selected extras, and any ``UV_EXTRAS``."""
    extras = [extra for extra in (task_backend_extra(config),) if extra]
    if config.use_ai:
        extras.append("ai")
    selected = "".join(f" --extra {extra}" for extra in extras)
    return (
        'ARG UV_EXTRAS=""\n'
        f"RUN uv sync --no-dev{selected} "
        """$(for extra in $UV_EXTRAS; do printf -- '--extra %s ' "$extra"; done)"""
    )


def _pin(config: ProjectConfig, key: str) -> str | None:
    """Return a version from the clone snapshot, else from the files on disk."""
    return config.source_pins.get(key) or read_versions(config.path).get(key)


def _uv_image(config: ProjectConfig) -> str:
    """Pin uv to the backend Dockerfile's version, else the fallback."""
    return f"ghcr.io/astral-sh/uv:{_pin(config, 'uv') or UV_FALLBACK}"


def _python_minor(config: ProjectConfig) -> str:
    """Return the backend's ``major.minor`` Python (``.python-version``, pyproject)."""
    parts = (_pin(config, "python") or "").split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else _PYTHON_FALLBACK


def bun_image(component: Path) -> str:
    """Pin Bun to ``packageManager`` in the component's package.json, else the fallback."""
    return f"oven/bun:{bun_pin(component) or BUN_FALLBACK}"


def _production_tail(config: ProjectConfig) -> str:
    """Install the entrypoint; ``serve`` starts the framework server on ``$PORT``."""
    return f"""\
COPY {ENTRYPOINT_FILE} {ENTRYPOINT_PATH}
RUN chmod 0755 {ENTRYPOINT_PATH}
EXPOSE {config.backend_api_port}
ENTRYPOINT ["{ENTRYPOINT}"]
CMD ["serve"]
"""


def _env_line(env: dict[str, str]) -> str:
    return "ENV " + " ".join(f"{key}={value}" for key, value in env.items())


def _python_base(config: ProjectConfig, build_packages: str) -> str:
    python = _python_minor(config)
    return f"""\
FROM python:{python}-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    UV_PROJECT_ENVIRONMENT=/opt/venv \\
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \\
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends {build_packages} \\
    && rm -rf /var/lib/apt/lists/*
COPY --from={_uv_image(config)} /uv /uvx /bin/
# Pin the interpreter to the image's Python. A permissive requires-python
# makes uv provision the newest release, and some wheels, such as
# pydantic-core, have no build for it.
ENV UV_PYTHON={python}
COPY backend/ .
# UV_PROJECT_ENVIRONMENT puts the environment at /opt/venv. Without it, uv
# creates /app/.venv and the runtime stages below copy an empty directory.
"""


def _django_backend(config: ProjectConfig) -> str:
    port = config.backend_api_port
    build_packages = "build-essential libpq-dev" + (" git" if config.is_django_matt else "")
    # Only Ninja's prod settings validate these keys during collectstatic.
    ninja_keys = (
        ""
        if config.is_django_matt
        else """\
    NINJA_JWT_SIGNING_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" \\
    CENTRIFUGO_TOKEN_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" \\
"""
    )
    return f"""\
{_python_base(config, build_packages)}{_uv_sync(config)}

FROM base AS development
COPY --from=builder /opt/venv /opt/venv
COPY --from={_uv_image(config)} /uv /uvx /bin/
COPY backend/ .
EXPOSE {port}
CMD ["python", "manage.py", "runserver", "0.0.0.0:{port}"]

FROM base AS production
{_env_line(production_mode_env(config))}
COPY --from=builder /opt/venv /opt/venv
COPY backend/ .
# Use transient build keys for settings validation, never runtime credentials.
RUN SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" \\
{ninja_keys}    python manage.py collectstatic --noinput
{_production_tail(config)}"""


def _fastapi_backend(config: ProjectConfig) -> str:
    port = config.backend_api_port
    return f"""\
{_python_base(config, "build-essential libpq-dev")}{_uv_sync(config)}

FROM base AS development
COPY --from=builder /opt/venv /opt/venv
COPY --from={_uv_image(config)} /uv /uvx /bin/
COPY backend/ .
EXPOSE {port}
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "{port}", "--reload"]

FROM base AS production
{_env_line(production_mode_env(config))}
COPY --from=builder /opt/venv /opt/venv
COPY backend/ .
{_production_tail(config)}"""


def _nestjs_backend(config: ProjectConfig) -> str:
    port = config.backend_api_port
    return f"""\
FROM {bun_image(config.backend_dir)} AS base
WORKDIR /app
COPY backend/package.json backend/bun.lock* ./
RUN bun install --frozen-lockfile

FROM base AS development
COPY backend/ .
EXPOSE {port}
CMD ["bun", "run", "start:dev"]

FROM base AS production
{_env_line(production_mode_env(config))}
COPY backend/ .
RUN bun run build
{_production_tail(config)}"""


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
    proxy_env = ""
    if config.has_backend:
        # nginx renders the template into conf.d/default.conf at startup.
        proxy_env = (
            f"ENV API_PREFIX={api_prefix(config)} \\\n"
            f"    API_UPSTREAM={service_origin(config, PROD_API_SERVICE)}\n"
        )
    return f"""\
FROM {bun_image(config.frontend_dir)} AS build
WORKDIR /app
COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile
COPY frontend/ .
{_browser_build_env(config)}RUN bun run build

FROM {_NGINX_IMAGE} AS production
# Run as the image's nginx user. The file capability keeps port 80, so
# Compose and the deployment recipes need no port change.
RUN apk add --no-cache libcap-setcap \\
    && setcap cap_net_bind_service=+ep /usr/sbin/nginx \\
    && sed -i -e '/^user /d' -e 's,^pid .*;,pid /tmp/nginx.pid;,' /etc/nginx/nginx.conf \\
    && chown -R nginx:nginx /var/cache/nginx /etc/nginx/conf.d
{proxy_env}COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/templates/default.conf.template
USER nginx
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\
    CMD wget -q --spider http://127.0.0.1/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
"""


def _nextjs_frontend(config: ProjectConfig) -> str:
    upstream = service_origin(config, PROD_API_SERVICE)
    return f"""\
FROM {bun_image(config.frontend_dir)} AS build
WORKDIR /app
# next.config.ts reads INTERNAL_API_URL for its API rewrite during the build.
ARG INTERNAL_API_URL={upstream}
ENV INTERNAL_API_URL=$INTERNAL_API_URL
COPY frontend/package.json frontend/bun.lock* ./
RUN bun install --frozen-lockfile
COPY frontend/ .
{_browser_build_env(config)}RUN bun run build

FROM {bun_image(config.frontend_dir)} AS production
WORKDIR /app
ARG INTERNAL_API_URL={upstream}
ENV NODE_ENV=production \\
    INTERNAL_API_URL=$INTERNAL_API_URL
COPY --from=build --chown=bun:bun /app ./
USER bun
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\
    CMD {_NEXT_HEALTH}
CMD ["bun", "run", "start"]
"""
