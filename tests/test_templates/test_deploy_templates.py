"""Tests for deployment config templates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mattstack.config import (
    DeploymentTarget,
    FrontendFramework,
    ProjectConfig,
    ProjectType,
    Variant,
)
from mattstack.templates.deploy_cloudflare import generate_wrangler_toml
from mattstack.templates.deploy_digitalocean import generate_do_app_spec
from mattstack.templates.deploy_railway import generate_railway_json, generate_railway_toml
from mattstack.templates.deploy_render import generate_render_yaml

# --- Fixtures for deployment-specific configs ---


@pytest.fixture
def railway_fullstack_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="my-app",
        path=tmp_path / "my-app",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        deployment=DeploymentTarget.RAILWAY,
    )


@pytest.fixture
def railway_backend_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="my-api",
        path=tmp_path / "my-api",
        project_type=ProjectType.BACKEND_ONLY,
        variant=Variant.STARTER,
        deployment=DeploymentTarget.RAILWAY,
    )


@pytest.fixture
def render_fullstack_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="my-app",
        path=tmp_path / "my-app",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        deployment=DeploymentTarget.RENDER,
    )


@pytest.fixture
def render_backend_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="my-api",
        path=tmp_path / "my-api",
        project_type=ProjectType.BACKEND_ONLY,
        variant=Variant.STARTER,
        deployment=DeploymentTarget.RENDER,
    )


@pytest.fixture
def render_backend_no_redis_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="my-api",
        path=tmp_path / "my-api",
        project_type=ProjectType.BACKEND_ONLY,
        variant=Variant.STARTER,
        deployment=DeploymentTarget.RENDER,
        use_celery=False,
        use_redis=False,
    )


# --- Railway JSON tests ---


def test_railway_json_fullstack(railway_fullstack_config: ProjectConfig) -> None:
    content = generate_railway_json(railway_fullstack_config)
    data = json.loads(content)
    assert data["build"]["builder"] == "NIXPACKS"
    assert "uv" in data["build"]["buildCommand"]
    assert "runserver" in data["deploy"]["startCommand"]
    assert data["deploy"]["healthcheckPath"] == "/api/health/"


def test_railway_json_backend_only(railway_backend_config: ProjectConfig) -> None:
    content = generate_railway_json(railway_backend_config)
    data = json.loads(content)
    assert data["build"]["builder"] == "NIXPACKS"
    assert data["deploy"]["healthcheckPath"] == "/api/health/"
    assert data["deploy"]["restartPolicyType"] == "ON_FAILURE"


def test_railway_json_is_valid_json(railway_fullstack_config: ProjectConfig) -> None:
    content = generate_railway_json(railway_fullstack_config)
    data = json.loads(content)
    assert "$schema" in data


# --- Railway TOML tests ---


def test_railway_toml_fullstack(railway_fullstack_config: ProjectConfig) -> None:
    content = generate_railway_toml(railway_fullstack_config)
    assert "[build]" in content
    assert "[deploy]" in content
    assert "gunicorn" in content
    assert "api.wsgi:application" in content
    assert "healthcheckPath" in content


def test_railway_toml_backend_only(railway_backend_config: ProjectConfig) -> None:
    content = generate_railway_toml(railway_backend_config)
    assert "[build]" in content
    assert "gunicorn" in content
    assert "api.wsgi:application" in content


def test_railway_toml_uses_the_django_package(
    railway_fullstack_config: ProjectConfig,
) -> None:
    """The boilerplate keeps `api` as its import package, not the project name."""
    content = generate_railway_toml(railway_fullstack_config)
    assert "api.wsgi:application" in content
    assert "my_app.wsgi" not in content


# --- Render YAML tests ---


def test_render_yaml_fullstack(render_fullstack_config: ProjectConfig) -> None:
    content = generate_render_yaml(render_fullstack_config)
    assert "services:" in content
    assert "databases:" in content
    assert "my-app-api" in content
    assert "my-app-frontend" in content
    assert "my-app-db" in content
    assert "gunicorn" in content
    assert "healthCheckPath: /api/health/" in content


def test_render_yaml_backend_only(render_backend_config: ProjectConfig) -> None:
    content = generate_render_yaml(render_backend_config)
    assert "my-api-api" in content
    assert "my-api-db" in content
    assert "my-api-frontend" not in content


def test_render_yaml_has_redis_when_configured(
    render_fullstack_config: ProjectConfig,
) -> None:
    content = generate_render_yaml(render_fullstack_config)
    assert "my-app-redis" in content
    assert "type: redis" in content


def test_render_yaml_no_redis_when_disabled(
    render_backend_no_redis_config: ProjectConfig,
) -> None:
    content = generate_render_yaml(render_backend_no_redis_config)
    assert "redis" not in content.lower()


def test_render_yaml_has_celery_when_configured(
    render_fullstack_config: ProjectConfig,
) -> None:
    content = generate_render_yaml(render_fullstack_config)
    assert "my-app-celery-worker" in content
    assert "my-app-celery-beat" in content
    assert "celery -A api worker" in content
    assert "celery -A api beat" in content


def test_render_yaml_no_celery_when_disabled(
    render_backend_no_redis_config: ProjectConfig,
) -> None:
    content = generate_render_yaml(render_backend_no_redis_config)
    assert "celery" not in content.lower()


def test_render_yaml_project_name_substitution(
    render_fullstack_config: ProjectConfig,
) -> None:
    content = generate_render_yaml(render_fullstack_config)
    assert "api.wsgi:application" in content
    assert "api.settings" in content


def test_render_yaml_frontend_static_site(render_fullstack_config: ProjectConfig) -> None:
    content = generate_render_yaml(render_fullstack_config)
    assert "runtime: static" in content
    assert "frontend/dist" in content
    assert "bun install && bun run build" in content


def test_render_yaml_env_groups(render_fullstack_config: ProjectConfig) -> None:
    content = generate_render_yaml(render_fullstack_config)
    assert "envGroups:" in content
    assert "shared-env" in content


# --- Cloudflare tests ---


class TestCloudflare:
    def test_wrangler_frontend_only(self, tmp_path: Path) -> None:
        config = ProjectConfig(
            name="my-app",
            path=tmp_path / "my-app",
            project_type=ProjectType.FRONTEND_ONLY,
            variant=Variant.STARTER,
            deployment=DeploymentTarget.CLOUDFLARE,
        )
        content = generate_wrangler_toml(config)
        assert 'name = "my-app"' in content
        assert "pages_build_output_dir" in content
        assert "bun install && bun run build" in content

    def test_wrangler_fullstack(self, tmp_path: Path) -> None:
        config = ProjectConfig(
            name="my-app",
            path=tmp_path / "my-app",
            project_type=ProjectType.FULLSTACK,
            variant=Variant.STARTER,
            deployment=DeploymentTarget.CLOUDFLARE,
        )
        content = generate_wrangler_toml(config)
        assert 'name = "my-app"' in content
        assert "VITE_API_BASE_URL" in content

    def test_wrangler_fullstack_nextjs(self, tmp_path: Path) -> None:
        config = ProjectConfig(
            name="my-app",
            path=tmp_path / "my-app",
            project_type=ProjectType.FULLSTACK,
            variant=Variant.STARTER,
            frontend_framework=FrontendFramework.NEXTJS,
            deployment=DeploymentTarget.CLOUDFLARE,
        )
        content = generate_wrangler_toml(config)
        assert "NEXT_PUBLIC_API_BASE_URL" in content

    def test_wrangler_backend_only(self, tmp_path: Path) -> None:
        config = ProjectConfig(
            name="my-api",
            path=tmp_path / "my-api",
            project_type=ProjectType.BACKEND_ONLY,
            variant=Variant.STARTER,
            deployment=DeploymentTarget.CLOUDFLARE,
        )
        content = generate_wrangler_toml(config)
        assert "API_ORIGIN" in content


# --- DigitalOcean tests ---


class TestDigitalOcean:
    def test_do_fullstack(self, tmp_path: Path) -> None:
        config = ProjectConfig(
            name="my-app",
            path=tmp_path / "my-app",
            project_type=ProjectType.FULLSTACK,
            variant=Variant.STARTER,
            deployment=DeploymentTarget.DIGITAL_OCEAN,
        )
        content = generate_do_app_spec(config)
        assert "name: my-app" in content
        assert "my-app-api" in content
        assert "my-app-frontend" in content
        assert "databases:" in content
        assert "db-my-app" in content

    def test_do_backend_only(self, tmp_path: Path) -> None:
        config = ProjectConfig(
            name="my-api",
            path=tmp_path / "my-api",
            project_type=ProjectType.BACKEND_ONLY,
            variant=Variant.STARTER,
            deployment=DeploymentTarget.DIGITAL_OCEAN,
        )
        content = generate_do_app_spec(config)
        assert "my-api-api" in content
        assert "databases:" in content
        assert "frontend" not in content

    def test_do_fullstack_nextjs(self, tmp_path: Path) -> None:
        config = ProjectConfig(
            name="my-app",
            path=tmp_path / "my-app",
            project_type=ProjectType.FULLSTACK,
            variant=Variant.STARTER,
            frontend_framework=FrontendFramework.NEXTJS,
            deployment=DeploymentTarget.DIGITAL_OCEAN,
        )
        content = generate_do_app_spec(config)
        assert "NEXT_PUBLIC_API_BASE_URL" in content
        assert "my-app-frontend" in content

    def test_do_frontend_only(self, tmp_path: Path) -> None:
        config = ProjectConfig(
            name="my-fe",
            path=tmp_path / "my-fe",
            project_type=ProjectType.FRONTEND_ONLY,
            variant=Variant.STARTER,
            deployment=DeploymentTarget.DIGITAL_OCEAN,
        )
        content = generate_do_app_spec(config)
        assert "my-fe-frontend" in content
        assert "databases:" not in content
