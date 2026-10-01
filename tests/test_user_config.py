"""Tests for user config loading and merging."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mattstack.user_config import (
    TEMPLATE_CONFIG,
    get_user_defaults,
    get_user_presets,
    get_user_repos,
    init_user_config,
    load_user_config,
)


def test_load_missing_config() -> None:
    with patch("mattstack.user_config.USER_CONFIG_PATH", Path("/nonexistent/config.yaml")):
        assert load_user_config() == {}


def test_load_valid_config(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("repos:\n  my-repo: https://example.com/repo.git\n")
    with patch("mattstack.user_config.USER_CONFIG_PATH", config_file):
        config = load_user_config()
        assert config["repos"]["my-repo"] == "https://example.com/repo.git"


def test_load_invalid_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(":\n  invalid: [yaml\n")
    with patch("mattstack.user_config.USER_CONFIG_PATH", config_file):
        assert load_user_config() == {}


def test_load_non_dict_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("- just a list\n")
    with patch("mattstack.user_config.USER_CONFIG_PATH", config_file):
        assert load_user_config() == {}


def test_get_user_repos(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "repos:\n  fastapi: https://example.com/fastapi.git\n"
        "  django-ninja: https://example.com/override.git\n"
    )
    with patch("mattstack.user_config.USER_CONFIG_PATH", config_file):
        repos = get_user_repos()
        assert repos["fastapi"] == "https://example.com/fastapi.git"
        assert repos["django-ninja"] == "https://example.com/override.git"


def test_get_user_repos_missing() -> None:
    with patch("mattstack.user_config.USER_CONFIG_PATH", Path("/nonexistent/config.yaml")):
        assert get_user_repos() == {}


def test_get_user_presets(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "presets:\n"
        "  my-fullstack:\n"
        "    description: Custom preset\n"
        "    project_type: fullstack\n"
        "    variant: starter\n"
    )
    with patch("mattstack.user_config.USER_CONFIG_PATH", config_file):
        presets = get_user_presets()
        assert "my-fullstack" in presets
        assert presets["my-fullstack"]["description"] == "Custom preset"


def test_get_user_defaults(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("defaults:\n  deployment: railway\n  use_celery: false\n")
    with patch("mattstack.user_config.USER_CONFIG_PATH", config_file):
        defaults = get_user_defaults()
        assert defaults["deployment"] == "railway"
        assert defaults["use_celery"] is False


def test_init_user_config(tmp_path: Path) -> None:
    config_dir = tmp_path / ".mattstack"
    config_file = config_dir / "config.yaml"
    with (
        patch("mattstack.user_config.USER_CONFIG_DIR", config_dir),
        patch("mattstack.user_config.USER_CONFIG_PATH", config_file),
    ):
        path = init_user_config()
        assert path == config_file
        assert config_file.exists()
        content = config_file.read_text()
        assert "mattstack user configuration" in content


def test_template_config_is_valid_yaml() -> None:
    import yaml

    data = yaml.safe_load(TEMPLATE_CONFIG)
    # Template is all comments, so it should parse as None
    assert data is None


def test_get_repo_urls_merges_user_config(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("repos:\n  custom-repo: https://example.com/custom.git\n")
    with patch("mattstack.user_config.USER_CONFIG_PATH", config_file):
        from mattstack.config import get_repo_urls

        urls = get_repo_urls()
        assert "django-ninja" in urls  # built-in
        assert "custom-repo" in urls  # user-defined


def test_get_all_presets_merges_user_presets(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "presets:\n"
        "  my-preset:\n"
        "    description: My custom preset\n"
        "    project_type: fullstack\n"
        "    variant: starter\n"
    )
    with patch("mattstack.user_config.USER_CONFIG_PATH", config_file):
        from mattstack.presets import get_all_presets

        presets = get_all_presets()
        assert "starter-fullstack" in presets  # built-in
        assert "my-preset" in presets  # user-defined
        assert presets["my-preset"].description == "My custom preset"


def test_user_preset_invalid_values_skipped(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "presets:\n  bad-preset:\n    description: Bad preset\n    project_type: nonexistent\n"
    )
    with patch("mattstack.user_config.USER_CONFIG_PATH", config_file):
        from mattstack.presets import get_all_presets

        presets = get_all_presets()
        assert "bad-preset" not in presets  # should be skipped


def test_user_preset_task_backend_and_actionable_skip(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "presets:\n"
        "  queue-app:\n    task_backend: huey\n    use_realtime: true\n"
        "  legacy-app:\n    use_celery: false\n"
        "  bad-app:\n    backend_framework: fastapi\n    task_backend: dramatiq\n"
    )
    with (
        patch("mattstack.user_config.USER_CONFIG_PATH", config_file),
        patch("mattstack.presets.print_warning") as warn,
    ):
        from mattstack.config import TaskBackend
        from mattstack.presets import get_all_presets

        presets = get_all_presets()

    queue = presets["queue-app"].to_config("queue-app", tmp_path / "q")
    assert (queue.task_backend, queue.use_realtime) == (TaskBackend.HUEY, True)
    legacy = presets["legacy-app"].to_config("legacy-app", tmp_path / "l")
    assert legacy.task_backend == TaskBackend.NONE
    assert "bad-app" not in presets
    message = warn.call_args[0][0]
    assert "bad-app" in message and str(config_file) in message and "celery, none" in message
