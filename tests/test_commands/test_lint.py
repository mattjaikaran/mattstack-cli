"""Tests for mattstack lint command."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

from mattstack.commands.lint import _has_backend, _has_frontend, run_lint


class TestHasBackend:
    def test_has_backend_when_pyproject_exists(self, tmp_path: Path) -> None:
        backend = tmp_path / "backend"
        backend.mkdir()
        (backend / "pyproject.toml").write_text('[project]\nname = "test"\n')
        assert _has_backend(tmp_path) is True

    def test_no_backend_when_pyproject_missing(self, tmp_path: Path) -> None:
        assert _has_backend(tmp_path) is False


class TestHasFrontend:
    def test_has_frontend_when_lint_script_exists(self, tmp_path: Path) -> None:
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text(json.dumps({"scripts": {"lint": "eslint ."}}))
        assert _has_frontend(tmp_path) is True

    def test_has_frontend_when_lint_fix_script_exists(self, tmp_path: Path) -> None:
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text(
            json.dumps({"scripts": {"lint:fix": "eslint . --fix"}})
        )
        assert _has_frontend(tmp_path) is True

    def test_no_frontend_when_no_lint_script(self, tmp_path: Path) -> None:
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text(json.dumps({"scripts": {"dev": "vite"}}))
        assert _has_frontend(tmp_path) is False

    def test_no_frontend_when_no_package_json(self, tmp_path: Path) -> None:
        assert _has_frontend(tmp_path) is False


class TestRunLint:
    def test_no_backend_or_frontend_exits_1(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            run_lint(tmp_path)
        assert exc_info.value.exit_code == 1

    def test_nonexistent_path_exits_1(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            run_lint(tmp_path / "nonexistent")
        assert exc_info.value.exit_code == 1

    def test_backend_lint_runs_when_backend_exists(self, tmp_path: Path) -> None:
        backend = tmp_path / "backend"
        backend.mkdir()
        (backend / "pyproject.toml").write_text('[project]\nname = "test"\n')
        with patch("mattstack.commands.lint.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            run_lint(tmp_path)
        mock_run.assert_called()
        call_args = mock_run.call_args[0][0]
        assert "ruff" in call_args

    def test_parallel_spawns_two_popen_calls(self, tmp_path: Path) -> None:
        backend = tmp_path / "backend"
        backend.mkdir()
        (backend / "pyproject.toml").write_text('[project]\nname = "test"\n')
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text(
            json.dumps({"scripts": {"lint": "eslint ."}, "packageManager": "bun@1.0.0"})
        )

        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = None

        with patch(
            "mattstack.commands.lint.subprocess.Popen", return_value=mock_proc
        ) as mock_popen:
            run_lint(tmp_path, parallel=True)

        assert mock_popen.call_count == 2
        all_args = [call[0][0] for call in mock_popen.call_args_list]
        assert any("ruff" in args for args in all_args)

    def test_parallel_returns_nonzero_when_backend_fails(self, tmp_path: Path) -> None:
        backend = tmp_path / "backend"
        backend.mkdir()
        (backend / "pyproject.toml").write_text('[project]\nname = "test"\n')
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text(
            json.dumps({"scripts": {"lint": "eslint ."}, "packageManager": "bun@1.0.0"})
        )

        be_proc = MagicMock()
        be_proc.stdout = iter(["error: bad code\n"])
        be_proc.returncode = 1
        be_proc.wait.return_value = None

        fe_proc = MagicMock()
        fe_proc.stdout = iter([])
        fe_proc.returncode = 0
        fe_proc.wait.return_value = None

        with (
            patch("mattstack.commands.lint.subprocess.Popen", side_effect=[be_proc, fe_proc]),
            pytest.raises(typer.Exit) as exc_info,
        ):
            run_lint(tmp_path, parallel=True)

        assert exc_info.value.exit_code == 1

    def test_parallel_returns_nonzero_when_frontend_fails(self, tmp_path: Path) -> None:
        backend = tmp_path / "backend"
        backend.mkdir()
        (backend / "pyproject.toml").write_text('[project]\nname = "test"\n')
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text(
            json.dumps({"scripts": {"lint": "eslint ."}, "packageManager": "bun@1.0.0"})
        )

        be_proc = MagicMock()
        be_proc.stdout = iter([])
        be_proc.returncode = 0
        be_proc.wait.return_value = None

        fe_proc = MagicMock()
        fe_proc.stdout = iter(["error: lint failed\n"])
        fe_proc.returncode = 1
        fe_proc.wait.return_value = None

        with (
            patch("mattstack.commands.lint.subprocess.Popen", side_effect=[be_proc, fe_proc]),
            pytest.raises(typer.Exit) as exc_info,
        ):
            run_lint(tmp_path, parallel=True)

        assert exc_info.value.exit_code == 1


def _fake_tool(bin_dir: Path, name: str, body: str) -> None:
    script = bin_dir / name
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(0o755)


class TestParallelFlags:
    def test_parallel_format_check_fails_on_unformatted_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = tmp_path / "backend"
        backend.mkdir()
        (backend / "pyproject.toml").write_text('[project]\nname = "test"\n')
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text(
            json.dumps({"scripts": {"lint": "eslint ."}, "packageManager": "bun@1.0.0"})
        )
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        # ruff check passes; ruff format --check reports unformatted code
        _fake_tool(bin_dir, "uv", 'case "$*" in *format*) echo "Would reformat"; exit 1;; esac')
        _fake_tool(bin_dir, "bun", "exit 0")
        monkeypatch.setenv("PATH", str(bin_dir))

        run_lint(tmp_path, parallel=True)  # without --format-check: passes
        with pytest.raises(typer.Exit) as exc_info:
            run_lint(tmp_path, parallel=True, format_check=True)
        assert exc_info.value.exit_code == 1

    def test_missing_executable_is_nonzero_with_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        backend = tmp_path / "backend"
        backend.mkdir()
        (backend / "pyproject.toml").write_text('[project]\nname = "test"\n')
        empty = tmp_path / "empty-bin"
        empty.mkdir()
        monkeypatch.setenv("PATH", str(empty))

        with pytest.raises(typer.Exit) as exc_info:
            run_lint(tmp_path)
        assert exc_info.value.exit_code == 1
        assert "Command not found: uv" in capsys.readouterr().err
