"""Tests for config module."""

from pathlib import Path

from mattstack.config import (
    ProjectConfig,
    Variant,
    normalize_name,
    source_env_var,
    to_python_package,
)


def test_normalize_name():
    assert normalize_name("My Cool App") == "my-cool-app"
    assert normalize_name("  hello_world  ") == "hello-world"
    assert normalize_name("test--app") == "test-app"
    assert normalize_name("UPPERCASE") == "uppercase"


def test_to_python_package():
    assert to_python_package("my-cool-app") == "my_cool_app"
    assert to_python_package("test") == "test"


def test_source_env_var_maps_repo_key_to_override_variable():
    assert source_env_var("django-ninja") == "MATTSTACK_SOURCE_DJANGO_NINJA"
    assert source_env_var("react-rsbuild-kibo") == "MATTSTACK_SOURCE_REACT_RSBUILD_KIBO"


def test_project_config_normalization(tmp_path: Path):
    config = ProjectConfig(name="My App", path=tmp_path / "my-app")
    assert config.name == "my-app"
    assert config.python_package_name == "my_app"
    assert config.display_name == "My App"


def test_project_config_properties(starter_fullstack_config: ProjectConfig):
    assert starter_fullstack_config.has_backend is True
    assert starter_fullstack_config.has_frontend is True
    assert starter_fullstack_config.is_fullstack is True
    assert starter_fullstack_config.is_b2b is False


def test_b2b_config(b2b_config: ProjectConfig):
    assert b2b_config.is_b2b is True
    assert b2b_config.variant == Variant.B2B


def test_backend_only_config(backend_only_config: ProjectConfig):
    assert backend_only_config.has_backend is True
    assert backend_only_config.has_frontend is False
    assert backend_only_config.is_fullstack is False


def test_frontend_only_config(frontend_only_config: ProjectConfig):
    assert frontend_only_config.has_backend is False
    assert frontend_only_config.has_frontend is True
    assert frontend_only_config.is_fullstack is False
