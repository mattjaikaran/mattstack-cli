"""Contract tests for the generated runtime environment.

The boilerplate's Django settings read a fixed set of environment variables.
A missing key does not fail at generation time; it fails when a developer runs
`just up` or `manage.py migrate`. These tests assert the keys the settings
read are the keys the generated compose and .env files set.

Source of truth: the django-ninja boilerplate's
`api/settings/common.py`, which reads SECRET_KEY, DB_NAME, DB_USER,
DB_PASSWORD, DB_HOST, and DB_PORT.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from mattstack.config import (
    BackendFramework,
    FrontendFramework,
    ProjectConfig,
    ProjectType,
    TaskBackend,
)
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
        task_backend=TaskBackend.CELERY,
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
    assert env["REDIS_URL"] == "redis://:${REDIS_PASSWORD:-}@redis:6379/0"
    assert "localhost:3000" in _interpolate(env["CORS_ALLOWED_ORIGINS"], {})


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


def test_justfile_loads_the_root_env(tmp_path: Path) -> None:
    """Host commands need DB_* too, and just's dotenv-load supplies them."""
    from mattstack.templates.root_justfile import generate_justfile

    content = generate_justfile(_fullstack(tmp_path))
    assert "set dotenv-load" in content
    assert "LOAD_ENV" not in content
    assert "include .env" not in content


def test_justfile_compose_and_env_agree_on_db_host(tmp_path: Path) -> None:
    """The container uses `db`; the host uses `localhost`. Neither may leak."""
    from mattstack.templates.root_justfile import generate_justfile

    compose = generate_docker_compose(_fullstack(tmp_path))
    env_example = generate_env_example(_fullstack(tmp_path))
    content = generate_justfile(_fullstack(tmp_path))

    assert _service_env(compose, "api-dev")["DB_HOST"] == "db"
    assert "DB_HOST=localhost" in env_example
    assert "set dotenv-load" in content


def test_dockerfile_pins_the_interpreter_and_venv(tmp_path: Path) -> None:
    """An unpinned interpreter resolves past the wheels some deps ship."""
    from mattstack.templates.dockerfiles import generate_backend_dockerfile

    dockerfile = generate_backend_dockerfile(_fullstack(tmp_path))
    assert "UV_PYTHON=" in dockerfile
    assert "UV_PROJECT_ENVIRONMENT=/opt/venv" in dockerfile
    # A literal $$PATH is the shell PID, which breaks PATH and every lookup.
    assert "$$PATH" not in dockerfile
    assert "python:3.12-slim" not in dockerfile


_REFERENCE = re.compile(r"\$\{(\w+)(?::([-?])([^}]*))?\}")


def _interpolate(value: str, env: dict[str, str]) -> str:
    """Resolve Compose ``${NAME}``, ``${NAME:-default}``, and ``${NAME:?error}``."""

    def resolve(match: re.Match[str]) -> str:
        name, operator, argument = match.groups()
        if env.get(name):
            return env[name]
        if operator == "?":
            raise KeyError(f"{name}: {argument}")
        return argument if operator == "-" else ""

    return _REFERENCE.sub(resolve, value)


def _resolved_env(compose_text: str, service: str, env: dict[str, str]) -> dict[str, str]:
    return {k: _interpolate(v, env) for k, v in _service_env(compose_text, service).items()}


def _published(compose_text: str, service: str) -> list[tuple[str, ...]]:
    """Return (host default, container port) for each published port."""
    ports = yaml.safe_load(compose_text)["services"][service]["ports"]
    return [tuple(_interpolate(p, {}).rsplit(":", 2)[-2:]) for p in ports]


def test_custom_credentials_reach_the_database_and_every_backend_service(
    tmp_path: Path,
) -> None:
    """Changing POSTGRES_* in .env must not leave a service on the old password."""
    custom = {"POSTGRES_DB": "appdb", "POSTGRES_USER": "app", "POSTGRES_PASSWORD": "s3cret"}
    compose = generate_docker_compose(_fullstack(tmp_path))
    assert _resolved_env(compose, "db", custom) == custom
    for service in ("api-dev", "celery-worker", "celery-beat"):
        env = _resolved_env(compose, service, custom)
        assert (env["DB_NAME"], env["DB_USER"], env["DB_PASSWORD"]) == ("appdb", "app", "s3cret")
        assert env["DATABASE_URL"] == "postgres://app:s3cret@db:5432/appdb"


def test_development_services_publish_only_on_loopback(tmp_path: Path) -> None:
    services = yaml.safe_load(generate_docker_compose(_fullstack(tmp_path)))["services"]
    for name in ("db", "redis", "api-dev", "frontend-dev"):
        for port in services[name]["ports"]:
            assert _interpolate(port, {}).rsplit(":", 2)[0] == "127.0.0.1", name


@pytest.mark.parametrize(
    ("backend", "frontend", "api_port", "frontend_port"),
    [
        (BackendFramework.DJANGO_NINJA, FrontendFramework.REACT_VITE, "8000", "80"),
        (BackendFramework.NESTJS, FrontendFramework.NEXTJS, "4000", "3000"),
    ],
)
def test_prod_ports_map_to_the_ports_the_images_listen_on(
    tmp_path: Path,
    backend: BackendFramework,
    frontend: FrontendFramework,
    api_port: str,
    frontend_port: str,
) -> None:
    """NestJS listens on 4000 and `next start` on 3000; nginx serves on 80."""
    config = ProjectConfig(
        name="todoapp",
        path=tmp_path / "todoapp",
        backend_framework=backend,
        frontend_framework=frontend,
    )
    compose = generate_docker_compose_prod(config)
    assert _published(compose, "api") == [(api_port, api_port)]
    assert _published(compose, "frontend")[0][1] == frontend_port


@pytest.mark.parametrize(
    ("frontend", "target_var"),
    [
        (FrontendFramework.REACT_VITE, "API_PROXY_TARGET"),
        (FrontendFramework.REACT_RSBUILD, "API_PROXY_TARGET"),
        (FrontendFramework.NEXTJS, "INTERNAL_API_URL"),
    ],
)
def test_frontend_container_proxies_to_the_api_service(
    tmp_path: Path, frontend: FrontendFramework, target_var: str
) -> None:
    """Inside the container, localhost is the frontend itself, not the API."""
    config = ProjectConfig(name="todoapp", path=tmp_path / "todoapp", frontend_framework=frontend)
    compose = generate_docker_compose(config)
    env = _service_env(compose, "frontend-dev")
    assert env[target_var] == "http://api-dev:8000"
    assert not any("localhost" in value for value in env.values())
    assert _published(compose, "frontend-dev") == [("3000", "3000")]


@pytest.mark.parametrize(
    "frontend",
    [
        FrontendFramework.REACT_VITE,
        FrontendFramework.REACT_RSBUILD,
        FrontendFramework.REACT_RSBUILD_KIBO,
        FrontendFramework.NEXTJS,
    ],
)
def test_dev_api_allows_the_proxied_host(tmp_path: Path, frontend: FrontendFramework) -> None:
    """Django 400s on the proxy's Host unless api-dev is in ALLOWED_HOSTS."""
    config = ProjectConfig(name="todoapp", path=tmp_path / "todoapp", frontend_framework=frontend)
    compose = generate_docker_compose(config)
    api = _service_env(compose, "api-dev")
    # Compose loads the root .env, which already allows only the host names;
    # the container value must still admit the proxy's Host.
    value = _interpolate(api["ALLOWED_HOSTS"], {"ALLOWED_HOSTS": "localhost,127.0.0.1"})
    hosts = value.split(",")
    assert "api-dev" in hosts
    # Host-run requests through the published port keep working.
    assert "localhost" in hosts
    assert "127.0.0.1" in hosts


def _run_just(justfile: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["just", "--justfile", str(justfile), *args],
        cwd=justfile.parent,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("just") is None, reason="just is not installed")
def test_justfile_never_drops_data_volumes_without_opt_in(tmp_path: Path) -> None:
    from mattstack.templates.root_justfile import generate_justfile

    config = _fullstack(tmp_path)
    config.path.mkdir()
    justfile = config.path / "justfile"
    justfile.write_text(generate_justfile(config))

    dry_clean = _run_just(justfile, "--dry-run", "clean")
    assert dry_clean.returncode == 0, dry_clean.stderr
    assert "down -v" not in dry_clean.stdout
    refused = _run_just(justfile, "clean-volumes")
    assert refused.returncode != 0
    assert "CONFIRM=1" in refused.stderr


@pytest.mark.skipif(shutil.which("just") is None, reason="just is not installed")
def test_missing_frontend_test_script_fails_instead_of_passing(tmp_path: Path) -> None:
    """nextjs-starter ships no test script; `just frontend-test` must not succeed."""
    from mattstack.templates.root_justfile import generate_justfile

    config = ProjectConfig(
        name="todoapp", path=tmp_path / "todoapp", frontend_framework=FrontendFramework.NEXTJS
    )
    config.path.mkdir()
    justfile = config.path / "justfile"
    justfile.write_text(generate_justfile(config))

    result = _run_just(justfile, "frontend-test")
    assert result.returncode != 0
    assert "no test script" in result.stderr
