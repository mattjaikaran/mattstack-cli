"""Tests for the client command: frontend package manager wrapper."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from mattstack.commands.client import _resolve, client_app
from mattstack.utils.package_manager import PackageManager


class TestResolve:
    def test_resolve_from_root_with_frontend(self, tmp_path: Path) -> None:
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text("{}")
        (frontend / "bun.lockb").write_text("")
        work_dir, pm = _resolve(tmp_path, None)
        assert work_dir == frontend
        assert pm == PackageManager.BUN

    def test_resolve_from_root_without_frontend(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "yarn.lock").write_text("")
        work_dir, pm = _resolve(tmp_path, None)
        assert work_dir == tmp_path.resolve()
        assert pm == PackageManager.YARN

    def test_resolve_missing_package_json(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit):
            _resolve(tmp_path, None)

    def test_resolve_with_pm_override(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}")
        work_dir, pm = _resolve(tmp_path, "pnpm")
        assert pm == PackageManager.PNPM


class TestClientCommands:
    """Test client subcommands via the Typer test runner."""

    def _setup_project(self, tmp_path: Path) -> Path:
        """Create a minimal project with package.json."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "test", "scripts": {"dev": "vite", "build": "vite build"}})
        )
        (tmp_path / "bun.lockb").write_text("")
        return tmp_path

    @patch("mattstack.user_config.load_user_config")
    def test_which_reports_lockfile_over_user_default(self, mock_config, tmp_path: Path) -> None:
        mock_config.return_value = {"defaults": {"package_manager": "yarn"}}
        proj = self._setup_project(tmp_path)
        result = CliRunner().invoke(client_app, ["which", "--path", str(proj)])
        assert result.exit_code == 0
        assert "Package manager: bun" in result.output
        assert "bun.lockb" in result.output.replace("\n", "")

    def test_unknown_pm_override_fails(self, tmp_path: Path) -> None:
        proj = self._setup_project(tmp_path)
        result = CliRunner().invoke(client_app, ["install", "--path", str(proj), "--pm", "pip"])
        assert result.exit_code == 2

    @patch("mattstack.commands.client.run_pm_command")
    def test_exec_passes_options_after_separator(self, mock_run, tmp_path: Path) -> None:
        mock_run.return_value.returncode = 0
        proj = self._setup_project(tmp_path)
        args = ["exec", "--path", str(proj), "tsc", "--", "--noEmit", "-p", "app"]
        result = CliRunner().invoke(client_app, args)
        assert result.exit_code == 0
        assert mock_run.call_args[0][0].full == ["bunx", "tsc", "--noEmit", "-p", "app"]
