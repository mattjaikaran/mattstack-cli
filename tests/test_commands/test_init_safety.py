"""Consumer-visible initialization and filesystem safety regressions."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from mattstack.cli import app
from mattstack.config import ProjectConfig
from mattstack.generators.fullstack import FullstackGenerator

runner = CliRunner()


@pytest.mark.parametrize(
    "preset",
    [
        "starter-fullstack",
        "starter-api",
        "starter-frontend",
    ],
)
def test_dry_run_does_not_touch_existing_project(tmp_path: Path, preset: str) -> None:
    project = tmp_path / "existing"
    project.mkdir()
    sentinel = project / "notes.txt"
    sentinel.write_text("Keep this project.\n")

    result = runner.invoke(
        app, ["init", "existing", "--preset", preset, "--output", str(tmp_path), "--dry-run"]
    )

    assert result.exit_code == 0, result.output
    assert sentinel.read_text() == "Keep this project.\n"
    assert set(project.iterdir()) == {sentinel}


def test_clone_failure_is_a_command_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mattstack.generators.base.clone_repo", lambda *_args: False)
    result = runner.invoke(
        app, ["init", "broken", "--preset", "starter-api", "--output", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert not (tmp_path / "broken").exists()


def test_failed_generator_preserves_existing_directory(tmp_path: Path) -> None:
    project = tmp_path / "existing"
    project.mkdir()
    sentinel = project / "notes.txt"
    sentinel.write_text("Keep this project.\n")
    generator = FullstackGenerator(ProjectConfig(name="existing", path=project, init_git=False))
    assert generator.run() is False
    assert sentinel.read_text() == "Keep this project.\n"


def test_preset_requires_name_without_prompting() -> None:
    result = runner.invoke(app, ["init", "--preset", "starter-api"], input="")
    assert result.exit_code == 2


def test_noninteractive_initialization_requires_configuration() -> None:
    result = runner.invoke(app, ["init", "project"], input="")
    assert result.exit_code == 2
