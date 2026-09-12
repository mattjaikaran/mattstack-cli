"""Render deployment config template."""

from __future__ import annotations

from mattstack.config import ProjectConfig


def generate_render_yaml(config: ProjectConfig) -> str:
    """Generate render.yaml Render Blueprint."""
    services: list[str] = []
    databases: list[str] = []
    env_groups: list[str] = []

    if config.has_backend:
        backend_service = f"""\
  - type: web
    name: {config.name}-api
    runtime: python
    region: oregon
    plan: starter
    buildCommand: pip install uv && uv sync
    startCommand: uv run gunicorn {config.django_package}.wsgi:application --bind 0.0.0.0:$PORT
    healthCheckPath: /api/health/
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: {config.name}-db
          property: connectionString
      - key: DJANGO_SECRET_KEY
        generateValue: true
      - key: DJANGO_SETTINGS_MODULE
        value: {config.django_package}.settings
      - key: ALLOWED_HOSTS
        value: .onrender.com"""

        if config.use_redis:
            backend_service += f"""
      - key: REDIS_URL
        fromService:
          name: {config.name}-redis
          type: redis
          property: connectionString"""

        if config.has_frontend:
            backend_service += """
      - key: CORS_ALLOWED_ORIGINS
        value: https://${RENDER_EXTERNAL_HOSTNAME}"""

        backend_service += """
      - fromGroup: shared-env"""

        services.append(backend_service)

        db_block = f"""\
  - name: {config.name}-db
    plan: starter
    ipAllowList: []"""
        databases.append(db_block)

    if config.use_redis:
        redis_service = f"""\
  - type: redis
    name: {config.name}-redis
    plan: starter
    ipAllowList: []
    maxmemoryPolicy: allkeys-lru"""
        services.append(redis_service)

    if config.use_celery:
        celery_worker = f"""\
  - type: worker
    name: {config.name}-celery-worker
    runtime: python
    buildCommand: pip install uv && uv sync
    startCommand: uv run celery -A {config.django_package} worker -l info
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: {config.name}-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          name: {config.name}-redis
          type: redis
          property: connectionString
      - fromGroup: shared-env"""
        services.append(celery_worker)

        celery_beat = f"""\
  - type: worker
    name: {config.name}-celery-beat
    runtime: python
    buildCommand: pip install uv && uv sync
    startCommand: uv run celery -A {config.django_package} beat -l info
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: {config.name}-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          name: {config.name}-redis
          type: redis
          property: connectionString
      - fromGroup: shared-env"""
        services.append(celery_beat)

    if config.has_frontend:
        frontend_service = f"""\
  - type: web
    name: {config.name}-frontend
    runtime: static
    buildCommand: cd frontend && bun install && bun run build
    staticPublishPath: frontend/dist
    headers:
      - path: /*
        name: X-Frame-Options
        value: SAMEORIGIN
    routes:
      - type: rewrite
        source: /*
        destination: /index.html"""
        services.append(frontend_service)

    env_groups.append("""\
  - name: shared-env
    envVars:
      - key: PYTHON_VERSION
        value: "3.12"
      - key: NODE_VERSION
        value: "20" """)

    # Assemble the full render.yaml
    parts: list[str] = []

    if services:
        services_block = "\n\n".join(services)
        parts.append(f"services:\n{services_block}")

    if databases:
        databases_block = "\n\n".join(databases)
        parts.append(f"databases:\n{databases_block}")

    if env_groups:
        env_groups_block = "\n\n".join(g.rstrip() for g in env_groups)
        parts.append(f"envGroups:\n{env_groups_block}")

    return "\n\n".join(parts) + "\n"
