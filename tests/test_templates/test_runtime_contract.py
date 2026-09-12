"""Contract tests for the generated runtime environment.

The boilerplate's Django settings read a fixed set of environment variables.
A missing key does not fail at generation time; it fails when a developer runs
`make up` or `manage.py migrate`. These tests assert the keys the settings
read are the keys the generated compose and .env files set.

Source of truth: the django-ninja boilerplate's
`api/settings/common.py`, which reads SECRET_KEY, DB_NAME, DB_USER,
DB_PASSWORD, DB_HOST, and DB_PORT.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mattstack.config import FrontendFramework, ProjectConfig, ProjectType
from mattstack.templates.docker_compose import generate_docker_compose
from mattstack.templates.docker_compose_prod import generate_docker_compose_prod
from mattstack.templates.root_env import generate_env_example, generate_env_production_example

# The variables api/settings/common.py reads for the database and secret.
DJANGO_ENV_KEYS = ("SECRET_KEY", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT")


def _fullstack(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="todoapp",
        path=tmp_path / "todoapp",
        project_type=ProjectType.FULLSTACK,
        frontend_framework=FrontendFramework.REACT_VITE,
        use_celery=True,
        use_redis=True,
        init_git=False,
    )


def _service_env(compose_text: str, service: str) -> dict[str, str]:
    document = yaml.safe_load(compose_text)
    environment = document["services"][service].get("environment")
    if isinstance(environment, list):
        return dict(item.split(": ", 1) for item in environment)
    assert isinstance(environment, dict), f"{service} has no environment mapping"
    return {str(k): str(v) for k, v in environment.items()}


@pytest.mark.parametrize("service", ["api-dev", "celery-worker", "celery-beat"])
def test_dev_services_pass_the_settings_read(tmp_path: Path, service: str) -> None:
    """Each Django service needs the DB_* keys, not just DATABASE_URL."""
    compose = generate_docker_compose(_fullstack(tmp_path))
    env = _service_env(compose, service)
    for key in DJANGO_ENV_KEYS:
        assert key in env, f"{service} is missing {key}"
    # Containers reach Postgres over the compose network, not localhost.
    assert env["DB_HOST"] == "db"


def test_dev_api_keeps_redis_and_cors(tmp_path: Path) -> None:
    """A regression dropped these two keys with every test still green."""
    compose = generate_docker_compose(_fullstack(tmp_path))
    env = _service_env(compose, "api-dev")
    assert env["REDIS_URL"] == "redis://redis:6379/0"
    assert "localhost:3000" in env["CORS_ALLOWED_ORIGINS"]


@pytest.mark.parametrize("service", ["api", "celery-worker", "celery-beat"])
def test_prod_services_pass_the_settings_read(tmp_path: Path, service: str) -> None:
    compose = generate_docker_compose_prod(_fullstack(tmp_path))
    env = _service_env(compose, service)
    for key in DJANGO_ENV_KEYS:
        assert key in env, f"{service} is missing {key}"


def test_prod_api_sets_cors_and_csrf(tmp_path: Path) -> None:
    """prod.py reads these with an empty default, so a missing key blocks the SPA."""
    compose = generate_docker_compose_prod(_fullstack(tmp_path))
    env = _service_env(compose, "api")
    assert "CORS_ALLOWED_ORIGINS" in env
    assert "CSRF_TRUSTED_ORIGINS" in env


def test_env_example_defines_the_settings_read(tmp_path: Path) -> None:
    content = generate_env_example(_fullstack(tmp_path))
    for key in DJANGO_ENV_KEYS:
        assert f"{key}=" in content, f".env.example is missing {key}"
    # POSTGRES_* configures the postgres image; DB_* is what Django reads.
    assert "POSTGRES_DB=" in content


def test_production_env_defines_the_settings_read(tmp_path: Path) -> None:
    content = generate_env_production_example(_fullstack(tmp_path))
    for key in DJANGO_ENV_KEYS:
        assert f"{key}=" in content, f".env.production.example is missing {key}"


def test_makefile_loads_the_root_env(tmp_path: Path) -> None:
    """Host commands need DB_* too, and nothing else loads .env for them."""
    from mattstack.templates.root_makefile import generate_makefile

    makefile = generate_makefile(_fullstack(tmp_path))
    assert "include .env" in makefile
    assert "export" in makefile


def test_makefile_compose_and_env_agree_on_db_host(tmp_path: Path) -> None:
    """The container uses `db`; the host uses `localhost`. Neither may leak."""
    from mattstack.templates.root_makefile import generate_makefile

    compose = generate_docker_compose(_fullstack(tmp_path))
    env_example = generate_env_example(_fullstack(tmp_path))
    makefile = generate_makefile(_fullstack(tmp_path))

    assert _service_env(compose, "api-dev")["DB_HOST"] == "db"
    assert "DB_HOST=localhost" in env_example
    assert "include .env" in makefile


def test_dockerfile_pins_the_interpreter_and_venv(tmp_path: Path) -> None:
    """An unpinned interpreter resolves past the wheels some deps ship."""
    from mattstack.templates.dockerfiles import generate_backend_dockerfile

    dockerfile = generate_backend_dockerfile(_fullstack(tmp_path))
    assert "UV_PYTHON=" in dockerfile
    assert "UV_PROJECT_ENVIRONMENT=/opt/venv" in dockerfile
    # A literal $$PATH is the shell PID, which breaks PATH and every lookup.
    assert "$$PATH" not in dockerfile
    assert "python:3.12-slim" not in dockerfile
