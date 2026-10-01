"""Exempt the public health routes from the HTTPS redirect in a cloned Ninja backend.

With ``USE_TLS=true``, ``api/settings/prod.py`` redirects every plain-HTTP
request to HTTPS. Platform health checks that cannot send
``X-Forwarded-Proto: https`` (Railway accepts only 2xx) then fail. The
django-ninja-boilerplate source exempts the public routes of
``api/healthcheck.py``; until a published release carries that change, apply
the same block to the clone. Host validation (ALLOWED_HOSTS) is unchanged.
Parsers use regex anchors on the observed source; a missing anchor fails with
the file to fix instead of guessing.
"""

from __future__ import annotations

import re

from mattstack.config import BackendFramework, ProjectConfig
from mattstack.utils.console import print_info

# Kept identical to django-ninja-boilerplate api/settings/prod.py.
EXEMPT_BLOCK = """\
    # Platform health checks call the container over plain HTTP without
    # X-Forwarded-Proto, so a redirect would mark the deployment unhealthy.
    # Exempt only the public, I/O-free and readiness routes of
    # api.healthcheck; staff-only detail routes still redirect. Patterns match
    # request.path without its leading slash.
    SECURE_REDIRECT_EXEMPT = [
        r"^api/health/$",
        r"^api/health/liveness$",
        r"^api/health/readiness$",
    ]
"""

_TLS_BLOCK = re.compile(
    r"(^if USE_TLS:\n(?:    [^\n]*\n)*?"
    r"    SECURE_PROXY_SSL_HEADER = \(\"HTTP_X_FORWARDED_PROTO\", \"https\"\)\n)",
    re.MULTILINE,
)
_HEALTH_CONTROLLER = re.compile(r'@api_controller\("/health"')
_LIVENESS = re.compile(r'@http_get\("/liveness"')
_READINESS = re.compile(r'@http_get\("/readiness"')
_API_MOUNT = re.compile(r'path\("api/", api\.urls\)')


def _layout_error(rel: str, detail: str) -> ValueError:
    return ValueError(
        f"backend/{rel} {detail}, so mattstack cannot exempt the health routes from "
        f"the USE_TLS redirect; plain-HTTP platform health checks would get 301. Add "
        f"SECURE_REDIRECT_EXEMPT for the public health routes to the USE_TLS block "
        f"of backend/api/settings/prod.py by hand. "
        f"Verify: grep -n SECURE_REDIRECT_EXEMPT backend/api/settings/prod.py"
    )


def ensure_health_redirect_exempt(config: ProjectConfig) -> list[str]:
    """Add the health-route redirect exemption; return the changed files.

    Does nothing for other backends or when prod.py already sets
    SECURE_REDIRECT_EXEMPT. Raises ValueError naming the file whose layout
    does not match, before writing anything.
    """
    if config.backend_framework != BackendFramework.DJANGO_NINJA or not config.has_backend:
        return []
    backend = config.backend_dir
    prod = backend / "api" / "settings" / "prod.py"
    if not prod.is_file():
        raise _layout_error("api/settings/prod.py", "is missing")
    text = prod.read_text(encoding="utf-8")
    if "SECURE_REDIRECT_EXEMPT" in text:
        return []
    match = _TLS_BLOCK.search(text)
    if match is None:
        raise _layout_error("api/settings/prod.py", "has no `if USE_TLS:` proxy-header block")

    # The patterns are only correct if these routes exist at these paths.
    health = backend / "api" / "healthcheck.py"
    urls = backend / "api" / "urls.py"
    health_text = health.read_text(encoding="utf-8") if health.is_file() else ""
    if not all(p.search(health_text) for p in (_HEALTH_CONTROLLER, _LIVENESS, _READINESS)):
        raise _layout_error("api/healthcheck.py", "does not define /health, /liveness, /readiness")
    if not _API_MOUNT.search(urls.read_text(encoding="utf-8") if urls.is_file() else ""):
        raise _layout_error("api/urls.py", 'does not mount the API at path("api/", ...)')

    prod.write_text(text[: match.end(1)] + EXEMPT_BLOCK + text[match.end(1) :], encoding="utf-8")
    print_info("Exempted the public health routes from the USE_TLS redirect")
    return [prod.relative_to(config.path).as_posix()]
