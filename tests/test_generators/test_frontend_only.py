"""Tests for FrontendOnlyGenerator — mocked git clone."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mattstack.config import ProjectConfig, ProjectType, Variant
from mattstack.generators.frontend_only import FrontendOnlyGenerator


def _make_config(tmp_path: Path, **kwargs) -> ProjectConfig:
    defaults = {
        "name": "test-frontend",
        "path": tmp_path / "test-frontend",
        "project_type": ProjectType.FRONTEND_ONLY,
        "variant": Variant.STARTER,
        "init_git": False,
    }
    defaults.update(kwargs)
    return ProjectConfig(**defaults)


def _mock_clone(url: str, dest: Path, branch: str = "main", depth: int = 1) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "package.json").write_text('{"name": "test"}\n')
    (dest / "src").mkdir()
    return True


@patch("mattstack.generators.base.clone_repo", side_effect=_mock_clone)
def test_frontend_generates_files(mock_clone, tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    gen = FrontendOnlyGenerator(config)
    result = gen.run()
    assert result is True
    assert config.path.exists()
    assert (config.path / "justfile").exists()
    assert (config.path / "README.md").exists()
    assert (config.path / ".gitignore").exists()


@patch("mattstack.generators.base.clone_repo", return_value=False)
def test_frontend_clone_failure(mock_clone, tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    gen = FrontendOnlyGenerator(config)
    result = gen.run()
    assert result is False
    assert not config.path.exists()


@patch("mattstack.generators.frontend_only.customize_frontend")
@patch("mattstack.generators.base.clone_repo", side_effect=_mock_clone)
def test_frontend_dry_run(mock_clone, mock_fe, tmp_path: Path) -> None:
    config = _make_config(tmp_path, dry_run=True)
    gen = FrontendOnlyGenerator(config)
    result = gen.run()
    assert result is True
    mock_clone.assert_not_called()
