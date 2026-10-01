"""Tests for the upgrade command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import click.exceptions
import pytest

from mattstack.commands.upgrade import (
    SKIP_FILES,
    UpgradeReport,
    _compare_directories,
    _detect_components,
    run_upgrade,
)
from mattstack.stack import load_stack

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


NINJA_PYPROJECT = "[project]\nname = 'myapp'\ndependencies = ['django-ninja']\n"


def _make_project(
    tmp_path: Path,
    *,
    backend: bool = True,
    frontend: bool = True,
    pyproject: str = NINJA_PYPROJECT,
) -> Path:
    """Create a minimal project directory with backend and/or frontend."""
    proj = tmp_path / "test-proj"
    proj.mkdir()
    if backend:
        be = proj / "backend"
        be.mkdir()
        (be / "pyproject.toml").write_text(pyproject)
        (be / "manage.py").write_text("#!/usr/bin/env python\n")
        (be / "app").mkdir()
        (be / "app" / "models.py").write_text("# models\n")
    if frontend:
        fe = proj / "frontend"
        fe.mkdir()
        (fe / "package.json").write_text('{"name": "myapp", "devDependencies": {"vite": "6"}}\n')
        (fe / "src").mkdir()
        (fe / "src" / "App.tsx").write_text("export default function App() {}\n")
    return proj


def _make_upstream(tmp_path: Path, name: str = "upstream") -> Path:
    """Create a fake 'upstream' directory simulating a fresh boilerplate clone."""
    upstream = tmp_path / name
    upstream.mkdir()
    (upstream / "pyproject.toml").write_text("[project]\nname = 'myapp'\n")
    (upstream / "manage.py").write_text("#!/usr/bin/env python\n# updated\n")
    (upstream / "app").mkdir()
    (upstream / "app" / "models.py").write_text("# models\n")
    (upstream / "app" / "new_feature.py").write_text("# new feature\n")
    return upstream


def _fake_clone(target_dir: Path) -> bool:
    """Simulate clone_repo by creating files in the target directory."""
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "pyproject.toml").write_text("[project]\nname = 'myapp'\n")
    (target_dir / "manage.py").write_text("#!/usr/bin/env python\n# updated upstream\n")
    (target_dir / "app").mkdir()
    (target_dir / "app" / "models.py").write_text("# models\n")
    (target_dir / "app" / "new_feature.py").write_text("# new feature from upstream\n")
    return True


# ---------------------------------------------------------------------------
# _detect_components
# ---------------------------------------------------------------------------


def test_detect_backend_and_frontend(tmp_path: Path) -> None:
    proj = _make_project(tmp_path, backend=True, frontend=True)
    assert _detect_components(load_stack(proj)) == ["backend", "frontend"]


def test_detect_backend_only(tmp_path: Path) -> None:
    proj = _make_project(tmp_path, backend=True, frontend=False)
    assert _detect_components(load_stack(proj)) == ["backend"]


def test_detect_frontend_only(tmp_path: Path) -> None:
    proj = _make_project(tmp_path, backend=False, frontend=True)
    assert _detect_components(load_stack(proj)) == ["frontend"]


def test_detect_no_components(tmp_path: Path) -> None:
    proj = tmp_path / "empty"
    proj.mkdir()
    assert _detect_components(load_stack(proj)) == []


# ---------------------------------------------------------------------------
# _compare_directories
# ---------------------------------------------------------------------------


def test_compare_finds_new_files(tmp_path: Path) -> None:
    """Files in source but not in target are 'new'."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    (source / "existing.py").write_text("same")
    (target / "existing.py").write_text("same")
    (source / "new_file.py").write_text("new content")

    new, modified, deleted = _compare_directories(source, target)
    assert "new_file.py" in new
    assert modified == []
    assert deleted == []


def test_compare_finds_modified_files(tmp_path: Path) -> None:
    """Files that differ between source and target are 'modified'."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    (source / "file.py").write_text("upstream version")
    (target / "file.py").write_text("local version")

    new, modified, deleted = _compare_directories(source, target)
    assert new == []
    assert "file.py" in modified
    assert deleted == []


def test_compare_finds_deleted_files(tmp_path: Path) -> None:
    """Files in target but not in source are 'deleted'."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    (target / "old_file.py").write_text("removed upstream")

    new, modified, deleted = _compare_directories(source, target)
    assert new == []
    assert modified == []
    assert "old_file.py" in deleted


def test_compare_ignores_pycache(tmp_path: Path) -> None:
    """__pycache__ directories are excluded from comparison."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    cache = source / "__pycache__"
    cache.mkdir()
    (cache / "module.pyc").write_text("bytecode")

    new, modified, deleted = _compare_directories(source, target)
    assert new == []
    assert modified == []
    assert deleted == []


def test_compare_ignores_node_modules(tmp_path: Path) -> None:
    """node_modules directories are excluded from comparison."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    nm = source / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("module")

    new, modified, deleted = _compare_directories(source, target)
    assert new == []


def test_compare_skips_user_customized_files(tmp_path: Path) -> None:
    """Files in SKIP_FILES set are excluded even when different."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    for skip_file in SKIP_FILES:
        (source / skip_file).write_text("upstream version")
        (target / skip_file).write_text("user version")

    new, modified, deleted = _compare_directories(source, target)
    assert new == []
    assert modified == []
    assert deleted == []


def test_compare_nested_directories(tmp_path: Path) -> None:
    """Comparison works with nested directory structures."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    # Same file in nested dir
    (source / "app").mkdir()
    (target / "app").mkdir()
    (source / "app" / "models.py").write_text("same")
    (target / "app" / "models.py").write_text("same")

    # New nested file
    (source / "app" / "views.py").write_text("new view")

    new, modified, deleted = _compare_directories(source, target)
    assert any("views.py" in f for f in new)
    assert modified == []


def test_compare_identical_directories(tmp_path: Path) -> None:
    """Identical directories produce no changes."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    for d in (source, target):
        (d / "file.py").write_text("identical content")
        (d / "sub").mkdir()
        (d / "sub" / "nested.py").write_text("nested identical")

    new, modified, deleted = _compare_directories(source, target)
    assert new == []
    assert modified == []
    assert deleted == []


# ---------------------------------------------------------------------------
# run_upgrade — error handling
# ---------------------------------------------------------------------------


def test_nonexistent_project_path_errors(tmp_path: Path) -> None:
    """run_upgrade should exit with error for nonexistent path."""
    fake_path = tmp_path / "does-not-exist"
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        run_upgrade(fake_path)


def test_no_components_found_errors(tmp_path: Path) -> None:
    """run_upgrade should exit with error when no components are detected."""
    empty_proj = tmp_path / "empty"
    empty_proj.mkdir()
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        run_upgrade(empty_proj)


def test_invalid_component_name_errors(tmp_path: Path) -> None:
    """run_upgrade should exit with error for unknown component name."""
    proj = _make_project(tmp_path, backend=True, frontend=True)
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        run_upgrade(proj, component="database")


def test_component_not_in_project_errors(tmp_path: Path) -> None:
    """run_upgrade should exit when requested component doesn't exist in project."""
    proj = _make_project(tmp_path, backend=True, frontend=False)
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        run_upgrade(proj, component="frontend")


# ---------------------------------------------------------------------------
# run_upgrade — dry run
# ---------------------------------------------------------------------------


def test_dry_run_reports_changes_without_applying(tmp_path: Path) -> None:
    """Dry run should detect changes but not copy any files."""
    proj = _make_project(tmp_path, backend=True, frontend=False)

    def mock_clone(url: str, destination: Path, **kwargs: object) -> bool:
        return _fake_clone(destination)

    with (
        patch("mattstack.commands.upgrade.clone_repo", side_effect=mock_clone),
        patch("mattstack.commands.upgrade.remove_git_history"),
    ):
        run_upgrade(proj, component="backend", dry_run=True)

    # new_feature.py should NOT have been copied
    assert not (proj / "backend" / "app" / "new_feature.py").exists()
    # manage.py should still have original content
    assert "updated upstream" not in (proj / "backend" / "manage.py").read_text()


# ---------------------------------------------------------------------------
# run_upgrade — applying changes
# ---------------------------------------------------------------------------


def _mock_clone(url: str, destination: Path, **kwargs: object) -> bool:
    return _fake_clone(destination)


def test_new_files_are_copied_with_force(tmp_path: Path) -> None:
    """New upstream files are copied only with --force."""
    proj = _make_project(tmp_path, backend=True, frontend=False)

    with (
        patch("mattstack.commands.upgrade.clone_repo", side_effect=_mock_clone),
        patch("mattstack.commands.upgrade.remove_git_history"),
    ):
        run_upgrade(proj, component="backend", dry_run=False, force=True)

    new_file = proj / "backend" / "app" / "new_feature.py"
    assert "new feature from upstream" in new_file.read_text()


def test_forced_upgrade_preserves_symlink_directory(tmp_path: Path) -> None:
    proj = _make_project(tmp_path, backend=True, frontend=False)
    external = tmp_path / "user-owned"
    external.mkdir()
    owned = external / "new_feature.py"
    owned.write_text("Keep user data.")
    (proj / "backend/app").rename(tmp_path / "original-app")
    (proj / "backend/app").symlink_to(external, target_is_directory=True)
    with (
        patch("mattstack.commands.upgrade.clone_repo", side_effect=_mock_clone),
        patch("mattstack.commands.upgrade.remove_git_history"),
    ):
        run_upgrade(proj, component="backend", force=True)
    assert owned.read_text() == "Keep user data."
    assert (proj / "backend/app").is_symlink()


def test_no_files_written_without_force(tmp_path: Path) -> None:
    """Without --force, upgrade previews: new and modified files stay out."""
    proj = _make_project(tmp_path, backend=True, frontend=False)
    before = {p: p.read_bytes() for p in proj.rglob("*") if p.is_file()}

    with (
        patch("mattstack.commands.upgrade.clone_repo", side_effect=_mock_clone),
        patch("mattstack.commands.upgrade.remove_git_history"),
    ):
        run_upgrade(proj, component="backend", dry_run=False, force=False)

    after = {p: p.read_bytes() for p in proj.rglob("*") if p.is_file()}
    assert after == before


def test_modified_files_skipped_without_force(tmp_path: Path) -> None:
    """Modified files should NOT be overwritten without --force."""
    proj = _make_project(tmp_path, backend=True, frontend=False)
    original_content = (proj / "backend" / "manage.py").read_text()

    def mock_clone(url: str, destination: Path, **kwargs: object) -> bool:
        return _fake_clone(destination)

    with (
        patch("mattstack.commands.upgrade.clone_repo", side_effect=mock_clone),
        patch("mattstack.commands.upgrade.remove_git_history"),
    ):
        run_upgrade(proj, component="backend", dry_run=False, force=False)

    # manage.py should still have original content
    assert (proj / "backend" / "manage.py").read_text() == original_content


def test_modified_files_overwritten_with_force(tmp_path: Path) -> None:
    """Modified files should be overwritten with --force."""
    proj = _make_project(tmp_path, backend=True, frontend=False)

    def mock_clone(url: str, destination: Path, **kwargs: object) -> bool:
        return _fake_clone(destination)

    with (
        patch("mattstack.commands.upgrade.clone_repo", side_effect=mock_clone),
        patch("mattstack.commands.upgrade.remove_git_history"),
    ):
        run_upgrade(proj, component="backend", dry_run=False, force=True)

    # manage.py should now have upstream content
    content = (proj / "backend" / "manage.py").read_text()
    assert "updated upstream" in content


def test_clone_failure_exits_nonzero_without_up_to_date(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failed clone is a failure, never a clean 'up to date' result."""
    proj = _make_project(tmp_path, backend=True, frontend=False)

    with (
        patch("mattstack.commands.upgrade.clone_repo", return_value=False),
        patch("mattstack.commands.upgrade.remove_git_history"),
        pytest.raises((SystemExit, click.exceptions.Exit)) as exc,
    ):
        run_upgrade(proj, component="backend", dry_run=False, force=True)

    assert getattr(exc.value, "exit_code", getattr(exc.value, "code", None)) == 1
    output = capsys.readouterr()
    assert "up to date" not in (output.out + output.err).lower()


def _snapshot(proj: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in proj.rglob("*") if p.is_file()}


@pytest.mark.parametrize("frontend_package", ['{"devDependencies": {"vite": "6"}}', "{}"])
def test_forced_upgrade_writes_nothing_when_a_later_component_fails(
    tmp_path: Path, frontend_package: str
) -> None:
    """A failed frontend clone or unknown frontend blocks the backend writes too."""
    proj = _make_project(tmp_path, backend=True, frontend=True)
    (proj / "frontend" / "package.json").write_text(frontend_package)
    before = _snapshot(proj)

    def clone(url: str, destination: Path, **kwargs: object) -> bool:
        return _fake_clone(destination) if "django" in url else False

    with (
        patch("mattstack.commands.upgrade.clone_repo", side_effect=clone),
        patch("mattstack.commands.upgrade.remove_git_history"),
        pytest.raises((SystemExit, click.exceptions.Exit)),
    ):
        run_upgrade(proj, dry_run=False, force=True)

    assert _snapshot(proj) == before


# ---------------------------------------------------------------------------
# run_upgrade — upstream selection
# ---------------------------------------------------------------------------


def _clone_urls(proj: Path, **kwargs: object) -> list[str]:
    urls: list[str] = []

    def record(url: str, destination: Path, **_: object) -> bool:
        urls.append(url)
        return _fake_clone(destination)

    with (
        patch("mattstack.commands.upgrade.clone_repo", side_effect=record),
        patch("mattstack.commands.upgrade.remove_git_history"),
    ):
        run_upgrade(proj, component="backend", dry_run=True, **kwargs)  # type: ignore[arg-type]
    return urls


def test_fastapi_backend_compares_against_fastapi_upstream(tmp_path: Path) -> None:
    pyproject = "[project]\nname = 'api'\ndependencies = ['fastapi']\n"
    proj = _make_project(tmp_path, frontend=False, pyproject=pyproject)
    assert _clone_urls(proj) == ["https://github.com/mattjaikaran/fastapi-boilerplate.git"]


def test_user_repo_override_is_used(tmp_path: Path) -> None:
    proj = _make_project(tmp_path, frontend=False)
    override = {"django-ninja": "https://example.com/team/ninja.git"}
    with patch("mattstack.user_config.get_user_repos", return_value=override):
        assert _clone_urls(proj) == ["https://example.com/team/ninja.git"]


def test_unknown_backend_fails_without_cloning(tmp_path: Path) -> None:
    proj = _make_project(tmp_path, frontend=False, pyproject="[project]\nname = 'x'\n")
    with (
        patch("mattstack.commands.upgrade.clone_repo") as clone,
        pytest.raises((SystemExit, click.exceptions.Exit)),
    ):
        run_upgrade(proj, component="backend", force=True)
    clone.assert_not_called()


# ---------------------------------------------------------------------------
# UpgradeReport dataclass
# ---------------------------------------------------------------------------


def test_upgrade_report_total_changes() -> None:
    report = UpgradeReport(
        component="backend",
        new_files=["a.py", "b.py"],
        modified_files=["c.py"],
        deleted_files=["d.py"],
    )
    assert report.total_changes == 4
    assert report.has_changes is True


def test_upgrade_report_no_changes() -> None:
    report = UpgradeReport(component="backend")
    assert report.total_changes == 0
    assert report.has_changes is False
