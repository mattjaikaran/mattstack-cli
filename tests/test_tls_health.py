"""The USE_TLS health-route exemption patch for cloned django-ninja backends."""

from __future__ import annotations

from pathlib import Path

import pytest

from mattstack.config import DeploymentTarget, ProjectConfig, ProjectType
from mattstack.post_processors.task_runtime import prepare_runtime
from mattstack.post_processors.tls_health import ensure_health_redirect_exempt

# api/settings/prod.py as published in django-ninja-boilerplate 1.12.0.
PROD = """\
USE_TLS = env.bool("USE_TLS", default=False)

if USE_TLS:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0
"""

HEALTHCHECK = """\
@api_controller("/health", tags=["Health"])
class HealthCheckController:
    @http_get("/", response={200: dict})
    def basic_health_check(self, request): ...
    @http_get("/liveness", response={200: dict})
    def liveness_check(self, request): ...
    @http_get("/readiness", response={200: dict, 503: dict})
    def readiness_check(self, request): ...
"""

URLS = 'urlpatterns = [path("api/", api.urls)]\n'


def _project(tmp_path: Path, *, prod: str = PROD, health: str = HEALTHCHECK) -> ProjectConfig:
    config = ProjectConfig(
        name="tls-app", path=tmp_path / "tls-app", project_type=ProjectType.BACKEND_ONLY
    )
    api = config.backend_dir / "api"
    (api / "settings").mkdir(parents=True)
    (api / "settings" / "prod.py").write_text(prod)
    (api / "healthcheck.py").write_text(health)
    (api / "urls.py").write_text(URLS)
    return config


def test_refuses_routes_that_do_not_match_the_patterns(tmp_path: Path) -> None:
    config = _project(tmp_path, health=HEALTHCHECK.replace('"/liveness"', '"/live"'))
    before = {path: path.read_bytes() for path in config.backend_dir.rglob("*.py")}
    with pytest.raises(ValueError, match="backend/api/healthcheck.py.*SECURE_REDIRECT_EXEMPT"):
        ensure_health_redirect_exempt(config)
    assert {path: path.read_bytes() for path in config.backend_dir.rglob("*.py")} == before


def test_missing_tls_block_names_the_file(tmp_path: Path) -> None:
    config = _project(tmp_path, prod='USE_TLS = env.bool("USE_TLS", default=False)\n')
    with pytest.raises(ValueError, match=r"backend/api/settings/prod.py has no `if USE_TLS:`"):
        ensure_health_redirect_exempt(config)


def test_https_target_missing_prod_settings_fails_with_named_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = ProjectConfig(
        name="tls-missing",
        path=tmp_path / "tls-missing",
        project_type=ProjectType.BACKEND_ONLY,
        deployment=DeploymentTarget.RAILWAY,
    )
    config.backend_dir.mkdir(parents=True)
    assert prepare_runtime(config, dry_run=False) is False
    assert "backend/api/settings/prod.py is missing" in capsys.readouterr().err
    assert list(config.backend_dir.iterdir()) == []
