"""Tests for mattstack dev: one listener per port, supervised host servers."""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

import pytest
import typer

from mattstack.commands.dev import _parse_services, run_dev

COMPOSE = """\
services:
  db:
    image: postgres:17-alpine
  redis:
    image: redis:7-alpine
  api-dev:
    build: .
  frontend-dev:
    build: .
"""

FAKE_DOCKER = """\
import json, os, sys, time
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps(["docker", *sys.argv[1:]]) + "\\n")
args = sys.argv[1:]
if args[:2] == ["compose", "ps"]:
    counter = os.environ["FAKE_LOG"] + ".ps"
    n = int(open(counter).read()) if os.path.exists(counter) else 0
    open(counter, "w").write(str(n + 1))
    api_state = "running" if n < 3 else "exited"
    print(json.dumps([
        {"Service": "api-dev", "Name": "x-api-1", "State": api_state, "Health": ""},
        {"Service": "frontend-dev", "Name": "x-web-1", "State": "running", "Health": ""},
    ]))
elif args[:3] == ["compose", "logs", "-f"]:
    print("api-dev-1  | Watching for file changes", flush=True)
    time.sleep(30)
"""

FAKE_UV_FAILS = """\
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps(["uv", *sys.argv[1:]]) + "\\n")
print("django.core.exceptions.ImproperlyConfigured: fake", flush=True)
sys.exit(3)
"""

FAKE_BUN_SERVES_THEN_EXITS = """\
import json, os, socket, sys, time
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps(["bun", *sys.argv[1:]]) + "\\n")
server = socket.socket()
server.bind(("127.0.0.1", int(os.environ["PORT"])))
server.listen()
print("VITE ready on port " + os.environ["PORT"], flush=True)
time.sleep(1.5)
sys.exit(0)
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _fake_bin(directory: Path, name: str, body: str) -> None:
    script = directory / name
    script.write_text(f"#!{sys.executable}\n{body}")
    script.chmod(0o755)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "app"
    (root / "backend").mkdir(parents=True)
    (root / "backend" / "manage.py").write_text("")
    (root / "backend" / "pyproject.toml").write_text(
        '[project]\nname = "api"\ndependencies = ["django-ninja"]\n'
    )
    (root / "frontend").mkdir()
    (root / "frontend" / "package.json").write_text(
        json.dumps({"scripts": {"dev": "vite"}, "devDependencies": {"vite": "^6"}})
    )
    (root / "docker-compose.yml").write_text(COMPOSE)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_bin(bin_dir, "docker", FAKE_DOCKER)
    _fake_bin(bin_dir, "uv", FAKE_UV_FAILS)
    _fake_bin(bin_dir, "bun", FAKE_BUN_SERVES_THEN_EXITS)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.jsonl"))
    for var in ("API_PORT", "FRONTEND_PORT", "DB_PORT", "REDIS_PORT"):
        monkeypatch.setenv(var, str(_free_port()))
    monkeypatch.setattr("mattstack.utils.package_manager._get_user_pm_override", lambda: None)
    return root


def _calls(project: Path) -> list[list[str]]:
    log = Path(os.environ["FAKE_LOG"])
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def _compose_up(calls: list[list[str]]) -> list[list[str]]:
    return [c for c in calls if c[:3] == ["docker", "compose", "up"]]


class TestParseServices:
    def test_none_returns_all(self) -> None:
        assert _parse_services(None) == {"docker", "backend", "frontend"}

    def test_strips_and_lowercases(self) -> None:
        assert _parse_services(" Backend,,frontend ") == {"backend", "frontend"}


class TestHostMode:
    def test_starts_only_infra_and_stops_when_backend_dies(self, project: Path) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            run_dev(project)
        assert exc_info.value.exit_code == 1

        calls = _calls(project)
        assert _compose_up(calls) == [["docker", "compose", "up", "-d", "--wait", "db", "redis"]]
        api_port = os.environ["API_PORT"]
        assert ["uv", "run", "python", "manage.py", "runserver", f"127.0.0.1:{api_port}"] in calls
        # The backend died before listening, so the frontend never started.
        assert not any(c[0] == "bun" for c in calls)

    def test_frontend_logs_visible_and_crash_is_reported(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            run_dev(project, services="frontend")
        assert exc_info.value.exit_code == 1

        port = os.environ["FRONTEND_PORT"]
        out = capsys.readouterr()
        assert f"[frontend] VITE ready on port {port}" in out.out
        assert "frontend exited with code 0" in out.out + out.err
        calls = _calls(project)
        assert ["bun", "run", "dev", "--port", port, "--strictPort"] in calls
        assert not _compose_up(calls)

    def test_port_conflict_does_not_launch_duplicate(self, project: Path) -> None:
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", int(os.environ["FRONTEND_PORT"])))
            busy.listen()
            with pytest.raises(typer.Exit) as exc_info:
                run_dev(project, services="frontend")
        assert exc_info.value.exit_code == 1
        assert not any(c[0] == "bun" for c in _calls(project))

    def test_missing_docker_fails_clearly(
        self,
        project: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        empty = tmp_path / "empty-bin"
        empty.mkdir()
        monkeypatch.setenv("PATH", str(empty))
        with pytest.raises(typer.Exit) as exc_info:
            run_dev(project, services="docker")
        assert exc_info.value.exit_code == 1
        assert "docker is not installed" in capsys.readouterr().err


class TestContainerMode:
    def test_supervises_app_containers_and_stops_them_when_one_exits(
        self,
        project: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr("mattstack.commands.dev.CONTAINER_POLL_INTERVAL", 0.05)
        with pytest.raises(typer.Exit) as exc_info:
            run_dev(project, mode="container")
        assert exc_info.value.exit_code == 1

        calls = _calls(project)
        assert _compose_up(calls) == [
            ["docker", "compose", "up", "-d", "--wait", "db", "redis", "api-dev", "frontend-dev"]
        ]
        # Only the app containers are stopped; db and redis keep running.
        assert calls[-1] == ["docker", "compose", "stop", "api-dev", "frontend-dev"]
        assert not any(c[0] in ("uv", "bun") for c in calls)
        out = capsys.readouterr()
        assert "[compose] api-dev-1  | Watching for file changes" in out.out
        assert "Container api-dev is exited" in out.err

    def test_no_docker_conflicts_with_container_mode(self, project: Path) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            run_dev(project, mode="container", no_docker=True)
        assert exc_info.value.exit_code == 1


def test_nonexistent_path_exits_1(tmp_path: Path) -> None:
    with pytest.raises(typer.Exit) as exc_info:
        run_dev(tmp_path / "nonexistent")
    assert exc_info.value.exit_code == 1


def test_empty_directory_has_nothing_to_start(tmp_path: Path) -> None:
    with pytest.raises(typer.Exit) as exc_info:
        run_dev(tmp_path)
    assert exc_info.value.exit_code == 1
