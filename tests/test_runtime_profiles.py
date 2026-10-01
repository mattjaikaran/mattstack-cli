"""Generated task-worker and Centrifugo runtime for django-ninja projects.

Source of truth: django-ninja-boilerplate api/tasks/loader.py (TASK_BACKEND
names), pyproject.toml (optional extras), docker-compose.yml (worker commands
and the ``realtime`` Centrifugo profile).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from mattstack.config import ProjectConfig, ProjectType, TaskBackend
from mattstack.runtime_profiles import task_backend_extra
from mattstack.templates.docker_compose import generate_docker_compose
from mattstack.templates.docker_compose_prod import generate_docker_compose_prod
from mattstack.templates.root_env import generate_env_example, generate_env_file
from mattstack.templates.root_makefile import generate_makefile

WORKERS = {
    TaskBackend.CELERY: ({"celery-worker", "celery-beat"}, "celery", None),
    TaskBackend.HUEY: ({"huey-worker"}, "huey", "huey"),
    TaskBackend.DJANGO_Q: ({"django-q-worker"}, "django-q", "django-q"),
    TaskBackend.DJANGO_RQ: ({"django-rq-worker"}, "django-rq", "django-rq"),
    TaskBackend.DRAMATIQ: ({"dramatiq-worker"}, "dramatiq", "dramatiq"),
}
PLAIN_SERVICES = {"db", "redis", "api-dev", "frontend-dev"}


def _config(tmp_path: Path, task_backend: TaskBackend, *, realtime: bool = False) -> ProjectConfig:
    return ProjectConfig(
        name="shop",
        path=tmp_path / "shop",
        project_type=ProjectType.FULLSTACK,
        task_backend=task_backend,
        use_realtime=realtime,
        init_git=False,
    )


def _services(compose: str) -> dict[str, Any]:
    services = yaml.safe_load(compose)["services"]
    assert isinstance(services, dict)
    return services


@pytest.mark.parametrize("backend", list(WORKERS))
def test_each_backend_gets_its_worker_profile_extra_and_env(
    tmp_path: Path, backend: TaskBackend
) -> None:
    names, profile, extra = WORKERS[backend]
    config = _config(tmp_path, backend)
    assert task_backend_extra(config) == extra
    run = f"uv run --extra {extra}" if extra else "uv run"

    dev = _services(generate_docker_compose(config))
    # Workers start only with their profile; plain `docker compose up` is unchanged.
    assert {name for name, svc in dev.items() if "profiles" not in svc} == PLAIN_SERVICES
    for name in names:
        assert dev[name]["profiles"] == [profile]
        assert dev[name]["command"].startswith(f"{run} ")
        assert dev[name]["environment"]["TASK_BACKEND"] == backend.value
    assert dev["api-dev"]["command"].startswith(f"{run} python manage.py runserver")

    prod = _services(generate_docker_compose_prod(config))
    for name in names:
        assert "profiles" not in prod[name]
        assert not prod[name]["command"].startswith("uv ")
        assert prod[name]["environment"]["TASK_BACKEND"] == backend.value

    makefile = generate_makefile(config)
    assert f"up-{profile}:" in makefile
    assert f"docker compose --profile {profile} up -d" in makefile
    assert "backend-worker:" in makefile
    if extra:
        assert f"uv sync --extra {extra}" in makefile
    assert f"TASK_BACKEND={backend.value}" in generate_env_example(config)


def test_no_worker_mode_is_explicit_and_starts_no_consumer(tmp_path: Path) -> None:
    config = _config(tmp_path, TaskBackend.NONE)
    dev = _services(generate_docker_compose(config))
    prod = _services(generate_docker_compose_prod(config))

    assert set(dev) == PLAIN_SERVICES
    assert not any(name.endswith(("-worker", "-beat")) for name in prod)
    # Without TASK_BACKEND, Ninja would default to Celery with no worker running.
    assert dev["api-dev"]["environment"]["TASK_BACKEND"] == "none"
    makefile = generate_makefile(config)
    assert "backend-worker:" not in makefile
    assert not re.search(r"^up-(celery|huey|django-q|django-rq|dramatiq):", makefile, re.M)


@pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
@pytest.mark.parametrize("backend", [*WORKERS, TaskBackend.NONE])
def test_make_fails_for_task_processes_the_backend_does_not_run(
    tmp_path: Path, backend: TaskBackend
) -> None:
    """A declared target with no recipe makes `make backend-worker` exit 0 doing nothing."""
    worker_runs = backend != TaskBackend.NONE
    beat_runs = backend == TaskBackend.CELERY
    config = _config(tmp_path, backend)
    config.path.mkdir()
    (config.path / "Makefile").write_text(generate_makefile(config))

    for target, runs in (("backend-worker", worker_runs), ("backend-beat", beat_runs)):
        result = subprocess.run(
            ["make", "-C", str(config.path), "-n", target],
            capture_output=True,
            text=True,
            check=False,
        )
        if runs:
            assert result.returncode == 0, result.stderr
            assert "uv run" in result.stdout
        else:
            assert result.returncode != 0, result.stdout
            assert "No rule to make target" in result.stderr


def test_realtime_is_opt_in(tmp_path: Path) -> None:
    plain = _config(tmp_path, TaskBackend.CELERY)
    assert "centrifugo" not in _services(generate_docker_compose(plain))
    assert "CENTRIFUGO_API_KEY" not in generate_docker_compose(plain)
    assert "CENTRIFUGO_API_KEY" not in generate_env_example(plain)
    assert "up-realtime" not in generate_makefile(plain)


def test_realtime_profile_shares_secrets_without_committing_them(tmp_path: Path) -> None:
    config = _config(tmp_path, TaskBackend.CELERY, realtime=True)
    dev = _services(generate_docker_compose(config))

    centrifugo = dev["centrifugo"]
    assert centrifugo["profiles"] == ["realtime"]
    assert centrifugo["volumes"] == [
        "./backend/deploy/centrifugo/config.json:/centrifugo/config.json:ro"
    ]
    assert centrifugo["ports"] == ["127.0.0.1:${CENTRIFUGO_PORT:-8800}:8000"]
    env = centrifugo["environment"]
    # Centrifugo signs with the same secret Django uses; both fail when unset.
    assert env["CENTRIFUGO_TOKEN_HMAC_SECRET_KEY"] == (
        "${CENTRIFUGO_TOKEN_SECRET:?Set CENTRIFUGO_TOKEN_SECRET in .env}"
    )
    assert env["CENTRIFUGO_ADMIN"] == "false"
    api = dev["api-dev"]["environment"]
    assert api["CENTRIFUGO_URL"] == "http://centrifugo:8000"
    assert api["CENTRIFUGO_TOKEN_SECRET"] == env["CENTRIFUGO_TOKEN_HMAC_SECRET_KEY"]
    assert api["CENTRIFUGO_API_KEY"] == env["CENTRIFUGO_API_KEY"]

    example = generate_env_example(config)
    assert "CENTRIFUGO_API_KEY=\n" in example
    assert "CENTRIFUGO_TOKEN_SECRET=\n" in example
    local = generate_env_file(config)
    for key in ("CENTRIFUGO_API_KEY", "CENTRIFUGO_TOKEN_SECRET"):
        assert re.search(rf"^{key}=[0-9a-f]{{64}}$", local, re.M)
    assert generate_env_file(config) != local  # fresh secrets per project

    prod = _services(generate_docker_compose_prod(config))
    assert "profiles" not in prod["centrifugo"]
    assert prod["centrifugo"]["environment"]["CENTRIFUGO_ALLOWED_ORIGINS"].startswith(
        "${CENTRIFUGO_ALLOWED_ORIGINS:?"
    )
    assert "up-realtime:" in generate_makefile(config)
