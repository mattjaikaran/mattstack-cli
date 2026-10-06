"""Tests for consolidated Dockerfile templates."""

from __future__ import annotations

from typing import Any

import pytest

from mattstack.config import (
    BackendFramework,
    FrontendFramework,
    ProjectConfig,
    ProjectType,
    TaskBackend,
)
from mattstack.templates.dockerfiles import (
    generate_backend_dockerfile,
    generate_frontend_dev_dockerfile,
    generate_frontend_dockerfile,
    generate_frontend_nginx_conf,
)


def _config(
    backend: BackendFramework,
    frontend: FrontendFramework = FrontendFramework.REACT_VITE,
    **kwargs: Any,
) -> ProjectConfig:
    return ProjectConfig(
        name="test-proj",
        path="/tmp/test-proj",
        backend_framework=backend,
        frontend_framework=frontend,
        **kwargs,
    )


def _production_stage(dockerfile: str) -> str:
    return dockerfile.split("AS production\n", 1)[1]


@pytest.mark.parametrize("backend", list(BackendFramework))
def test_production_is_the_last_stage_and_starts_through_the_entrypoint(
    backend: BackendFramework,
) -> None:
    """Render, Railway, Fly.io, and App Platform build the last stage."""
    stage = _production_stage(generate_backend_dockerfile(_config(backend)))
    assert "FROM " not in stage
    assert "COPY docker/backend/entrypoint.sh /usr/local/bin/app-entrypoint" in stage
    assert stage.rstrip().endswith('ENTRYPOINT ["app-entrypoint"]\nCMD ["serve"]')


def test_ninja_production_bakes_both_mode_variables() -> None:
    stage = _production_stage(generate_backend_dockerfile(_config(BackendFramework.DJANGO_NINJA)))
    env_line = next(line for line in stage.splitlines() if line.startswith("ENV "))
    assert "DJANGO_ENVIRONMENT=production" in env_line
    assert " ENVIRONMENT=production" in env_line
    assert "TASK_BACKEND=celery" in env_line


def test_django_matt_bakes_debug_off_without_ninja_keys() -> None:
    stage = _production_stage(generate_backend_dockerfile(_config(BackendFramework.DJANGO_MATT)))
    assert "ENV DEBUG=false\n" in stage
    assert "NINJA_JWT_SIGNING_KEY" not in stage


def test_task_backend_extra_is_installed_in_the_image() -> None:
    huey = generate_backend_dockerfile(
        _config(BackendFramework.DJANGO_NINJA, task_backend=TaskBackend.HUEY)
    )
    celery = generate_backend_dockerfile(_config(BackendFramework.DJANGO_NINJA))
    assert "RUN uv sync --no-dev --extra huey $(for extra in $UV_EXTRAS" in huey
    assert "RUN uv sync --no-dev $(for extra in $UV_EXTRAS" in celery


def test_backend_dockerfile_nestjs() -> None:
    content = generate_backend_dockerfile(_config(BackendFramework.NESTJS))
    assert "oven/bun" in content
    assert "start:dev" in content
    assert "ENV NODE_ENV=production" in _production_stage(content)


def test_frontend_dockerfile_vite(starter_fullstack_config: ProjectConfig) -> None:
    content = generate_frontend_dockerfile(starter_fullstack_config)
    assert "COPY frontend/ ." in content
    assert "API_UPSTREAM=http://api:8000" in content
    assert "docker/frontend/nginx.conf" in content


def test_frontend_only_static_image_has_no_api_proxy() -> None:
    """nginx fails at startup when proxy_pass names an undefined upstream."""
    config = ProjectConfig(
        name="test-proj", path="/tmp/test-proj", project_type=ProjectType.FRONTEND_ONLY
    )
    assert "API_UPSTREAM" not in generate_frontend_dockerfile(config)
    conf = generate_frontend_nginx_conf(config)
    assert "${API_PREFIX}" not in conf
    assert "try_files $uri $uri/ /index.html;" in conf


def test_fullstack_nginx_conf_proxies_the_api_prefix(
    starter_fullstack_config: ProjectConfig,
) -> None:
    content = generate_frontend_nginx_conf(starter_fullstack_config)
    assert "location ^~ ${API_PREFIX}/ {" in content
    assert "proxy_pass ${API_UPSTREAM};" in content


def test_django_static_falls_back_to_the_api_after_bundle_files() -> None:
    """Rsbuild bundles live under /static/js; admin static is served by the API."""
    content = generate_frontend_nginx_conf(_config(BackendFramework.DJANGO_NINJA))
    assert "location ^~ /static/ {\n        try_files $uri @backend;" in content
    assert "location ^~ /admin/ {" in content
    assert "location ^~ /media/ {" in content
    fastapi = generate_frontend_nginx_conf(_config(BackendFramework.FASTAPI))
    assert "/admin/" not in fastapi


def test_frontend_dockerfile_nextjs() -> None:
    config = _config(BackendFramework.DJANGO_NINJA, FrontendFramework.NEXTJS)
    content = generate_frontend_dockerfile(config)
    assert "bun run build" in content
    assert '"bun", "run", "start"' in content


def test_frontend_dev_dockerfile(starter_fullstack_config: ProjectConfig) -> None:
    content = generate_frontend_dev_dockerfile(starter_fullstack_config)
    assert '"bun", "run", "dev"' in content
    assert "COPY frontend/" in content
