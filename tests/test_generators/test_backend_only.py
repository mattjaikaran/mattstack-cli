"""Tests for BackendOnlyGenerator — mocked git clone."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mattstack.config import ProjectConfig, ProjectType, Variant
from mattstack.generators.backend_only import BackendOnlyGenerator


def _make_config(tmp_path: Path, **kwargs) -> ProjectConfig:
    defaults = {
        "name": "test-api",
        "path": tmp_path / "test-api",
        "project_type": ProjectType.BACKEND_ONLY,
        "variant": Variant.STARTER,
        "init_git": False,
    }
    defaults.update(kwargs)
    return ProjectConfig(**defaults)


def _mock_clone(url: str, dest: Path, branch: str = "main", depth: int = 1) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    (dest / "manage.py").write_text("#!/usr/bin/env python\n")
    for f in [
        "Makefile",
        "docker-compose.yml",
        ".env",
        "Dockerfile",
        "README.md",
        "CLAUDE.md",
        ".gitignore",
        ".dockerignore",
    ]:
        (dest / f).write_text("x")
    return True


@patch("mattstack.generators.base.clone_repo", side_effect=_mock_clone)
def test_backend_generates_files(mock_clone, tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    gen = BackendOnlyGenerator(config)
    result = gen.run()
    assert result is True
    assert config.path.exists()
    assert (config.path / ".env.production.example").exists()
    assert (config.path / "Makefile").exists()
    assert (config.path / "docker-compose.yml").exists()
    assert (config.path / "README.md").exists()


@patch("mattstack.generators.base.clone_repo", side_effect=_mock_clone)
def test_backend_consolidates_boilerplate_files(mock_clone, tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    gen = BackendOnlyGenerator(config)
    result = gen.run()
    assert result is True
    for f in [
        "Makefile",
        "docker-compose.yml",
        ".env",
        "Dockerfile",
        "CLAUDE.md",
        ".gitignore",
    ]:
        assert not (config.backend_dir / f).exists(), f"{f} should be removed"
    assert (config.backend_dir / "pyproject.toml").exists()
    assert (config.backend_dir / "manage.py").exists()
    # backend/pyproject.toml declares readme = "README.md"; keep it buildable.
    assert (config.backend_dir / "README.md").exists()


@patch("mattstack.generators.base.clone_repo", side_effect=_mock_clone)
def test_backend_keeps_readme_for_packaging(mock_clone, tmp_path: Path) -> None:
    """backend/pyproject.toml declares readme = "README.md", so it must survive."""
    config = _make_config(tmp_path)
    gen = BackendOnlyGenerator(config)
    assert gen.run() is True
    assert (config.backend_dir / "README.md").exists()
    assert (config.path / "docker" / "backend" / "Dockerfile").exists()


@patch("mattstack.generators.base.clone_repo", return_value=False)
def test_backend_clone_failure(mock_clone, tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    gen = BackendOnlyGenerator(config)
    result = gen.run()
    assert result is False
    assert not config.path.exists()


@patch("mattstack.generators.base.clone_repo", side_effect=_mock_clone)
def test_backend_b2b(mock_clone, tmp_path: Path) -> None:
    config = _make_config(tmp_path, variant=Variant.B2B)
    gen = BackendOnlyGenerator(config)
    result = gen.run()
    assert result is True


@patch("mattstack.generators.backend_only.customize_backend")
@patch("mattstack.generators.base.clone_repo", side_effect=_mock_clone)
def test_backend_dry_run(mock_clone, mock_be, tmp_path: Path) -> None:
    config = _make_config(tmp_path, dry_run=True)
    gen = BackendOnlyGenerator(config)
    result = gen.run()
    assert result is True
    mock_clone.assert_not_called()
