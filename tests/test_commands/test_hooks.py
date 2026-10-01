"""Tests for commands/hooks.py — Phase 21."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mattstack.commands.hooks import hooks_app
from mattstack.config import ProjectConfig
from mattstack.templates.pre_commit_config import generate_pre_commit_config

# Writes the hook file the way `pre-commit install --hook-type X` does, unless
# FAKE_PRE_COMMIT_SKIP names that hook type.
_FAKE_PRE_COMMIT = f"""#!{sys.executable}
import os, sys
from pathlib import Path
hook_type = sys.argv[sys.argv.index("--hook-type") + 1]
if hook_type not in os.environ.get("FAKE_PRE_COMMIT_SKIP", "").split(","):
    Path(".git/hooks", hook_type).write_text("#!/bin/sh\\nexec pre-commit hook-impl\\n")
"""


def _git_project(path: Path, monkeypatch: pytest.MonkeyPatch, tools: tuple[str, ...]) -> Path:
    """Return a git repository whose PATH has a fake pre-commit and ``tools``."""
    bin_dir = path / "bin"
    bin_dir.mkdir()
    scripts = {"pre-commit": _FAKE_PRE_COMMIT, **dict.fromkeys(tools, "#!/bin/sh\n")}
    for name, body in scripts.items():
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    # A user-wide core.hooksPath would move the hooks out of .git/hooks.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    project = path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    return project


# ---------------------------------------------------------------------------
# hooks install
# ---------------------------------------------------------------------------


class TestHooksInstall:
    def test_no_pre_commit_config_exits_1(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(hooks_app, ["install", "--path", str(tmp_path)])
        assert result.exit_code == 1
        assert ".pre-commit-config.yaml" in result.output

    def test_pre_commit_not_available_exits_1(self, tmp_path: Path) -> None:
        (tmp_path / ".pre-commit-config.yaml").write_text("repos: []")
        with patch("mattstack.commands.hooks.command_available", return_value=False):
            runner = CliRunner()
            result = runner.invoke(hooks_app, ["install", "--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "pre-commit is not installed" in result.output

    def test_pre_commit_install_failure_exits_1(self, tmp_path: Path) -> None:
        (tmp_path / ".pre-commit-config.yaml").write_text("repos: []")
        failed = MagicMock()
        failed.returncode = 1
        failed.stderr = "something went wrong"
        with (
            patch("mattstack.commands.hooks.command_available", return_value=True),
            patch("mattstack.commands.hooks.subprocess.run", return_value=failed),
        ):
            runner = CliRunner()
            result = runner.invoke(hooks_app, ["install", "--path", str(tmp_path)])
        assert result.exit_code == 1

    def test_ninja_config_installs_and_verifies_push_hook(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        starter_fullstack_config: ProjectConfig,
    ) -> None:
        project = _git_project(tmp_path, monkeypatch, ("uv", "just", "bun"))
        (project / ".pre-commit-config.yaml").write_text(
            generate_pre_commit_config(starter_fullstack_config)
        )
        result = CliRunner().invoke(hooks_app, ["install", "--path", str(project)])
        assert result.exit_code == 0, result.output
        # The backend gauntlet runs on push, so the pre-push hook must exist.
        assert (project / ".git/hooks/pre-push").is_file()
        assert (project / ".git/hooks/pre-commit").is_file()

    def test_missing_hook_after_install_is_a_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _git_project(tmp_path, monkeypatch, ())
        # Block-style stages: a push-only hook must still require the pre-push hook.
        (project / ".pre-commit-config.yaml").write_text(
            "repos:\n  - repo: local\n    hooks:\n      - id: x\n        stages:\n"
            "          - pre-push\n"
        )
        monkeypatch.setenv("FAKE_PRE_COMMIT_SKIP", "pre-push")
        result = CliRunner().invoke(hooks_app, ["install", "--path", str(project)])
        assert result.exit_code == 1
        assert "pre-push" in result.output

    def test_missing_hook_tool_stops_before_install(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        starter_fullstack_config: ProjectConfig,
    ) -> None:
        project = _git_project(tmp_path, monkeypatch, ())
        (project / ".pre-commit-config.yaml").write_text(
            generate_pre_commit_config(starter_fullstack_config)
        )
        with patch(
            "mattstack.commands.hooks.command_available", side_effect=lambda name: name != "just"
        ):
            result = CliRunner().invoke(hooks_app, ["install", "--path", str(project)])
        assert result.exit_code == 1
        assert "uv tool install rust-just" in result.output
        assert not (project / ".git/hooks/pre-commit").exists()


# ---------------------------------------------------------------------------
# hooks status
# ---------------------------------------------------------------------------


class TestHooksStatus:
    def test_no_git_hooks_dir_exits_1(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(hooks_app, ["status", "--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "No .git/hooks directory" in result.output

    def test_no_hooks_installed_shows_not_installed(self, tmp_path: Path) -> None:
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        runner = CliRunner()
        result = runner.invoke(hooks_app, ["status", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "not installed" in result.output

    def test_installed_hook_shows_installed(self, tmp_path: Path) -> None:
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "pre-commit").write_text("#!/bin/sh\npre-commit run\n")
        runner = CliRunner()
        result = runner.invoke(hooks_app, ["status", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "installed" in result.output

    def test_no_config_shows_info_message(self, tmp_path: Path) -> None:
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        runner = CliRunner()
        result = runner.invoke(hooks_app, ["status", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "No .pre-commit-config.yaml found" in result.output

    def test_config_present_but_no_hooks_warns(self, tmp_path: Path) -> None:
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        (tmp_path / ".pre-commit-config.yaml").write_text("repos: []")
        runner = CliRunner()
        result = runner.invoke(hooks_app, ["status", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "hooks install" in result.output

    def test_pre_commit_source_detected(self, tmp_path: Path) -> None:
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "pre-commit").write_text("#!/bin/sh\npre-commit run --hook-stage pre-commit\n")
        runner = CliRunner()
        result = runner.invoke(hooks_app, ["status", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "pre-commit" in result.output


# ---------------------------------------------------------------------------
# hooks run
# ---------------------------------------------------------------------------


class TestHooksRun:
    def test_no_pre_commit_exits_1(self, tmp_path: Path) -> None:
        (tmp_path / ".pre-commit-config.yaml").write_text("repos: []")
        with patch("mattstack.commands.hooks.command_available", return_value=False):
            runner = CliRunner()
            result = runner.invoke(hooks_app, ["run", "--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "pre-commit is not installed" in result.output

    def test_no_config_exits_1(self, tmp_path: Path) -> None:
        with patch("mattstack.commands.hooks.command_available", return_value=True):
            runner = CliRunner()
            result = runner.invoke(hooks_app, ["run", "--path", str(tmp_path)])
        assert result.exit_code == 1

    def test_all_hooks_pass_exits_0(self, tmp_path: Path) -> None:
        (tmp_path / ".pre-commit-config.yaml").write_text("repos: []")
        ok = MagicMock()
        ok.returncode = 0
        with (
            patch("mattstack.commands.hooks.command_available", return_value=True),
            patch("mattstack.commands.hooks.subprocess.run", return_value=ok),
        ):
            runner = CliRunner()
            result = runner.invoke(hooks_app, ["run", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "All hooks passed" in result.output

    def test_failing_hooks_exits_1(self, tmp_path: Path) -> None:
        (tmp_path / ".pre-commit-config.yaml").write_text("repos: []")
        fail = MagicMock()
        fail.returncode = 1
        with (
            patch("mattstack.commands.hooks.command_available", return_value=True),
            patch("mattstack.commands.hooks.subprocess.run", return_value=fail),
        ):
            runner = CliRunner()
            result = runner.invoke(hooks_app, ["run", "--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "Some hooks failed" in result.output
