"""Tests for BaseGenerator methods."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from mattstack.config import ProjectConfig, ProjectType
from mattstack.generators.base import BaseGenerator


class _ConcreteGenerator(BaseGenerator):
    """Minimal concrete subclass for testing BaseGenerator methods."""

    @property
    def steps(self) -> list[tuple[str, Callable]]:
        return []


def _make_config(tmp_path: Path, **kwargs) -> ProjectConfig:
    defaults = {
        "name": "test-proj",
        "path": tmp_path / "test-proj",
        "project_type": ProjectType.FULLSTACK,
        "init_git": False,
    }
    defaults.update(kwargs)
    return ProjectConfig(**defaults)


def test_write_file(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.path.mkdir(parents=True)
    gen = _ConcreteGenerator(config)
    gen.write_file("test.txt", "hello world")
    assert (config.path / "test.txt").read_text() == "hello world"
    assert len(gen.created_files) == 1


def test_write_file_dry_run(tmp_path: Path) -> None:
    config = _make_config(tmp_path, dry_run=True)
    gen = _ConcreteGenerator(config)
    gen.write_file("test.txt", "hello world")
    assert not (config.path / "test.txt").exists()
    assert len(gen.created_files) == 0


def test_update_file(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.path.mkdir(parents=True)
    f = config.path / "test.txt"
    f.write_text("hello old world")
    gen = _ConcreteGenerator(config)
    gen.update_file(f, {"old": "new"})
    assert f.read_text() == "hello new world"


def test_update_file_warn_on_miss(tmp_path: Path, capsys) -> None:
    config = _make_config(tmp_path)
    config.path.mkdir(parents=True)
    f = config.path / "test.txt"
    f.write_text("hello world")
    gen = _ConcreteGenerator(config)
    gen.update_file(f, {"nonexistent": "replacement"}, warn_on_miss=True)
    # File should be unchanged
    assert f.read_text() == "hello world"


def test_update_file_missing(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    gen = _ConcreteGenerator(config)
    # Should not raise
    gen.update_file(config.path / "nonexistent.txt", {"a": "b"})


def test_update_json_file(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.path.mkdir(parents=True)
    f = config.path / "pkg.json"
    f.write_text(json.dumps({"name": "old", "version": "1.0"}))
    gen = _ConcreteGenerator(config)
    gen.update_json_file(f, {"name": "new"})
    data = json.loads(f.read_text())
    assert data["name"] == "new"
    assert data["version"] == "1.0"


def test_update_json_file_malformed(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.path.mkdir(parents=True)
    f = config.path / "bad.json"
    f.write_text("{broken json!!!")
    gen = _ConcreteGenerator(config)
    # Should not raise
    gen.update_json_file(f, {"name": "new"})
    # File should be unchanged (error handled gracefully)
    assert f.read_text() == "{broken json!!!"


def test_update_file_regex(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.path.mkdir(parents=True)
    f = config.path / "test.txt"
    f.write_text("version = 1.0.0")
    gen = _ConcreteGenerator(config)
    gen.update_file_regex(f, r"version = \d+\.\d+\.\d+", "version = 2.0.0")
    assert f.read_text() == "version = 2.0.0"


def test_cleanup_removes_owned_directory(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    gen = _ConcreteGenerator(config)
    assert gen.create_root_directory()
    (config.path / "some_file.txt").write_text("data")
    gen.cleanup()
    assert not config.path.exists()


def test_cleanup_preserves_existing_directory(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.path.mkdir()
    owned = config.path / "some_file.txt"
    owned.write_text("Keep user data.")
    gen = _ConcreteGenerator(config)
    assert not gen.create_root_directory()
    gen.cleanup()
    assert owned.read_text() == "Keep user data."


def test_cleanup_nonexistent(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    gen = _ConcreteGenerator(config)
    # Should not raise
    gen.cleanup()


def test_create_root_directory(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    gen = _ConcreteGenerator(config)
    result = gen.create_root_directory()
    assert result is True
    assert config.path.exists()


def test_create_root_directory_exists(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.path.mkdir(parents=True)
    gen = _ConcreteGenerator(config)
    result = gen.create_root_directory()
    assert result is False


def test_create_root_directory_dry_run(tmp_path: Path) -> None:
    config = _make_config(tmp_path, dry_run=True)
    gen = _ConcreteGenerator(config)
    result = gen.create_root_directory()
    assert result is True
    assert not config.path.exists()
