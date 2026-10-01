"""Tests for mattstack verify --scope (scope enforcement)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import typer

from mattstack.commands.verify import (
    is_in_scope,
    parse_porcelain_z,
    parse_scope_file,
    run_verify,
    verify_scope,
)


def test_parse_scope_file() -> None:
    content = "# comment\n\nsrc/mattstack/\ntests/\n  \ndocs/plans/*.md\n"
    assert parse_scope_file(content) == ["src/mattstack/", "tests/", "docs/plans/*.md"]


def test_is_in_scope_dir_prefix() -> None:
    scope = ["src/mattstack/"]
    assert is_in_scope("src/mattstack/cli.py", scope) is True
    assert is_in_scope("docs/readme.md", scope) is False


def test_is_in_scope_glob() -> None:
    scope = ["docs/plans/*.md"]
    assert is_in_scope("docs/plans/plan.md", scope) is True
    assert is_in_scope("docs/plans/plan.txt", scope) is False


def test_is_in_scope_exact() -> None:
    assert is_in_scope("pyproject.toml", ["pyproject.toml"]) is True
    assert is_in_scope("pyproject.toml", ["pyproject.yaml"]) is False


@pytest.mark.parametrize("scope", ["*", "*.py", "../other_pkg/*"])
def test_outside_root_cannot_match_scope_glob(scope: str) -> None:
    result = verify_scope(["../other_pkg/x.py"], [scope])
    assert result.out_of_scope == ["../other_pkg/x.py"]
    assert result.in_scope == []


def test_verify_scope_splits() -> None:
    result = verify_scope(
        ["src/mattstack/cli.py", "README.md"],
        ["src/mattstack/"],
    )
    assert result.in_scope == ["src/mattstack/cli.py"]
    assert result.out_of_scope == ["README.md"]


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create an isolated Git repository with one committed file."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "pkg" / "src").mkdir(parents=True)
    (root / "pkg" / "src" / "old.py").write_text("x = 1\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_parse_porcelain_z_rename_and_spaces() -> None:
    output = "R  pkg/src/new name.py\0pkg/src/old.py\0?? caf\u00e9 \u2192.md\0"
    assert parse_porcelain_z(output) == [
        "pkg/src/new name.py",
        "pkg/src/old.py",
        "caf\u00e9 \u2192.md",
    ]


def test_non_git_directory_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "SCOPE.md").write_text("src/\n", encoding="utf-8")
    with pytest.raises(typer.Exit) as exc:
        run_verify(tmp_path)
    assert exc.value.exit_code == 1


def test_subdirectory_scope_with_spaces_and_rename_passes(repo: Path) -> None:
    pkg = repo / "pkg"
    _git(repo, "mv", "pkg/src/old.py", "pkg/src/new name.py")
    (pkg / "src" / "caf\u00e9 file.py").write_text("y = 2\n")
    (pkg / "SCOPE.md").write_text("src/\nSCOPE.md\n", encoding="utf-8")

    run_verify(pkg)


def test_changes_outside_subdirectory_are_out_of_scope(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pkg = repo / "pkg"
    (pkg / "src" / "a.py").write_text("")
    (repo / "outside.py").write_text("")
    (pkg / "SCOPE.md").write_text("src/\nSCOPE.md\n", encoding="utf-8")

    with pytest.raises(typer.Exit) as exc:
        run_verify(pkg)

    assert exc.value.exit_code == 1
    assert "../outside.py" in capsys.readouterr().err


def test_run_verify_missing_scope_file(tmp_path: Path) -> None:
    with pytest.raises(typer.Exit) as exc:
        run_verify(tmp_path)

    assert exc.value.exit_code == 1
