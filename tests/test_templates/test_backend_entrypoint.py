"""Behavior of the generated production entrypoint, run under /bin/sh."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mattstack.config import BackendFramework, DeploymentTarget, ProjectConfig, TaskBackend
from mattstack.templates.backend_entrypoint import generate_backend_entrypoint

NINJA_ENV = {
    "DJANGO_ENVIRONMENT": "production",
    "ENVIRONMENT": "production",
    "DEBUG": "false",
    "TASK_BACKEND": "celery",
    "DB_NAME": "app",
    "DB_USER": "app",
    "DB_PASSWORD": "db-secret-value",
    "DB_HOST": "db.internal",
    "DB_PORT": "5432",
    "SECRET_KEY": "s" * 50,
    "NINJA_JWT_SIGNING_KEY": "j" * 50,
    "CENTRIFUGO_TOKEN_SECRET": "c" * 50,
    "REDIS_URL": "redis://cache:6379/0",
    "ALLOWED_HOSTS": "api.example.com",
}


def _script(tmp_path: Path, **overrides: Any) -> Path:
    config = ProjectConfig(name="my-app", path=tmp_path / "my-app", **overrides)
    script = tmp_path / "entrypoint.sh"
    script.write_text(generate_backend_entrypoint(config))
    return script


def _run(script: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(script), *args],
        env={"PATH": os.environ["PATH"], **env},
        capture_output=True,
        text=True,
        check=False,
    )


def test_complete_ninja_environment_passes(tmp_path: Path) -> None:
    result = _run(_script(tmp_path), NINJA_ENV, "check")
    assert result.returncode == 0, result.stderr
    assert "preflight: ok" in result.stdout


def test_failure_names_variable_reason_and_provider_fix(tmp_path: Path) -> None:
    script = _script(tmp_path, deployment=DeploymentTarget.FLY_IO)
    env = {k: v for k, v in NINJA_ENV.items() if k != "DB_PASSWORD"}
    result = _run(script, env, "check")
    assert result.returncode == 1
    assert "DB_PASSWORD is not set." in result.stderr
    assert "does not read DATABASE_URL" in result.stderr
    assert "fly secrets set DB_PASSWORD='<value>' --app my-app" in result.stderr
    assert "verify: docker build -f docker/backend/Dockerfile" in result.stderr


def test_compose_fix_points_at_the_postgres_source_variable(tmp_path: Path) -> None:
    env = {k: v for k, v in NINJA_ENV.items() if k != "DB_PASSWORD"}
    result = _run(_script(tmp_path), env, "check")
    assert "set POSTGRES_PASSWORD=<value> in .env.production" in result.stderr


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("NINJA_JWT_SIGNING_KEY", "s" * 50, "SECRET_KEY and NINJA_JWT_SIGNING_KEY hold the same"),
        ("CENTRIFUGO_TOKEN_SECRET", "j" * 50, "NINJA_JWT_SIGNING_KEY and CENTRIFUGO_TOKEN_SECRET"),
        ("CENTRIFUGO_TOKEN_SECRET", "centrifugo-token-secret", "known default value"),
        ("SECRET_KEY", "change-me-strong-secret-key", "generated placeholder"),
        ("DB_PASSWORD", "change-me-strong-password", "generated placeholder"),
        ("ENVIRONMENT", "development", "ENVIRONMENT must be production."),
        ("DJANGO_ENVIRONMENT", "dev", "DJANGO_ENVIRONMENT must be production."),
        ("TASK_BACKEND", "huey", "TASK_BACKEND must be celery."),
    ],
)
def test_ninja_rejects_unsafe_values(tmp_path: Path, name: str, value: str, message: str) -> None:
    result = _run(_script(tmp_path), {**NINJA_ENV, name: value}, "check")
    assert result.returncode == 1
    assert message in result.stderr


def test_failed_check_starts_nothing(tmp_path: Path) -> None:
    marker = tmp_path / "started"
    env = {k: v for k, v in NINJA_ENV.items() if k != "SECRET_KEY"}
    result = _run(_script(tmp_path), env, "touch", str(marker))
    assert result.returncode == 1
    assert not marker.exists()


def test_workers_do_not_need_web_only_settings(tmp_path: Path) -> None:
    marker = tmp_path / "worker-ran"
    env = {k: v for k, v in NINJA_ENV.items() if k != "ALLOWED_HOSTS"}
    script = _script(tmp_path)
    assert _run(script, env, "touch", str(marker)).returncode == 0
    assert marker.exists()
    serve = _run(script, env, "serve")
    assert serve.returncode == 1
    assert "ALLOWED_HOSTS is not set." in serve.stderr


def test_disabled_task_backend_is_the_baked_value(tmp_path: Path) -> None:
    script = _script(tmp_path, task_backend=TaskBackend.NONE)
    assert _run(script, {**NINJA_ENV, "TASK_BACKEND": "none"}, "check").returncode == 0


def test_django_matt_rejects_debug_and_default_secret(tmp_path: Path) -> None:
    script = _script(tmp_path, backend_framework=BackendFramework.DJANGO_MATT)
    env = {
        "DEBUG": "true",
        "SECRET_KEY": "change-me-in-production",
        **{k: NINJA_ENV[k] for k in ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT")},
        "ALLOWED_HOSTS": "api.example.com",
    }
    result = _run(script, env, "check")
    assert "DEBUG must be false." in result.stderr
    assert "SECRET_KEY still holds a generated placeholder." in result.stderr
    assert _run(script, {**env, "DEBUG": "false", "SECRET_KEY": "x" * 50}, "check").returncode == 0


def test_fastapi_enforces_settings_validators(tmp_path: Path) -> None:
    script = _script(tmp_path, backend_framework=BackendFramework.FASTAPI)
    env = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql://u:p@db/app",
        "SECRET_KEY": "short",
        "JWT_SECRET_KEY": "short",
        "WEBAUTHN_RP_ID": "localhost",
        "WEBAUTHN_ORIGIN": "http://app.example.com",
        "REDIS_URL": "redis://cache:6379/0",
        "CELERY_BROKER_URL": "redis://cache:6379/1",
        "CELERY_RESULT_BACKEND": "redis://cache:6379/2",
        "CORS_ORIGINS": "https://app.example.com",
    }
    result = _run(script, env, "check")
    assert "DATABASE_URL must start with postgresql+asyncpg://." in result.stderr
    assert "SECRET_KEY is shorter than 32 characters." in result.stderr
    assert "SECRET_KEY and JWT_SECRET_KEY hold the same value." in result.stderr
    assert "WEBAUTHN_RP_ID holds a known default value." in result.stderr
    assert "WEBAUTHN_ORIGIN must start with https://." in result.stderr
    assert "CORS_ORIGINS must start with [." in result.stderr  # JSON list setting
    fixed = {
        **env,
        "DATABASE_URL": "postgresql+asyncpg://u:p@db/app",
        "SECRET_KEY": "a" * 32,
        "JWT_SECRET_KEY": "b" * 32,
        "WEBAUTHN_RP_ID": "app.example.com",
        "WEBAUTHN_ORIGIN": "https://app.example.com",
        "CORS_ORIGINS": '["https://app.example.com"]',
    }
    assert _run(script, fixed, "check").returncode == 0


def test_unresolved_platform_reference_is_rejected(tmp_path: Path) -> None:
    """A literal ${NAME} would otherwise pass as a non-empty public secret."""
    result = _run(_script(tmp_path), {**NINJA_ENV, "SECRET_KEY": "${SECRET_KEY}"}, "check")
    assert result.returncode == 1
    assert "SECRET_KEY holds an unresolved platform reference." in result.stderr


def test_app_port_overrides_platform_port(tmp_path: Path) -> None:
    """A Cloud Run sidecar must not take the ingress container's PORT."""
    env = {**NINJA_ENV, "PORT": "80", "APP_PORT": "8000"}
    result = _run(_script(tmp_path), env, "sh", "-c", "echo $PORT")
    assert result.stdout.strip() == "8000"


def _fake_bin(tmp_path: Path, name: str, body: str) -> dict[str, str]:
    """Put an executable ``name`` first on PATH; it records its argv and env."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    tool = bin_dir / name
    tool.write_text(f"#!/bin/sh\n{body}\n")
    tool.chmod(0o755)
    return {"PATH": f"{bin_dir}:{os.environ['PATH']}"}


def test_health_probe_sends_an_allowed_host_and_https_scheme(tmp_path: Path) -> None:
    """Probes bypass neither ALLOWED_HOSTS nor the TLS redirect; they speak like the edge."""
    log = tmp_path / "curl.args"
    path = _fake_bin(tmp_path, "curl", f'printf "%s\\n" "$@" > {log}')
    env = {**NINJA_ENV, **path, "ALLOWED_HOSTS": ".example.com,api.example.com"}
    assert _run(_script(tmp_path), env, "health").returncode == 0
    args = log.read_text().splitlines()
    assert "Host: example.com" in args
    assert "X-Forwarded-Proto: https" in args
    assert args[-1] == "http://127.0.0.1:8000/api/health/"


def test_health_probe_skips_the_startup_check(tmp_path: Path) -> None:
    """A probe must not re-run the preflight or start anything else."""
    path = _fake_bin(tmp_path, "curl", "exit 0")
    assert _run(_script(tmp_path), {**path, "ALLOWED_HOSTS": "a.example"}, "health").returncode == 0


def test_tls_target_requires_use_tls_for_the_web_process(tmp_path: Path) -> None:
    script = _script(tmp_path, deployment=DeploymentTarget.HETZNER)
    assert "USE_TLS must be true." in _run(script, NINJA_ENV, "check").stderr
    assert _run(script, {**NINJA_ENV, "USE_TLS": "true"}, "check").returncode == 0
    # Workers do not serve requests and need no web settings.
    assert _run(script, NINJA_ENV, "true").returncode == 0


def test_render_allows_its_own_health_check_hosts(tmp_path: Path) -> None:
    path = _fake_bin(tmp_path, "gunicorn", 'echo "$ALLOWED_HOSTS"')
    script = _script(tmp_path, deployment=DeploymentTarget.RENDER)
    env = {
        **NINJA_ENV,
        **path,
        "USE_TLS": "true",
        "RENDER": "true",
        "RENDER_EXTERNAL_HOSTNAME": "my-app-api.onrender.com",
    }
    result = _run(script, env, "serve")
    # localhost: Render's port detector probes with Host localhost:$PORT.
    assert result.stdout.strip() == "api.example.com,localhost,my-app-api.onrender.com"
    # Outside Render (no RENDER variable) nothing is added.
    del env["RENDER"]
    assert _run(script, env, "serve").stdout.strip() == "api.example.com"


def test_ecs_allows_only_its_own_task_ip_for_alb_checks(tmp_path: Path) -> None:
    path = _fake_bin(tmp_path, "gunicorn", 'echo "$ALLOWED_HOSTS"')
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"Networks": [{"IPv4Addresses": ["10.0.1.5"]}]}))
    script = _script(tmp_path, deployment=DeploymentTarget.AWS)
    env = {
        **NINJA_ENV,
        **path,
        "ALLOWED_HOSTS_INCLUDE_TASK_IP": "true",
        "ECS_CONTAINER_METADATA_URI_V4": meta.as_uri(),
    }
    assert _run(script, env, "serve").stdout.strip() == "api.example.com,10.0.1.5"
    del env["ECS_CONTAINER_METADATA_URI_V4"]
    failed = _run(script, env, "serve")
    assert failed.returncode == 1
    assert "The ECS task IP could not be read." in failed.stderr


def test_nestjs_requires_distinct_jwt_secrets(tmp_path: Path) -> None:
    script = _script(tmp_path, backend_framework=BackendFramework.NESTJS)
    env = {
        "NODE_ENV": "production",
        "DATABASE_URL": "postgres://u:p@db/app",
        "JWT_SECRET": "k" * 20,
        "JWT_REFRESH_SECRET": "k" * 20,
        "REDIS_URL": "redis://cache:6379",
    }
    assert "JWT_SECRET and JWT_REFRESH_SECRET hold" in _run(script, env, "check").stderr
    assert _run(script, {**env, "JWT_REFRESH_SECRET": "r" * 20}, "check").returncode == 0
