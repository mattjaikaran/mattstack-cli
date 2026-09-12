"""Tests for the init command — preset mode, config mode, error handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import click.exceptions
import pytest

from mattstack.commands.init import (
    _generate,
    _run_from_preset,
    _run_interactive,
    run_init,
)
from mattstack.config import FrontendFramework, ProjectConfig, ProjectType, Variant


def test_preset_creates_config(tmp_path: Path) -> None:
    """Preset mode should create a valid ProjectConfig."""
    with patch("mattstack.commands.init._generate") as mock_gen:
        mock_gen.return_value = True
        _run_from_preset("my-app", "starter-fullstack", False, tmp_path)
        config = mock_gen.call_args[0][0]
        assert config.name == "my-app"
        assert config.project_type == ProjectType.FULLSTACK
        assert config.variant == Variant.STARTER


def test_preset_with_ios(tmp_path: Path) -> None:
    with patch("mattstack.commands.init._generate") as mock_gen:
        mock_gen.return_value = True
        _run_from_preset("my-app", "starter-fullstack", True, tmp_path)
        config = mock_gen.call_args[0][0]
        assert config.include_ios is True


def test_bad_preset_exits(tmp_path: Path) -> None:
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        _run_from_preset("test", "nonexistent-preset", False, tmp_path)


def test_yaml_config_mode(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("name: my-app\ntype: backend-only\nvariant: starter\n")
    with patch("mattstack.commands.init._generate") as mock_gen:
        mock_gen.return_value = True
        run_init(config_file=str(cfg_file), output_dir=tmp_path)
        config = mock_gen.call_args[0][0]
        assert config.name == "my-app"
        assert config.project_type == ProjectType.BACKEND_ONLY


def test_yaml_config_bad_type(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("name: my-app\ntype: invalid-type\n")
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        run_init(config_file=str(cfg_file), output_dir=tmp_path)


def test_yaml_config_missing_name(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("type: fullstack\nvariant: starter\n")
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        run_init(config_file=str(cfg_file), output_dir=tmp_path)


def test_yaml_config_nonexistent_file(tmp_path: Path) -> None:
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        run_init(config_file=str(tmp_path / "missing.yaml"), output_dir=tmp_path)


def test_generate_existing_dir_exits(tmp_path: Path) -> None:
    proj_dir = tmp_path / "existing"
    proj_dir.mkdir()
    config = ProjectConfig(
        name="existing",
        path=proj_dir,
        project_type=ProjectType.FULLSTACK,
    )
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        _generate(config)


def test_generate_dry_run_skips_dir_check(tmp_path: Path) -> None:
    proj_dir = tmp_path / "existing"
    proj_dir.mkdir()
    config = ProjectConfig(
        name="existing",
        path=proj_dir,
        project_type=ProjectType.FULLSTACK,
        dry_run=True,
        init_git=False,
    )
    with patch("mattstack.generators.fullstack.FullstackGenerator.run", return_value=True):
        result = _generate(config)
    assert result is True


def test_generate_dry_run_does_not_write_gauntlet_toml(tmp_path: Path) -> None:
    """A dry run must not create the project directory or gauntlet.toml."""
    proj_dir = tmp_path / "preview"
    config = ProjectConfig(
        name="preview",
        path=proj_dir,
        project_type=ProjectType.BACKEND_ONLY,
        dry_run=True,
        init_git=False,
    )
    with patch("mattstack.generators.backend_only.BackendOnlyGenerator.run", return_value=True):
        result = _generate(config)
    assert result is True
    assert not proj_dir.exists()
    assert not (proj_dir / "gauntlet.toml").exists()


def test_generate_writes_gauntlet_toml(tmp_path: Path) -> None:
    """A real run writes gauntlet.toml with the Python adapter enabled."""
    proj_dir = tmp_path / "real-app"
    config = ProjectConfig(
        name="real-app",
        path=proj_dir,
        project_type=ProjectType.BACKEND_ONLY,
        init_git=False,
    )

    def _fake_run() -> bool:
        proj_dir.mkdir(parents=True, exist_ok=True)
        return True

    with patch(
        "mattstack.generators.backend_only.BackendOnlyGenerator.run",
        side_effect=_fake_run,
    ):
        _generate(config)
    config_file = proj_dir / "gauntlet.toml"
    assert config_file.exists()
    assert "[adapters.python]" in config_file.read_text()


def test_keyboard_interrupt_handling(tmp_path: Path) -> None:
    with (
        patch("mattstack.commands.init._run_interactive", side_effect=KeyboardInterrupt),
        pytest.raises((SystemExit, click.exceptions.Exit)),
    ):
        run_init(output_dir=tmp_path)


# ---------------------------------------------------------------------------
# Interactive wizard mode tests
# ---------------------------------------------------------------------------


def _mock_questionary_for_wizard(
    mock_q: object,
    *,
    name: str | None = "wizard-app",
    project_type: str = "fullstack",
    variant: str = "starter",
    backend_framework: str | None = "django-ninja",
    framework: str | None = "react-vite",
    ios: bool | None = False,
    celery: bool | None = True,
    confirm: bool | None = True,
) -> None:
    """Configure a mock questionary object for _run_interactive.

    The wizard calls questionary methods in this order:
    1. text() — project name
    2. select() — project type
    3. select() — variant
    4. select() — backend framework (only for fullstack / backend-only)
    5. select() — frontend framework (only for fullstack / frontend-only)
    6. confirm() — include iOS (only for fullstack)
    7. confirm() — include Celery (only for fullstack / backend-only)
    8. confirm() — "Generate project?" final confirmation

    We use side_effect lists on the .ask() return to handle the ordering.
    """
    # text().ask() — project name
    mock_q.text.return_value.ask.return_value = name

    # select().ask() — called 2-4 times depending on project type
    select_answers: list[str | None] = [project_type, variant]
    if backend_framework is not None and project_type in ("fullstack", "backend-only"):
        select_answers.append(backend_framework)
    if framework is not None:
        select_answers.append(framework)
    mock_q.select.return_value.ask.side_effect = select_answers

    # confirm().ask() — 1-3 calls depending on project type
    confirm_answers: list[bool | None] = []
    if project_type == "fullstack":
        confirm_answers.append(ios if ios is not None else False)
    if project_type in ("fullstack", "backend-only"):
        confirm_answers.append(celery if celery is not None else True)
    if confirm is not None:
        confirm_answers.append(confirm)
    mock_q.confirm.return_value.ask.side_effect = confirm_answers

    # questionary.Choice needs to be passthrough so the select() calls work
    mock_q.Choice = lambda title, value: value  # noqa: ARG005


def test_wizard_creates_fullstack(tmp_path: Path) -> None:
    """Interactive wizard should build a fullstack config with the chosen options."""
    with (
        patch("mattstack.commands.init._generate") as mock_gen,
        patch("mattstack.commands.init.questionary") as mock_q,
        patch(
            "mattstack.commands.init.get_git_user",
            return_value=("Test Author", "test@test.com"),
        ),
    ):
        mock_gen.return_value = True
        _mock_questionary_for_wizard(
            mock_q,
            name="wizard-app",
            project_type="fullstack",
            variant="starter",
            framework="react-vite",
            ios=False,
            celery=True,
            confirm=True,
        )

        _run_interactive(tmp_path)

        mock_gen.assert_called_once()
        config: ProjectConfig = mock_gen.call_args[0][0]
        assert config.name == "wizard-app"
        assert config.project_type == ProjectType.FULLSTACK
        assert config.variant == Variant.STARTER
        assert config.frontend_framework == FrontendFramework.REACT_VITE
        assert config.include_ios is False
        assert config.use_celery is True
        assert config.author_name == "Test Author"
        assert config.author_email == "test@test.com"


def test_wizard_creates_backend_only(tmp_path: Path) -> None:
    """Interactive wizard should create a backend-only project when selected."""
    with (
        patch("mattstack.commands.init._generate") as mock_gen,
        patch("mattstack.commands.init.questionary") as mock_q,
        patch(
            "mattstack.commands.init.get_git_user",
            return_value=("Test Author", "test@test.com"),
        ),
    ):
        mock_gen.return_value = True
        _mock_questionary_for_wizard(
            mock_q,
            name="backend-app",
            project_type="backend-only",
            variant="starter",
            framework=None,  # no framework prompt for backend-only
            ios=None,  # no iOS prompt for backend-only
            celery=True,
            confirm=True,
        )

        _run_interactive(tmp_path)

        mock_gen.assert_called_once()
        config: ProjectConfig = mock_gen.call_args[0][0]
        assert config.name == "backend-app"
        assert config.project_type == ProjectType.BACKEND_ONLY
        assert config.variant == Variant.STARTER
        assert config.use_celery is True


def test_wizard_cancel_on_name(tmp_path: Path) -> None:
    """Returning None from the name prompt should raise KeyboardInterrupt (caught by run_init)."""
    with (
        patch("mattstack.commands.init._generate") as mock_gen,
        patch("mattstack.commands.init.questionary") as mock_q,
        patch(
            "mattstack.commands.init.get_git_user",
            return_value=("Test Author", "test@test.com"),
        ),
        pytest.raises((SystemExit, click.exceptions.Exit)),
    ):
        mock_q.text.return_value.ask.return_value = None
        # run_init wraps KeyboardInterrupt into typer.Exit
        run_init(output_dir=tmp_path)
        mock_gen.assert_not_called()


def test_wizard_cancel_on_confirm(tmp_path: Path) -> None:
    """Declining the final confirmation should skip generation."""
    with (
        patch("mattstack.commands.init._generate") as mock_gen,
        patch("mattstack.commands.init.questionary") as mock_q,
        patch(
            "mattstack.commands.init.get_git_user",
            return_value=("Test Author", "test@test.com"),
        ),
    ):
        _mock_questionary_for_wizard(
            mock_q,
            name="wizard-app",
            project_type="fullstack",
            variant="starter",
            framework="react-vite",
            ios=False,
            celery=True,
            confirm=False,
        )

        _run_interactive(tmp_path)

        mock_gen.assert_not_called()


def test_wizard_default_name_skips_prompt(tmp_path: Path) -> None:
    """Passing default_name should skip the name prompt and use the provided name."""
    with (
        patch("mattstack.commands.init._generate") as mock_gen,
        patch("mattstack.commands.init.questionary") as mock_q,
        patch(
            "mattstack.commands.init.get_git_user",
            return_value=("Test Author", "test@test.com"),
        ),
    ):
        mock_gen.return_value = True
        # Only need select + confirm answers since name prompt is skipped
        select_answers: list[str] = ["fullstack", "starter", "django-ninja", "react-vite"]
        mock_q.select.return_value.ask.side_effect = select_answers
        mock_q.confirm.return_value.ask.side_effect = [False, True, True]  # ios, celery, confirm
        mock_q.Choice = lambda title, value: value  # noqa: ARG005

        _run_interactive(tmp_path, default_name="prenamed")

        # text() should never have been called
        mock_q.text.return_value.ask.assert_not_called()

        mock_gen.assert_called_once()
        config: ProjectConfig = mock_gen.call_args[0][0]
        assert config.name == "prenamed"


# ---------------------------------------------------------------------------
# YAML config E2E tests
# ---------------------------------------------------------------------------


def test_yaml_config_fullstack_creates_expected_config(tmp_path: Path) -> None:
    """E2E: init from YAML config with fullstack type builds correct ProjectConfig."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "name: yaml-test-project\n"
        "type: fullstack\n"
        "variant: starter\n"
        "frontend:\n"
        "  framework: react-vite-starter\n"
        "ios: false\n"
        "backend:\n"
        "  celery: false\n"
        "  redis: true\n"
        "deployment: docker\n"
    )
    with patch("mattstack.commands.init._generate") as mock_gen:
        mock_gen.return_value = True
        run_init(config_file=str(cfg_file), output_dir=tmp_path)

        mock_gen.assert_called_once()
        config: ProjectConfig = mock_gen.call_args[0][0]
        assert config.name == "yaml-test-project"
        assert config.project_type == ProjectType.FULLSTACK
        assert config.variant == Variant.STARTER
        assert config.frontend_framework == FrontendFramework.REACT_VITE_STARTER
        assert config.include_ios is False
        assert config.use_celery is False
        assert config.use_redis is True


def test_yaml_config_backend_only_e2e(tmp_path: Path) -> None:
    """E2E: init from YAML with backend-only type and B2B variant."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "name: api-service\n"
        "type: backend-only\n"
        "variant: b2b\n"
        "backend:\n"
        "  celery: true\n"
        "  redis: true\n"
        "deployment: railway\n"
        "author:\n"
        "  name: Test Dev\n"
        "  email: dev@test.com\n"
    )
    with patch("mattstack.commands.init._generate") as mock_gen:
        mock_gen.return_value = True
        run_init(config_file=str(cfg_file), output_dir=tmp_path)

        config: ProjectConfig = mock_gen.call_args[0][0]
        assert config.name == "api-service"
        assert config.project_type == ProjectType.BACKEND_ONLY
        assert config.variant == Variant.B2B
        assert config.use_celery is True
        assert config.use_redis is True
        assert config.author_name == "Test Dev"
        assert config.author_email == "dev@test.com"


def test_yaml_config_frontend_only_e2e(tmp_path: Path) -> None:
    """E2E: init from YAML with frontend-only type."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "name: my-frontend\ntype: frontend-only\nfrontend:\n  framework: react-vite\n"
    )
    with patch("mattstack.commands.init._generate") as mock_gen:
        mock_gen.return_value = True
        run_init(config_file=str(cfg_file), output_dir=tmp_path)

        config: ProjectConfig = mock_gen.call_args[0][0]
        assert config.name == "my-frontend"
        assert config.project_type == ProjectType.FRONTEND_ONLY
        assert config.frontend_framework == FrontendFramework.REACT_VITE
        # Frontend-only forces these off
        assert config.use_celery is False
        assert config.use_redis is False
        assert config.include_ios is False


def test_yaml_config_with_invalid_project_type_exits(tmp_path: Path) -> None:
    """YAML config with an invalid project type should exit with error."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("name: bad-app\ntype: nonexistent\n")

    with pytest.raises((SystemExit, click.exceptions.Exit)):
        run_init(config_file=str(cfg_file), output_dir=tmp_path)


def test_yaml_config_with_missing_name_exits(tmp_path: Path) -> None:
    """YAML config without a name field should exit with error."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("type: fullstack\nvariant: starter\n")

    with pytest.raises((SystemExit, click.exceptions.Exit)):
        run_init(config_file=str(cfg_file), output_dir=tmp_path)


def test_yaml_config_dry_run_flag(tmp_path: Path) -> None:
    """dry_run flag should be propagated to the config from YAML init."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("name: dry-run-test\ntype: fullstack\n")

    with patch("mattstack.commands.init._generate") as mock_gen:
        mock_gen.return_value = True
        run_init(config_file=str(cfg_file), output_dir=tmp_path, dry_run=True)

        config: ProjectConfig = mock_gen.call_args[0][0]
        assert config.dry_run is True


def test_yaml_config_with_ios_enabled(tmp_path: Path) -> None:
    """YAML config with ios: true should set include_ios on the config."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("name: ios-app\ntype: fullstack\nios: true\n")

    with patch("mattstack.commands.init._generate") as mock_gen:
        mock_gen.return_value = True
        run_init(config_file=str(cfg_file), output_dir=tmp_path)

        config: ProjectConfig = mock_gen.call_args[0][0]
        assert config.include_ios is True


def test_yaml_config_path_resolution(tmp_path: Path) -> None:
    """YAML config should create the project path under output_dir / name."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("name: path-test\ntype: fullstack\n")

    with patch("mattstack.commands.init._generate") as mock_gen:
        mock_gen.return_value = True
        custom_output = tmp_path / "projects"
        custom_output.mkdir()
        run_init(config_file=str(cfg_file), output_dir=custom_output)

        config: ProjectConfig = mock_gen.call_args[0][0]
        assert config.path == custom_output / "path-test"
