"""Tests for multi-env and gitignore consolidation."""

from __future__ import annotations

from mattstack.config import ProjectConfig
from mattstack.templates.root_env import generate_env_production_example
from mattstack.templates.root_gitignore import generate_gitignore


def test_env_production_example_has_production_values(
    starter_fullstack_config: ProjectConfig,
) -> None:
    content = generate_env_production_example(starter_fullstack_config)
    assert "DEBUG=false" in content
    assert "@db:5432" in content
    assert "SECRET_KEY=" in content
    assert "ALLOWED_HOSTS=" in content


def test_env_production_example_has_frontend_api(
    starter_fullstack_config: ProjectConfig,
) -> None:
    content = generate_env_production_example(starter_fullstack_config)
    assert "VITE_API_BASE_URL=" in content


def test_gitignore_ignores_production_env(starter_fullstack_config: ProjectConfig) -> None:
    content = generate_gitignore(starter_fullstack_config)
    assert ".env.production" in content
