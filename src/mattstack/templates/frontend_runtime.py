"""Frontend runtime contract shared by the generated config, env, and Compose files.

The browser always calls the API through a relative prefix, so the same build
works on the host, in the ``frontend-dev`` container, and behind nginx. The dev
server proxies that prefix to the backend. Only the proxy target changes: the
host uses ``localhost`` and the container uses the ``api-dev`` service.

Each boilerplate reads a different variable for the API base URL:

- ``react-vite-boilerplate``: ``VITE_API_BASE_URL``
- ``react-vite-starter``: ``VITE_API_URL``
- the Rsbuild boilerplates: ``PUBLIC_API_URL``
- ``nextjs-starter``: ``NEXT_PUBLIC_API_BASE_URL``; its ``next.config.ts``
  rewrites the API prefix to ``INTERNAL_API_URL``.
"""

from __future__ import annotations

from mattstack.config import FrontendFramework, ProjectConfig

# Port the dev server listens on inside the container and by default on the
# host. Compose publishes it on ${FRONTEND_PORT:-3000}.
FRONTEND_PORT = 3000

# Compose service names that the frontend proxy reaches over the network.
DEV_API_SERVICE = "api-dev"
PROD_API_SERVICE = "api"

_API_BASE_VAR: dict[FrontendFramework, str] = {
    FrontendFramework.REACT_VITE: "VITE_API_BASE_URL",
    FrontendFramework.REACT_VITE_STARTER: "VITE_API_URL",
    FrontendFramework.REACT_RSBUILD: "PUBLIC_API_URL",
    FrontendFramework.REACT_RSBUILD_KIBO: "PUBLIC_API_URL",
    FrontendFramework.NEXTJS: "NEXT_PUBLIC_API_BASE_URL",
}

RSBUILD_FRAMEWORKS = (FrontendFramework.REACT_RSBUILD, FrontendFramework.REACT_RSBUILD_KIBO)
VITE_FRAMEWORKS = (FrontendFramework.REACT_VITE, FrontendFramework.REACT_VITE_STARTER)


def api_prefix(config: ProjectConfig) -> str:
    """Return the backend API mount as ``/segment`` without a trailing slash."""
    prefix = "/" + config.api_prefix.strip("/")
    return prefix if prefix != "/" else "/api"


def api_base_env_var(config: ProjectConfig) -> str:
    """Return the variable the frontend reads for the API base URL."""
    return _API_BASE_VAR[config.frontend_framework]


def proxy_target_env_var(config: ProjectConfig) -> str:
    """Return the variable the dev server reads for the backend origin."""
    return "INTERNAL_API_URL" if config.is_nextjs else "API_PROXY_TARGET"


def service_origin(config: ProjectConfig, service: str) -> str:
    """Return the backend origin on the Compose network."""
    return f"http://{service}:{config.backend_api_port}"


def proxy_paths(config: ProjectConfig) -> list[str]:
    """Return the path prefixes the dev server forwards to the backend."""
    paths = [api_prefix(config)]
    if config.is_django_backend:
        # Admin pages and their assets. Do not proxy all of /static: Rsbuild
        # serves its own bundles from /static/js and /static/css.
        paths.extend(["/admin", "/static/admin", "/media"])
    return paths


def browser_env(config: ProjectConfig) -> dict[str, str]:
    """Return the non-secret browser variables for a frontend with a backend."""
    prefix = api_prefix(config)
    framework = config.frontend_framework
    env = {api_base_env_var(config): prefix}
    if framework == FrontendFramework.REACT_VITE:
        env.update(
            {
                "VITE_AUTH_STORAGE_KEY": "access_token",  # Public storage name, not a credential.
                "VITE_AUTH_REFRESH_STORAGE_KEY": "refresh_token",  # Public storage name.
            }
        )
        if config.is_django_backend:
            env.update(
                {
                    "VITE_MODE": "django-spa",
                    "VITE_DJANGO_CSRF_COOKIE_NAME": "csrftoken",  # Public cookie name.
                    "VITE_DJANGO_STATIC_URL": "/static/",
                    "VITE_DJANGO_MEDIA_URL": "/media/",
                    "VITE_DJANGO_API_PREFIX": prefix,
                }
            )
    elif framework == FrontendFramework.NEXTJS:
        env.update(
            {
                "NEXT_PUBLIC_AUTH_TOKEN_KEY": "access_token",  # nosec B105 # Public key name, not a secret.
                "NEXT_PUBLIC_AUTH_REFRESH_TOKEN_KEY": "refresh_token",  # nosec B105 # Public key name, not a secret.
            }
        )
        if config.is_django_backend:
            env.update(
                {
                    "NEXT_PUBLIC_MODE": "django-spa",
                    "NEXT_PUBLIC_DJANGO_CSRF_TOKEN_NAME": "csrftoken",  # nosec B105 # Public key name, not a secret.
                    "NEXT_PUBLIC_DJANGO_STATIC_URL": "/static/",
                    "NEXT_PUBLIC_DJANGO_MEDIA_URL": "/media/",
                    "NEXT_PUBLIC_DJANGO_API_PREFIX": prefix,
                }
            )
    return env


def render_env_file(values: dict[str, str]) -> str:
    """Render ``KEY=value`` lines for a dotenv file."""
    return "".join(f"{key}={value}\n" for key, value in values.items())
