"""Tests for mattstack env command."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from mattstack.commands.env import (
    _find_env_pairs,
    _mask_value,
    run_env,
    run_env_check,
    run_env_show,
    run_env_sync,
)


class TestMaskValue:
    def test_empty_value_is_distinct_from_masked_secret(self) -> None:
        assert _mask_value("") == "(empty)"
        assert _mask_value("") != _mask_value("abc")

    def test_short_value_masks_fully(self) -> None:
        assert _mask_value("ab") == "**"
        assert _mask_value("a") == "*"

    def test_long_value_shows_first_three(self) -> None:
        assert _mask_value("secretkey123") == "sec***"
        assert _mask_value("abc") == "***"


class TestFindEnvPairs:
    def test_finds_root_example_actual_pair(self, tmp_path: Path) -> None:
        (tmp_path / ".env.example").write_text("FOO=bar\n")
        pairs = _find_env_pairs(tmp_path)
        assert len(pairs) >= 1
        ex, act = pairs[0]
        assert ex.name == ".env.example"
        assert act.name == ".env"

    def test_finds_backend_pair(self, tmp_path: Path) -> None:
        backend = tmp_path / "backend"
        backend.mkdir()
        (backend / ".env.example").write_text("FOO=bar\n")
        pairs = _find_env_pairs(tmp_path)
        assert any(".env.example" in str(p[0]) and "backend" in str(p[0]) for p in pairs)

    def test_empty_when_no_examples(self, tmp_path: Path) -> None:
        assert _find_env_pairs(tmp_path) == []

    def test_frontend_example_pairs_with_the_file_in_use(self, tmp_path: Path) -> None:
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / ".env.example").write_text("VITE_API=x\n")
        (frontend / ".env").write_text("VITE_API=y\n")
        assert _find_env_pairs(tmp_path) == [(frontend / ".env.example", frontend / ".env")]

    def test_frontend_sync_creates_a_single_env_file(self, tmp_path: Path) -> None:
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / ".env.example").write_text("VITE_API=x\n")
        run_env_sync(tmp_path)
        assert (frontend / ".env.local").read_text() == "VITE_API=x\n"
        assert not (frontend / ".env").exists()


class TestRunEnvCheck:
    def test_matching_env_files(self, tmp_path: Path) -> None:
        (tmp_path / ".env.example").write_text("FOO=bar\nBAZ=qux\n")
        (tmp_path / ".env").write_text("FOO=bar\nBAZ=qux\n")
        run_env_check(tmp_path)
        # Should not raise

    def test_missing_vars_exit_1(self, tmp_path: Path) -> None:
        (tmp_path / ".env.example").write_text("FOO=bar\nBAZ=qux\nMISSING=val\n")
        (tmp_path / ".env").write_text("FOO=bar\nBAZ=qux\n")
        with pytest.raises(typer.Exit) as exc_info:
            run_env_check(tmp_path)
        assert exc_info.value.exit_code == 1

    def test_empty_and_extra_vars_do_not_fail(self, tmp_path: Path) -> None:
        (tmp_path / ".env.example").write_text("FOO=bar\nSECRET_KEY=x\n")
        (tmp_path / ".env").write_text("FOO=bar\nSECRET_KEY=\nLOCAL_ONLY=1\n")
        run_env_check(tmp_path)

    def test_check_from_nested_dir_uses_project_root(self, tmp_path: Path) -> None:
        (tmp_path / "mattstack.yml").write_text("version: 1\n")
        (tmp_path / ".env.example").write_text("FOO=bar\n")
        nested = tmp_path / "backend" / "api"
        nested.mkdir(parents=True)
        with pytest.raises(typer.Exit) as exc_info:
            run_env("check", nested)
        assert exc_info.value.exit_code == 1

    def test_nonexistent_path_exits_1(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            run_env_check(tmp_path / "nonexistent")
        assert exc_info.value.exit_code == 1


class TestRunEnvSync:
    def test_creates_missing_vars(self, tmp_path: Path) -> None:
        (tmp_path / ".env.example").write_text("FOO=bar\nBAZ=qux\n")
        run_env_sync(tmp_path)
        actual = tmp_path / ".env"
        assert actual.exists()
        content = actual.read_text()
        assert "FOO=" in content
        assert "BAZ=" in content

    def test_adds_only_missing_to_existing(self, tmp_path: Path) -> None:
        (tmp_path / ".env.example").write_text("FOO=bar\nBAZ=qux\n")
        (tmp_path / ".env").write_text("FOO=existing\n")
        run_env_sync(tmp_path)
        content = (tmp_path / ".env").read_text()
        assert "FOO=existing" in content
        assert "BAZ=" in content


class TestRunEnvShow:
    def test_masks_values(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("SECRET=mysecret123\n")
        run_env_show(tmp_path)
        # Output goes to console; we verify no exception and file was read
        # The function uses _mask_value internally
        assert (tmp_path / ".env").exists()

    def test_nonexistent_path_exits_1(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            run_env_show(tmp_path / "nonexistent")
        assert exc_info.value.exit_code == 1


class TestRunEnv:
    def test_invalid_action_exits_1(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            run_env("invalid", tmp_path)
        assert exc_info.value.exit_code == 1

    def test_check_action(self, tmp_path: Path) -> None:
        (tmp_path / ".env.example").write_text("FOO=bar\n")
        (tmp_path / ".env").write_text("FOO=bar\n")
        run_env("check", tmp_path)

    def test_sync_action(self, tmp_path: Path) -> None:
        (tmp_path / ".env.example").write_text("FOO=bar\n")
        run_env("sync", tmp_path)
        assert (tmp_path / ".env").exists()

    def test_show_action(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("FOO=bar\n")
        run_env("show", tmp_path)


class TestEnvCliIntegration:
    def test_env_check_via_cli(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from mattstack.cli import app

        (tmp_path / ".env.example").write_text("FOO=bar\n")
        (tmp_path / ".env").write_text("FOO=bar\n")
        runner = CliRunner()
        result = runner.invoke(app, ["env", "check", "--path", str(tmp_path)])
        assert result.exit_code == 0
