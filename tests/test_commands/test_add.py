"""Tests for the add command: expand existing projects with new layers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import typer
import yaml

from mattstack.commands.add import run_add

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NINJA_PYPROJECT = '[project]\nname = "test-backend"\ndependencies = ["django-ninja"]\n'
VITE_PACKAGE = {
    "name": "test-frontend",
    "scripts": {"dev": "vite", "type-check": "tsc --noEmit"},
    "devDependencies": {"vite": "^6.0.0"},
}


def _make_backend_project(path: Path, pyproject: str = NINJA_PYPROJECT) -> Path:
    """Create a minimal backend-only project structure."""
    path.mkdir(parents=True, exist_ok=True)
    backend = path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text(pyproject)
    (backend / "manage.py").write_text("#!/usr/bin/env python\n")
    (path / "Makefile").write_text(".DEFAULT_GOAL := help\n")
    return path


def _make_frontend_project(path: Path) -> Path:
    """Create a minimal frontend-only project structure."""
    path.mkdir(parents=True, exist_ok=True)
    frontend = path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(json.dumps(VITE_PACKAGE))
    (frontend / "src").mkdir()
    (path / "Makefile").write_text(".DEFAULT_GOAL := help\n")
    return path


def _make_fullstack_project(path: Path) -> Path:
    """Create a minimal fullstack project structure."""
    _make_backend_project(path)
    frontend = path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(json.dumps(VITE_PACKAGE))
    return path


def _mock_clone(url: str, dest: Path, *args: object, **kwargs: object) -> bool:
    """Simulate a git clone by creating the directory with expected files."""
    dest.mkdir(parents=True, exist_ok=True)
    if "django" in url or "fastapi" in url:
        (dest / "pyproject.toml").write_text('[project]\nname = "test"\n')
        (dest / "manage.py").write_text("#!/usr/bin/env python\n")
    elif "react" in url or "nextjs" in url:
        (dest / "package.json").write_text('{"name": "test"}\n')
        (dest / "src").mkdir(exist_ok=True)
    elif "swift" in url:
        (dest / "Package.swift").write_text("// swift\n")
    return True


def _stack_metadata(proj: Path) -> dict[str, object]:
    data = yaml.safe_load((proj / "mattstack.yml").read_text())
    return data["project"]


# ---------------------------------------------------------------------------
# Tests: run_add (integration with mocks)
# ---------------------------------------------------------------------------


@patch("mattstack.commands.add.remove_git_history")
@patch("mattstack.commands.add.clone_repo", side_effect=_mock_clone)
class TestRunAdd:
    def test_add_frontend_to_backend(self, mock_clone, mock_rm_git, tmp_path: Path) -> None:
        proj = _make_backend_project(tmp_path / "my-app")
        run_add("frontend", proj)
        assert (proj / "frontend" / "package.json").exists()
        mock_clone.assert_called_once()
        mock_rm_git.assert_called_once()
        # The regenerated Makefile is staged next to the user's file.
        assert "frontend" in (proj / "Makefile.mattstack-new").read_text().lower()

    def test_add_backend_to_frontend(self, mock_clone, mock_rm_git, tmp_path: Path) -> None:
        proj = _make_frontend_project(tmp_path / "my-app")
        run_add("backend", proj)
        assert (proj / "backend" / "pyproject.toml").exists()
        assert "backend" in (proj / "Makefile.mattstack-new").read_text().lower()

    def test_add_ios_to_fullstack(self, mock_clone, mock_rm_git, tmp_path: Path) -> None:
        proj = _make_fullstack_project(tmp_path / "my-app")
        run_add("ios", proj)
        assert (proj / "ios" / "Package.swift").exists()
        assert "ios" in (proj / "Makefile.mattstack-new").read_text().lower()

    def test_existing_root_files_stay_byte_identical(
        self, mock_clone, mock_rm_git, tmp_path: Path
    ) -> None:
        proj = _make_frontend_project(tmp_path / "my-app")
        (proj / "Makefile").write_bytes(b"custom:\n\techo hi\n")
        (proj / "README.md").write_bytes(b"mine\n")
        run_add("backend", proj)
        assert (proj / "Makefile").read_bytes() == b"custom:\n\techo hi\n"
        assert (proj / "README.md").read_bytes() == b"mine\n"
        # Missing root files are still created.
        assert (proj / "docker-compose.yml").exists()

    def test_force_replaces_existing_root_files(
        self, mock_clone, mock_rm_git, tmp_path: Path
    ) -> None:
        proj = _make_frontend_project(tmp_path / "my-app")
        (proj / "README.md").write_text("mine\n")
        run_add("backend", proj, force=True)
        assert (proj / "README.md").read_text() != "mine\n"
        assert not (proj / "README.md.mattstack-new").exists()

    def test_dry_run_does_not_clone_or_write(self, mock_clone, mock_rm_git, tmp_path: Path) -> None:
        proj = _make_backend_project(tmp_path / "my-app")
        before = sorted(p.name for p in proj.iterdir())
        run_add("frontend", proj, dry_run=True)
        mock_clone.assert_not_called()
        mock_rm_git.assert_not_called()
        assert sorted(p.name for p in proj.iterdir()) == before

    def test_add_frontend_with_custom_framework(
        self, mock_clone, mock_rm_git, tmp_path: Path
    ) -> None:
        proj = _make_backend_project(tmp_path / "my-app")
        run_add("frontend", proj, framework="react-vite-starter")
        url = mock_clone.call_args[0][0]
        assert "react-vite-starter" in url

    def test_add_backend_with_backend_framework(
        self, mock_clone, mock_rm_git, tmp_path: Path
    ) -> None:
        proj = _make_frontend_project(tmp_path / "my-app")
        run_add("backend", proj, framework="fastapi")
        assert "fastapi-boilerplate" in mock_clone.call_args[0][0]
        assert _stack_metadata(proj)["backend"]["framework"] == "fastapi"

    def test_existing_fastapi_backend_is_kept_in_templates(
        self, mock_clone, mock_rm_git, tmp_path: Path
    ) -> None:
        pyproject = '[project]\nname = "api"\ndependencies = ["fastapi"]\n'
        proj = _make_backend_project(tmp_path / "my-app", pyproject)
        run_add("frontend", proj)
        makefile = (proj / "Makefile.mattstack-new").read_text()
        assert "alembic" in makefile
        assert "manage.py" not in makefile
        assert _stack_metadata(proj)["backend"]["framework"] == "fastapi"

    def test_persisted_metadata_wins_over_detection(
        self, mock_clone, mock_rm_git, tmp_path: Path
    ) -> None:
        proj = _make_backend_project(tmp_path / "my-app", '[project]\nname = "api"\n')
        (proj / "mattstack.yml").write_text(
            "scope:\n  enforce: false\nproject:\n  variant: b2b\n"
            "  backend:\n    framework: django-matt\n    celery: false\n"
        )
        run_add("frontend", proj)
        meta = _stack_metadata(proj)
        assert meta["variant"] == "b2b"
        assert meta["backend"]["framework"] == "django-matt"
        assert meta["backend"]["celery"] is False
        assert yaml.safe_load((proj / "mattstack.yml").read_text())["scope"] == {"enforce": False}

    def test_unknown_backend_refuses_without_writing(
        self, mock_clone, mock_rm_git, tmp_path: Path
    ) -> None:
        proj = _make_backend_project(tmp_path / "my-app", '[project]\nname = "api"\n')
        before = sorted(p.name for p in proj.iterdir())
        with pytest.raises(typer.Exit) as exc:
            run_add("frontend", proj)
        assert exc.value.exit_code == 1
        mock_clone.assert_not_called()
        assert sorted(p.name for p in proj.iterdir()) == before

    def test_framework_must_match_component(self, mock_clone, mock_rm_git, tmp_path: Path) -> None:
        proj = _make_backend_project(tmp_path / "my-app")
        with pytest.raises(typer.Exit):
            run_add("frontend", proj, framework="fastapi")
        mock_clone.assert_not_called()


class TestRunAddRejections:
    def test_reject_add_existing_frontend(self, tmp_path: Path) -> None:
        proj = _make_fullstack_project(tmp_path / "my-app")
        with pytest.raises(typer.Exit):
            run_add("frontend", proj)

    def test_reject_add_existing_backend(self, tmp_path: Path) -> None:
        proj = _make_fullstack_project(tmp_path / "my-app")
        with pytest.raises(typer.Exit):
            run_add("backend", proj)

    def test_reject_add_existing_ios(self, tmp_path: Path) -> None:
        proj = _make_fullstack_project(tmp_path / "my-app")
        (proj / "ios").mkdir()
        with pytest.raises(typer.Exit):
            run_add("ios", proj)

    def test_reject_invalid_component(self, tmp_path: Path) -> None:
        proj = _make_backend_project(tmp_path / "my-app")
        with pytest.raises(typer.Exit):
            run_add("database", proj)

    def test_reject_nonexistent_path(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit):
            run_add("frontend", tmp_path / "does-not-exist")

    @patch("mattstack.commands.add.remove_git_history")
    @patch("mattstack.commands.add.clone_repo", return_value=False)
    def test_clone_failure_raises_exit(self, mock_clone, mock_rm_git, tmp_path: Path) -> None:
        proj = _make_backend_project(tmp_path / "my-app")
        with pytest.raises(typer.Exit):
            run_add("frontend", proj)
        assert not (proj / "mattstack.yml").exists()
