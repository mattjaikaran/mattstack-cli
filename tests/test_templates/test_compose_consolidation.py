"""Tests for consolidated docker-compose templates."""

from __future__ import annotations

import yaml

from mattstack.config import ProjectConfig
from mattstack.templates.docker_compose import generate_docker_compose
from mattstack.templates.docker_compose_prod import generate_docker_compose_prod


def test_dev_compose_uses_relocated_dockerfiles(starter_fullstack_config: ProjectConfig) -> None:
    content = generate_docker_compose(starter_fullstack_config)
    assert "context: ." in content
    assert "dockerfile: docker/backend/Dockerfile" in content
    assert "dockerfile: docker/frontend/Dockerfile.dev" in content
    assert "target: development" in content


def test_dev_compose_has_celery_profile(starter_fullstack_config: ProjectConfig) -> None:
    content = generate_docker_compose(starter_fullstack_config)
    assert "profiles:" in content
    assert "- celery" in content


def test_prod_compose_uses_relocated_dockerfiles(starter_fullstack_config: ProjectConfig) -> None:
    content = generate_docker_compose_prod(starter_fullstack_config)
    assert "context: ." in content
    assert "dockerfile: docker/backend/Dockerfile" in content
    assert "dockerfile: docker/frontend/Dockerfile" in content


def test_dev_compose_environment_is_mapping(
    starter_fullstack_config: ProjectConfig,
) -> None:
    services = yaml.safe_load(generate_docker_compose(starter_fullstack_config))["services"]
    for name in ("api-dev", "frontend-dev"):
        environment = services[name]["environment"]
        assert isinstance(environment, dict), f"{name} environment must be a mapping"
    assert services["api-dev"]["environment"]["DEBUG"] == "true"


def test_unedited_override_example_is_a_valid_services_mapping(
    starter_fullstack_config: ProjectConfig,
) -> None:
    """Compose rejects `services: null`, which a comments-only block parses to."""
    from mattstack.templates.docker_compose_override import generate_docker_compose_override

    services = yaml.safe_load(generate_docker_compose_override(starter_fullstack_config))[
        "services"
    ]
    assert isinstance(services, dict)
    assert set(services) == {"api-dev", "frontend-dev"}
    assert all(isinstance(service, dict) for service in services.values())
    # An override `ports:` list is appended to the base, publishing both ports.
    assert not any("ports" in service for service in services.values())


def test_prod_frontend_build_gets_the_relative_browser_api_base(
    starter_fullstack_config: ProjectConfig,
) -> None:
    """frontend/.env is gitignored, so a fresh clone must get the base as a build arg."""
    from mattstack.templates.dockerfiles import generate_frontend_dockerfile

    services = yaml.safe_load(generate_docker_compose_prod(starter_fullstack_config))["services"]
    args = services["frontend"]["build"]["args"]
    prefix = starter_fullstack_config.api_prefix
    assert args["VITE_API_BASE_URL"] == f"${{VITE_API_BASE_URL:-{prefix}}}"
    dockerfile = generate_frontend_dockerfile(starter_fullstack_config)
    build_stage = dockerfile.split("FROM nginx")[0]
    assert f"ARG VITE_API_BASE_URL={prefix}\n" in build_stage
    assert build_stage.index("ENV VITE_API_BASE_URL=") < build_stage.index("RUN bun run build")
