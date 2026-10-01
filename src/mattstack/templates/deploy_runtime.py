"""Production runtime contract shared by the backend image and the provider configs.

The backend image bakes the production mode variables and checks every other
required variable at startup (see ``backend_entrypoint``). Provider templates
read the same requirements, so a provider config and the startup check cannot
disagree about what production needs.

Each requirement comes from the boilerplate settings:

- django-ninja ``api/settings/common.py`` reads ``DB_*`` (not ``DATABASE_URL``),
  ``REDIS_URL`` with a Compose-only ``valkey`` default, and ``CENTRIFUGO_*``;
  ``api/settings/prod.py`` rejects a missing or ``SECRET_KEY``-equal
  ``NINJA_JWT_SIGNING_KEY`` and the default ``CENTRIFUGO_TOKEN_SECRET``.
- django-matt-starter ``config/settings.py`` reads ``DB_*`` with
  ``postgres``/``localhost`` defaults, ``SECRET_KEY`` with a
  ``change-me-in-production`` default, and ``DEBUG`` with a ``True`` default.
- fastapi-boilerplate ``app/config/settings.py`` requires ``SECRET_KEY`` and
  ``JWT_SECRET_KEY`` of 32+ characters and reads an asyncpg ``DATABASE_URL``.
- nestjs-boilerplate ``src/config/env.validation.ts`` requires
  ``DATABASE_URL`` and 16+ character ``JWT_SECRET``/``JWT_REFRESH_SECRET``.
"""

from __future__ import annotations

from dataclasses import dataclass

from mattstack.config import DeploymentTarget, MediaStorage, ProjectConfig
from mattstack.runtime_profiles import task_backend_env
from mattstack.templates.frontend_runtime import api_prefix

BACKEND_DOCKERFILE = "docker/backend/Dockerfile"
FRONTEND_DOCKERFILE = "docker/frontend/Dockerfile"
ENTRYPOINT_FILE = "docker/backend/entrypoint.sh"
ENTRYPOINT = "app-entrypoint"
ENTRYPOINT_PATH = f"/usr/local/bin/{ENTRYPOINT}"
MIGRATE_COMMAND = f"{ENTRYPOINT} migrate"
SERVE_COMMAND = f"{ENTRYPOINT} serve"
CHECK_COMMAND = f"{ENTRYPOINT} check"
PLACEHOLDER_PREFIX = "change-me"

_DB_WHY = "Django builds DATABASES from DB_*; it does not read DATABASE_URL."


@dataclass(frozen=True)
class EnvRequirement:
    """One variable the production backend needs from the operator."""

    name: str
    why: str
    secret: bool = False
    web_only: bool = False
    min_length: int = 0
    prefixes: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()


def production_mode_env(config: ProjectConfig) -> dict[str, str]:
    """Return the mode variables the production image bakes and the check enforces."""
    if config.is_nestjs_backend:
        return {"NODE_ENV": "production"}
    if config.is_fastapi_backend:
        return {"APP_ENV": "production"}
    if config.is_django_matt:
        return {"DEBUG": "false"}
    # Ninja selects api.settings.prod from DJANGO_ENVIRONMENT; logging and the
    # S3 media branch read ENVIRONMENT. Both must say production.
    env = {"DJANGO_ENVIRONMENT": "production", "ENVIRONMENT": "production", "DEBUG": "false"}
    env.update(task_backend_env(config))
    return env


def tls_env(config: ProjectConfig) -> dict[str, str]:
    """Return the web settings for a target that always serves HTTPS at its edge.

    Ninja's api/settings/prod.py enables the HTTPS redirect, HSTS, secure
    cookies, and trusts ``X-Forwarded-Proto: https`` only when USE_TLS=true.
    ``docker`` serves plain HTTP. On ``aws`` the load balancer may have only
    an HTTP listener (Copilot's default, or an operator ALB on :80), where the
    redirect points at nothing; set USE_TLS=true there once HTTPS exists.
    The other backends do not read USE_TLS.
    """
    ninja = config.is_django_backend and not config.is_django_matt
    if not ninja or config.deployment in _PLAIN_HTTP_POSSIBLE:
        return {}
    return {"USE_TLS": "true"}


_PLAIN_HTTP_POSSIBLE = (DeploymentTarget.DOCKER, DeploymentTarget.AWS)


def required_env(config: ProjectConfig) -> tuple[EnvRequirement, ...]:
    """Return the variables an operator must supply, in a stable order."""
    if config.is_nestjs_backend:
        return _nestjs_env()
    if config.is_fastapi_backend:
        return _fastapi_env(config)
    if config.is_django_matt:
        return (
            *_django_db_env(),
            EnvRequirement("SECRET_KEY", "Django signs sessions and tokens with it.", secret=True),
            _allowed_hosts(),
        )
    return _ninja_env(config)


def distinct_secrets(config: ProjectConfig) -> tuple[str, ...]:
    """Return the secrets that must all hold different values."""
    if config.is_nestjs_backend:
        return ("JWT_SECRET", "JWT_REFRESH_SECRET")
    if config.is_fastapi_backend:
        return ("SECRET_KEY", "JWT_SECRET_KEY")
    if config.is_django_matt:
        return ()
    return ("SECRET_KEY", "NINJA_JWT_SIGNING_KEY", "CENTRIFUGO_TOKEN_SECRET")


def health_path(config: ProjectConfig) -> str:
    """Return the unauthenticated liveness route each backend defines."""
    prefix = api_prefix(config)
    if config.is_nestjs_backend:
        # main.ts: setGlobalPrefix('api') plus URI versioning, default version 1.
        return f"{prefix}/v1/health"
    if config.is_fastapi_backend:
        return f"{prefix}/health/live"
    if config.is_django_matt:
        return f"{prefix}/health"
    return f"{prefix}/health/"


def edge_backend_paths(config: ProjectConfig) -> list[str]:
    """Return the paths an edge router sends to the API in front of Next.js.

    Next.js rewrites only the API prefix, so the edge also routes the Django
    admin, static (WhiteNoise serves admin and app assets), and media paths.
    Next.js serves its own bundles from ``/_next``. The static frontend image
    proxies all of these itself (``generate_frontend_nginx_conf``), so an
    edge in front of it sends everything to the frontend.
    """
    paths = [api_prefix(config)]
    if config.is_django_backend:
        paths.extend(["/admin", "/static", "/media"])
    return paths


def api_service(config: ProjectConfig) -> str:
    return f"{config.name}-api"


def set_instruction(config: ProjectConfig, name: str) -> str:
    """Return the exact command or location that sets ``name`` for the target."""
    app = config.name
    api = api_service(config)
    target = config.deployment
    if name == "USE_TLS" and tls_env(config):
        recipe = _TLS_RECIPE_FILES[target]
        return f"restore USE_TLS=true in the API environment in {recipe}"
    if target == DeploymentTarget.RAILWAY:
        return f"printf '%s' '<value>' | railway variable set --service {api} --stdin {name}"
    if target == DeploymentTarget.RENDER:
        return f"Render Dashboard > {api} > Environment: set {name} (render.yaml: sync: false)"
    if target == DeploymentTarget.FLY_IO:
        return f"fly secrets set {name}='<value>' --app {app}"
    if target == DeploymentTarget.DIGITAL_OCEAN:
        return (
            f"add {name} to the app-level envs in .do/app.yaml, then run: "
            "doctl apps update <app-id> --spec .do/app.yaml"
        )
    if target == DeploymentTarget.AWS:
        return (
            f"aws ssm put-parameter --name /{app}/production/{name} --type SecureString "
            f"--value '<value>' (Copilot: copilot secret init --name {name})"
        )
    if target == DeploymentTarget.GCP:
        return f"printf '%s' '<value>' | gcloud secrets create {app}-{name} --data-file=-"
    # docker-compose.prod.yml derives DB_NAME/DB_USER/DB_PASSWORD from POSTGRES_*.
    source = _COMPOSE_DB_SOURCES.get(name, name)
    return f"set {source}=<value> in .env.production"


_COMPOSE_DB_SOURCES = {
    "DB_NAME": "POSTGRES_DB",
    "DB_USER": "POSTGRES_USER",
    # Compose variable name, not a credential value.
    "DB_PASSWORD": "POSTGRES_PASSWORD",  # nosec B105
}


def verify_command(config: ProjectConfig) -> str:
    """Return a local command that runs the same startup check without deploying."""
    if config.deployment in _COMPOSE_TARGETS:
        return f"{compose_command(config)} run --rm --no-deps api check"
    image = f"{api_service(config)}:check"
    mode = "".join(f" -e {name}={value}" for name, value in tls_env(config).items())
    return (
        f"docker build -f {BACKEND_DOCKERFILE} -t {image} . && "
        f"docker run --rm --env-file .env.production{mode} {image} check"
    )


_COMPOSE_TARGETS = (
    DeploymentTarget.DOCKER,
    DeploymentTarget.CLOUDFLARE,
    DeploymentTarget.HETZNER,
    DeploymentTarget.SELF_HOSTED,
)


_TLS_RECIPE_FILES = {
    DeploymentTarget.RAILWAY: ".railway/railway.ts",
    DeploymentTarget.RENDER: "render.yaml",
    DeploymentTarget.FLY_IO: "fly.toml",
    DeploymentTarget.DIGITAL_OCEAN: ".do/app.yaml",
    DeploymentTarget.GCP: "service.yaml",
    DeploymentTarget.HETZNER: "docker-compose.caddy.yml",
    DeploymentTarget.CLOUDFLARE: "docker-compose.caddy.yml",
    DeploymentTarget.SELF_HOSTED: "docker-compose.nginx.yml",
}


def compose_command(config: ProjectConfig) -> str:
    """Return the Compose invocation for the target's production stack."""
    files = "-f docker-compose.prod.yml"
    if config.deployment in (DeploymentTarget.HETZNER, DeploymentTarget.CLOUDFLARE):
        # Cloudflare Pages needs an HTTPS API origin; Caddy terminates TLS.
        files += " -f docker-compose.caddy.yml"
    elif config.deployment == DeploymentTarget.SELF_HOSTED:
        files += " -f docker-compose.nginx.yml"
    return f"docker compose {files} --env-file .env.production"


def _allowed_hosts() -> EnvRequirement:
    return EnvRequirement(
        "ALLOWED_HOSTS",
        "With DEBUG off, Django answers 400 to every host not listed here.",
        web_only=True,
    )


def _django_db_env() -> tuple[EnvRequirement, ...]:
    return (
        EnvRequirement("DB_NAME", _DB_WHY),
        EnvRequirement("DB_USER", _DB_WHY),
        EnvRequirement("DB_PASSWORD", _DB_WHY, secret=True),
        EnvRequirement("DB_HOST", _DB_WHY),
        EnvRequirement("DB_PORT", _DB_WHY),
    )


def _ninja_env(config: ProjectConfig) -> tuple[EnvRequirement, ...]:
    reqs = [
        *_django_db_env(),
        EnvRequirement(
            "SECRET_KEY", "api/settings/prod.py refuses an empty SECRET_KEY.", secret=True
        ),
        EnvRequirement(
            "NINJA_JWT_SIGNING_KEY",
            "api/settings/prod.py requires a JWT signing key distinct from SECRET_KEY.",
            secret=True,
        ),
        EnvRequirement(
            "CENTRIFUGO_TOKEN_SECRET",
            "api/settings/prod.py rejects the default realtime token secret.",
            secret=True,
            rejected=("centrifugo-token-secret", "dev-centrifugo-token-secret"),
        ),
        EnvRequirement(
            "REDIS_URL",
            "The cache, sessions, and throttles use it; the default host exists only in Compose.",
        ),
    ]
    if config.use_realtime:
        reqs.extend(
            [
                EnvRequirement(
                    "CENTRIFUGO_URL",
                    "Realtime publishes to Centrifugo; the default host exists only in Compose.",
                ),
                EnvRequirement(
                    "CENTRIFUGO_API_KEY",
                    "Realtime authenticates to the Centrifugo API with it.",
                    secret=True,
                    rejected=("centrifugo-api-key",),
                ),
            ]
        )
    if config.media_storage == MediaStorage.S3:
        s3_why = "Media storage is S3; ENVIRONMENT=production enables the S3 branch."
        reqs.extend(
            [
                EnvRequirement("AWS_STORAGE_BUCKET_NAME", s3_why),
                EnvRequirement("AWS_ACCESS_KEY_ID", s3_why, secret=True),
                EnvRequirement("AWS_SECRET_ACCESS_KEY", s3_why, secret=True),
            ]
        )
    reqs.append(_allowed_hosts())
    return tuple(reqs)


def _fastapi_env(config: ProjectConfig) -> tuple[EnvRequirement, ...]:
    reqs = [
        EnvRequirement(
            "DATABASE_URL",
            "SQLAlchemy uses the asyncpg driver; the default points at localhost.",
            secret=True,
            prefixes=("postgresql+asyncpg://",),
        ),
        EnvRequirement(
            "SECRET_KEY", "Settings require at least 32 characters.", secret=True, min_length=32
        ),
        EnvRequirement(
            "JWT_SECRET_KEY",
            "Settings require at least 32 characters.",
            secret=True,
            min_length=32,
        ),
        # validate_production_settings rejects these defaults when APP_ENV=production.
        EnvRequirement(
            "WEBAUTHN_RP_ID",
            "Production rejects localhost; set the production domain.",
            rejected=("localhost", "127.0.0.1"),
        ),
        EnvRequirement(
            "WEBAUTHN_ORIGIN",
            "Production requires an https:// origin.",
            prefixes=("https://",),
        ),
    ]
    if config.use_redis:
        reqs.append(EnvRequirement("REDIS_URL", "The default points at localhost."))
    if config.use_celery:
        reqs.extend(
            [
                EnvRequirement("CELERY_BROKER_URL", "The default points at localhost."),
                EnvRequirement("CELERY_RESULT_BACKEND", "The default points at localhost."),
            ]
        )
    # main.py passes CORS_ORIGINS to CORSMiddleware; pydantic-settings parses
    # list fields from JSON, e.g. ["https://app.example.com"]. The app never
    # reads ALLOWED_HOSTS, so it is not required.
    reqs.append(
        EnvRequirement(
            "CORS_ORIGINS",
            "A JSON list; the default allows only http://localhost:3000.",
            web_only=True,
            prefixes=("[",),
        )
    )
    return tuple(reqs)


def _nestjs_env() -> tuple[EnvRequirement, ...]:
    jwt_why = "env.validation.ts requires at least 16 characters."
    return (
        EnvRequirement(
            "DATABASE_URL",
            "env.validation.ts requires a postgres URL.",
            secret=True,
            prefixes=("postgresql://", "postgres://"),
        ),
        EnvRequirement("JWT_SECRET", jwt_why, secret=True, min_length=16),
        EnvRequirement("JWT_REFRESH_SECRET", jwt_why, secret=True, min_length=16),
        EnvRequirement("REDIS_URL", "Bull queues connect to it; the default is localhost."),
    )
