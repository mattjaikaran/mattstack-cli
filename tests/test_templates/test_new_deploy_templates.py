"""Tests for new deployment config templates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mattstack.config import DeploymentTarget, ProjectConfig, ProjectType, Variant

# --- Fixtures ---


@pytest.fixture
def fly_fullstack_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="my-app",
        path=tmp_path / "my-app",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        deployment=DeploymentTarget.FLY_IO,
    )


@pytest.fixture
def fly_frontend_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="my-frontend",
        path=tmp_path / "my-frontend",
        project_type=ProjectType.FRONTEND_ONLY,
        variant=Variant.STARTER,
        deployment=DeploymentTarget.FLY_IO,
    )


@pytest.fixture
def aws_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="my-app",
        path=tmp_path / "my-app",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        deployment=DeploymentTarget.AWS,
    )


@pytest.fixture
def aws_backend_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="my-api",
        path=tmp_path / "my-api",
        project_type=ProjectType.BACKEND_ONLY,
        variant=Variant.STARTER,
        deployment=DeploymentTarget.AWS,
    )


@pytest.fixture
def gcp_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="my-app",
        path=tmp_path / "my-app",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        deployment=DeploymentTarget.GCP,
    )


@pytest.fixture
def hetzner_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="my-app",
        path=tmp_path / "my-app",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        deployment=DeploymentTarget.HETZNER,
    )


@pytest.fixture
def self_hosted_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="my-app",
        path=tmp_path / "my-app",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
        deployment=DeploymentTarget.SELF_HOSTED,
    )


# --- Fly.io tests ---


def test_fly_toml_fullstack(fly_fullstack_config: ProjectConfig) -> None:
    from mattstack.templates.deploy_fly import generate_fly_toml

    content = generate_fly_toml(fly_fullstack_config)
    assert 'app = "my-app"' in content
    assert "internal_port = 8000" in content
    assert "/api/health/" in content
    assert "force_https = true" in content


def test_fly_toml_frontend(fly_frontend_config: ProjectConfig) -> None:
    from mattstack.templates.deploy_fly import generate_fly_toml

    content = generate_fly_toml(fly_frontend_config)
    assert 'app = "my-frontend"' in content
    assert "internal_port = 3000" in content


# --- AWS tests ---


def test_ecs_task_definition(aws_config: ProjectConfig) -> None:
    from mattstack.templates.deploy_aws import generate_ecs_task_definition

    content = generate_ecs_task_definition(aws_config)
    data = json.loads(content)
    assert data["family"] == "my-app-task"
    assert data["requiresCompatibilities"] == ["FARGATE"]
    assert len(data["containerDefinitions"]) == 1
    container = data["containerDefinitions"][0]
    assert container["name"] == "my-app-api"
    assert container["portMappings"][0]["containerPort"] == 8000
    assert any(e["name"] == "DJANGO_SETTINGS_MODULE" for e in container["environment"])


def test_ecs_task_definition_backend_only(aws_backend_config: ProjectConfig) -> None:
    from mattstack.templates.deploy_aws import generate_ecs_task_definition

    content = generate_ecs_task_definition(aws_backend_config)
    data = json.loads(content)
    assert len(data["containerDefinitions"]) == 1
    assert data["containerDefinitions"][0]["name"] == "my-api-api"


def test_copilot_manifest(aws_config: ProjectConfig) -> None:
    from mattstack.templates.deploy_aws import generate_copilot_manifest

    content = generate_copilot_manifest(aws_config)
    assert "name: my-app-api" in content
    assert "Load Balanced Web Service" in content
    assert "/api/health/" in content
    assert "api.settings" in content


# --- GCP tests ---


def test_cloud_run_yaml(gcp_config: ProjectConfig) -> None:
    from mattstack.templates.deploy_gcp import generate_cloud_run_yaml

    content = generate_cloud_run_yaml(gcp_config)
    assert "name: my-app-api" in content
    assert "containerPort: 8000" in content
    assert "/api/health/" in content
    assert "api.settings" in content


def test_app_engine_yaml(gcp_config: ProjectConfig) -> None:
    from mattstack.templates.deploy_gcp import generate_app_engine_yaml

    content = generate_app_engine_yaml(gcp_config)
    assert "runtime: python312" in content
    assert "gunicorn api.wsgi:application" in content
    assert "automatic_scaling:" in content


# --- Hetzner tests ---


def test_hetzner_compose(hetzner_config: ProjectConfig) -> None:
    from mattstack.templates.deploy_hetzner import generate_hetzner_compose

    content = generate_hetzner_compose(hetzner_config)
    assert "caddy:" in content
    assert "api:" in content
    assert "db:" in content
    assert "gunicorn api.wsgi" in content
    assert "postgres_data:" in content


def test_hetzner_compose_has_redis(hetzner_config: ProjectConfig) -> None:
    from mattstack.templates.deploy_hetzner import generate_hetzner_compose

    content = generate_hetzner_compose(hetzner_config)
    assert "redis:" in content


def test_caddyfile(hetzner_config: ProjectConfig) -> None:
    from mattstack.templates.deploy_hetzner import generate_caddyfile

    content = generate_caddyfile(hetzner_config)
    assert "my-app.example.com" in content
    assert "reverse_proxy api:8000" in content
    assert "reverse_proxy frontend:3000" in content


# --- Self-hosted tests ---


def test_self_hosted_compose(self_hosted_config: ProjectConfig) -> None:
    from mattstack.templates.deploy_self_hosted import generate_self_hosted_compose

    content = generate_self_hosted_compose(self_hosted_config)
    assert "nginx:" in content
    assert "certbot:" in content
    assert "api:" in content
    assert "db:" in content
    assert "gunicorn api.wsgi" in content


def test_nginx_conf(self_hosted_config: ProjectConfig) -> None:
    from mattstack.templates.deploy_self_hosted import generate_nginx_conf

    content = generate_nginx_conf(self_hosted_config)
    assert "server_name my-app.example.com" in content
    assert "proxy_pass http://api:8000" in content
    assert "proxy_pass http://frontend:3000" in content
    assert "ssl_certificate" in content


def test_systemd_service(self_hosted_config: ProjectConfig) -> None:
    from mattstack.templates.deploy_self_hosted import generate_systemd_service

    content = generate_systemd_service(self_hosted_config)
    assert "My App" in content  # display_name
    assert "docker compose" in content
    assert "WantedBy=multi-user.target" in content
    assert "/opt/my-app" in content


# --- Enum tests ---


def test_deployment_target_new_values() -> None:
    assert DeploymentTarget.FLY_IO == "fly-io"
    assert DeploymentTarget.AWS == "aws"
    assert DeploymentTarget.GCP == "gcp"
    assert DeploymentTarget.HETZNER == "hetzner"
    assert DeploymentTarget.SELF_HOSTED == "self-hosted"
    assert DeploymentTarget.CLOUDFLARE == "cloudflare"
    assert DeploymentTarget.DIGITAL_OCEAN == "digital-ocean"
