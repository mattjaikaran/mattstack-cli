"""Tests for mattstack db commands, using a fake `uv` so no database is touched."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mattstack.cli import app

FAKE_UV = """#!/bin/sh
case "$*" in
  *"manage.py shell -c"*)
    [ -n "$FAKE_TARGET" ] && echo "MATTSTACK_DB_TARGET=$FAKE_TARGET"
    exit "${FAKE_TARGET_RC:-0}";;
esac
echo "$3 $4 DB_NAME=$DB_NAME" >> "$FAKE_LOG"
case "$4" in
  dumpdata) echo "boom: relation missing" >&2; exit 3;;
esac
exit 0
"""

LOCAL = {
    "engine": "django.db.backends.postgresql",
    "host": "localhost",
    "port": "5432",
    "name": "foo",
    "debug": True,
    "settings": "api.settings",
}


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    backend = root / "backend"
    backend.mkdir(parents=True)
    (backend / "manage.py").write_text("")
    (backend / "pyproject.toml").write_text('dependencies = ["django-ninja>=1"]\n')
    (backend / "seed.py").write_text("")
    (root / ".env").write_text("export DB_NAME=foo\nDB_PASSWORD='supersecret'\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(FAKE_UV)
    uv.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "uv.log"))
    monkeypatch.setenv("FAKE_TARGET", json.dumps(LOCAL))
    monkeypatch.delenv("DB_NAME", raising=False)
    monkeypatch.delenv("DJANGO_SETTINGS_MODULE", raising=False)
    return root


def _calls(project: Path) -> list[str]:
    log = project.parent / "uv.log"
    return log.read_text().splitlines() if log.exists() else []


def _db(*args: str) -> tuple[int, str]:
    result = CliRunner().invoke(app, ["db", *args])
    return result.exit_code, result.output


def test_seed_fresh_without_tty_or_yes_does_not_flush(project: Path) -> None:
    code, output = _db("seed", "--fresh", "-p", str(project))
    assert code == 1
    assert "--yes" in output
    assert _calls(project) == []


def test_seed_fresh_with_missing_seed_file_does_not_flush(project: Path) -> None:
    code, _ = _db("seed", "--fresh", "--yes", "-f", "nope.py", "-p", str(project))
    assert code == 1
    assert _calls(project) == []


def test_seed_fresh_with_yes_flushes_then_seeds(project: Path) -> None:
    code, _ = _db("seed", "--fresh", "--yes", "-p", str(project))
    assert code == 0
    assert [c.split()[1] for c in _calls(project)] == ["flush", "migrate", "DB_NAME=foo"]


def test_reset_with_yes_on_local_target(project: Path) -> None:
    code, output = _db("reset", "--yes", "-p", str(project))
    assert code == 0
    assert _calls(project) == ["manage.py flush DB_NAME=foo", "manage.py migrate DB_NAME=foo"]
    assert "localhost:5432/foo" in output
    assert "supersecret" not in output


def test_reset_with_seed_and_no_seed_file_does_not_flush(project: Path) -> None:
    (project / "backend" / "seed.py").unlink()
    code, _ = _db("reset", "--yes", "--seed", "-p", str(project))
    assert code == 1
    assert _calls(project) == []


@pytest.mark.parametrize(
    "override",
    [{"host": "db.prod.example.com"}, {"debug": False}, {"settings": "config.settings.production"}],
)
def test_reset_refuses_remote_or_production_without_force(
    project: Path, monkeypatch: pytest.MonkeyPatch, override: dict[str, object]
) -> None:
    monkeypatch.setenv("FAKE_TARGET", json.dumps({**LOCAL, **override}))
    code, output = _db("reset", "--yes", "-p", str(project))
    assert code == 1
    assert "--force" in output
    assert _calls(project) == []

    code, _ = _db("reset", "--yes", "--force", "-p", str(project))
    assert code == 0
    assert "manage.py flush DB_NAME=foo" in _calls(project)


@pytest.mark.parametrize(
    "override",
    [
        {"engine": "", "host": "", "name": ""},
        {"engine": "django.db.backends.dummy"},
        {"name": ""},
    ],
)
def test_reset_refuses_incomplete_or_unknown_target(
    project: Path, monkeypatch: pytest.MonkeyPatch, override: dict[str, object]
) -> None:
    monkeypatch.setenv("FAKE_TARGET", json.dumps({**LOCAL, **override}))
    code, _ = _db("reset", "--yes", "-p", str(project))
    assert code == 1
    assert _calls(project) == []


def test_reset_refuses_unverifiable_target(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_TARGET", "")
    monkeypatch.setenv("FAKE_TARGET_RC", "1")
    code, _ = _db("reset", "--yes", "-p", str(project))
    assert code == 1
    assert _calls(project) == []


def test_dump_failure_shows_stderr_and_exit_status(project: Path) -> None:
    code, output = _db("dump", "-o", "out.json", "-p", str(project))
    assert code == 3
    assert "boom: relation missing" in output


def test_non_django_backend_is_rejected(project: Path) -> None:
    (project / "backend" / "pyproject.toml").write_text('dependencies = ["fastapi"]\n')
    code, _ = _db("migrate", "-p", str(project))
    assert code == 1
    assert _calls(project) == []
