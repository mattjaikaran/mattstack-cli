"""Dependency commands fail when tools cannot verify a component."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mattstack.cli import app
from mattstack.commands import deps


@pytest.fixture
def project(tmp_path: Path) -> Path:
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text(
        '[project]\nname = "dependency-fixture"\nversion = "0.1.0"\ndependencies = []\n'
    )
    return tmp_path


@pytest.mark.parametrize("command", ["check", "audit"])
def test_missing_dependency_tool_fails(command: str, project: Path, tmp_path: Path) -> None:
    empty_path = tmp_path / "empty-tools"
    empty_path.mkdir()
    result = CliRunner().invoke(
        app, ["deps", command, "--path", str(project)], env={"PATH": str(empty_path)}
    )
    assert result.exit_code == 1


@pytest.mark.parametrize(
    ("returncode", "payload", "expected"),
    [
        (0, {"dependencies": []}, 0),
        (2, {"dependencies": []}, 1),
        (0, {}, 1),
        (0, "not-json", 1),
        (0, {"dependencies": [{}]}, 1),
        (0, {"dependencies": [{"name": "unknown", "skip_reason": "not on PyPI"}]}, 1),
        (
            1,
            {"dependencies": [{"name": "unsafe", "vulns": [{"id": "CVE-fixture"}]}]},
            1,
        ),
    ],
)
def test_backend_audit_reports_failure_or_vulnerabilities(
    returncode: int,
    payload: object,
    expected: int,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = payload if isinstance(payload, str) else json.dumps(payload)

    def tool_result(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, returncode, stdout, "scanner diagnostic")

    monkeypatch.setattr(deps, "_run", tool_result)
    result = CliRunner().invoke(app, ["deps", "audit", "--path", str(project)])
    assert result.exit_code == expected


def test_clean_frontend_does_not_hide_backend_audit_failure(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frontend = project / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text('{"name":"frontend","packageManager":"bun@1.3.11"}')

    def tool_result(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if cwd == frontend:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 2, "", "scanner unavailable")

    monkeypatch.setattr(deps, "_run", tool_result)
    result = CliRunner().invoke(app, ["deps", "audit", "--path", str(project)])
    assert result.exit_code == 1


@pytest.mark.parametrize("payload", ["not-json", '{"error":{"code":"EFAIL"}}'])
def test_failed_frontend_check_does_not_treat_error_payload_as_packages(
    payload: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "package.json").write_text('{"name":"frontend","packageManager":"npm@10"}')

    def tool_result(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 1, payload, "dependency lookup failed")

    monkeypatch.setattr(deps, "_run", tool_result)
    result = CliRunner().invoke(app, ["deps", "check", "--path", str(tmp_path)])
    assert result.exit_code == 1
