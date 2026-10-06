"""Centrifugo Compose service for projects generated with ``--realtime``.

Mirrors the django-ninja boilerplate's ``realtime`` profile: the
``centrifugo/centrifugo:v5`` image reads ``backend/deploy/centrifugo/config.json``
for its namespaces. Centrifugo does not expand ``${...}`` inside that file; it
reads environment variables named after its own keys, and they override the
file. Compose therefore passes the signing key and API key from the env file,
turns the admin UI off (the file's admin password is a published default), and
points the Redis engine at this project's ``redis`` service.
"""

from __future__ import annotations

from mattstack.runtime_profiles import (
    CENTRIFUGO_CONFIG,
    CENTRIFUGO_CONTAINER_PORT,
    CENTRIFUGO_IMAGE,
    CENTRIFUGO_PORT,
    CENTRIFUGO_SERVICE,
    REALTIME_PROFILE,
)
from mattstack.templates.compose_env import redis_url, render_mapping, required
from mattstack.templates.frontend_runtime import FRONTEND_PORT


def centrifugo_service(*, production: bool) -> str:
    """Render ``centrifugo``; dev starts it only with ``--profile realtime``."""
    env_file = ".env.production" if production else ".env"
    origins = (
        required("CENTRIFUGO_ALLOWED_ORIGINS", env_file)
        if production
        else f"http://localhost:${{FRONTEND_PORT:-{FRONTEND_PORT}}}"
    )
    env = {
        "CENTRIFUGO_TOKEN_HMAC_SECRET_KEY": required("CENTRIFUGO_TOKEN_SECRET", env_file),
        "CENTRIFUGO_API_KEY": required("CENTRIFUGO_API_KEY", env_file),
        "CENTRIFUGO_ADMIN": "false",
        "CENTRIFUGO_ALLOWED_ORIGINS": origins,
        # Admin stays off; generated values keep a later opt-in from using defaults.
        "CENTRIFUGO_ADMIN_PASSWORD": "${CENTRIFUGO_ADMIN_PASSWORD:-}",  # nosec B105 # Env reference.
        "CENTRIFUGO_ADMIN_SECRET": "${CENTRIFUGO_ADMIN_SECRET:-}",  # nosec B105 # Env reference.
        "CENTRIFUGO_REDIS_ADDRESS": f"{redis_url('redis', production=production)}/1",
    }
    bind = "" if production else "127.0.0.1:"
    tail = (
        "\n    restart: unless-stopped"
        if production
        else f"\n    profiles:\n      - {REALTIME_PROFILE}"
    )
    return f"""\
  {CENTRIFUGO_SERVICE}:
    image: {CENTRIFUGO_IMAGE}
    command: centrifugo -c config.json
    volumes:
      - ./backend/{CENTRIFUGO_CONFIG}:/centrifugo/config.json:ro
    ports:
      - "{bind}${{CENTRIFUGO_PORT:-{CENTRIFUGO_PORT}}}:{CENTRIFUGO_CONTAINER_PORT}"
    environment:
{render_mapping(env, indent=6)}
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:{CENTRIFUGO_CONTAINER_PORT}/health"]
      interval: 10s
      timeout: 5s
      retries: 5{tail}"""
