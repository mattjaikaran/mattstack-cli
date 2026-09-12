"""Tests for template generation."""

from mattstack.config import ProjectConfig
from mattstack.templates.docker_compose import generate_docker_compose
from mattstack.templates.docker_compose_override import generate_docker_compose_override
from mattstack.templates.docker_compose_prod import generate_docker_compose_prod
from mattstack.templates.pre_commit_config import generate_pre_commit_config
from mattstack.templates.root_claude_md import generate_claude_md
from mattstack.templates.root_env import generate_env_example
from mattstack.templates.root_gitignore import generate_gitignore
from mattstack.templates.root_makefile import generate_makefile
from mattstack.templates.root_readme import generate_readme


def test_makefile_fullstack(starter_fullstack_config: ProjectConfig):
    content = generate_makefile(starter_fullstack_config)
    assert "setup:" in content
    assert "backend-dev:" in content
    assert "frontend-dev:" in content
    assert "prod-build:" in content


def test_makefile_backend_only(backend_only_config: ProjectConfig):
    content = generate_makefile(backend_only_config)
    assert "backend-dev:" in content
    assert "frontend-dev:" not in content


def test_makefile_frontend_only(frontend_only_config: ProjectConfig):
    content = generate_makefile(frontend_only_config)
    assert "frontend-dev:" in content
    assert "backend-dev:" not in content


def test_makefile_has_docker_profiles(starter_fullstack_config: ProjectConfig):
    content = generate_makefile(starter_fullstack_config)
    assert "up-celery:" in content
    assert "--profile celery" in content
    assert "--env-file .env.production" in content


def test_docker_compose_fullstack(starter_fullstack_config: ProjectConfig):
    content = generate_docker_compose(starter_fullstack_config)
    assert "db:" in content
    assert "redis:" in content
    assert "api-dev:" in content
    assert "frontend-dev:" in content
    assert "test_project" in content  # python_package_name


def test_docker_compose_no_celery(starter_fullstack_config: ProjectConfig):
    starter_fullstack_config.use_celery = False
    content = generate_docker_compose(starter_fullstack_config)
    assert "celery-worker:" not in content


def test_env_example(starter_fullstack_config: ProjectConfig):
    content = generate_env_example(starter_fullstack_config)
    assert "SECRET_KEY" in content
    assert "VITE_API_BASE_URL" in content
    assert "POSTGRES_DB=test_project" in content


def test_gitignore_fullstack(starter_fullstack_config: ProjectConfig):
    content = generate_gitignore(starter_fullstack_config)
    assert "__pycache__" in content
    assert "node_modules" in content


def test_gitignore_frontend_only(frontend_only_config: ProjectConfig):
    content = generate_gitignore(frontend_only_config)
    assert "node_modules" in content
    assert "__pycache__" not in content


def test_readme(starter_fullstack_config: ProjectConfig):
    content = generate_readme(starter_fullstack_config)
    assert "# Test Project" in content
    assert "Django" in content
    assert "React" in content


def test_readme_b2b(b2b_config: ProjectConfig):
    content = generate_readme(b2b_config)
    assert "B2B" in content
    assert "generate_feature" in content


# --- Feature 1: Conditional template cleanup ---


def test_claude_md_frontend_only_no_backend_dev(frontend_only_config: ProjectConfig):
    """Frontend-only project should not include make backend-dev."""
    content = generate_claude_md(frontend_only_config)
    assert "make backend-dev" not in content
    assert "make frontend-dev" in content
    assert "make up" not in content


def test_claude_md_backend_only_no_frontend_dev(backend_only_config: ProjectConfig):
    """Backend-only project should not include make frontend-dev."""
    content = generate_claude_md(backend_only_config)
    assert "make frontend-dev" not in content
    assert "make backend-dev" in content
    assert "make up" in content


def test_readme_quickstart_frontend_only_no_migrate(frontend_only_config: ProjectConfig):
    """Frontend-only quickstart should skip migrate/superuser commands."""
    content = generate_readme(frontend_only_config)
    assert "backend-migrate" not in content
    assert "backend-superuser" not in content
    assert "make frontend-dev" in content


def test_docker_compose_prod_frontend_only_no_depends_on_api(
    frontend_only_config: ProjectConfig,
):
    """Frontend-only docker-compose.prod should not depend on api."""
    content = generate_docker_compose_prod(frontend_only_config)
    assert "depends_on" not in content
    assert "api" not in content
    assert "frontend:" in content


# --- Feature 2: Pre-commit hooks auto-setup ---


def test_pre_commit_config_fullstack(starter_fullstack_config: ProjectConfig):
    """Fullstack project should have both ruff and prettier hooks."""
    content = generate_pre_commit_config(starter_fullstack_config)
    assert "ruff" in content
    assert "prettier" in content
    assert "pre-commit-hooks" in content


def test_pre_commit_config_backend_only(backend_only_config: ProjectConfig):
    """Backend-only project should have ruff but not prettier."""
    content = generate_pre_commit_config(backend_only_config)
    assert "ruff" in content
    assert "prettier" not in content


def test_pre_commit_config_frontend_only(frontend_only_config: ProjectConfig):
    """Frontend-only project should have prettier but not ruff."""
    content = generate_pre_commit_config(frontend_only_config)
    assert "prettier" in content
    assert "ruff" not in content


# --- Feature 3: Docker compose override ---


def test_docker_compose_override_backend(backend_only_config: ProjectConfig):
    """Backend project should include api-dev section in override."""
    content = generate_docker_compose_override(backend_only_config)
    assert "api-dev" in content
    assert "frontend-dev" not in content


def test_docker_compose_override_frontend(frontend_only_config: ProjectConfig):
    """Frontend project should include frontend-dev section in override."""
    content = generate_docker_compose_override(frontend_only_config)
    assert "frontend-dev" in content
    assert "api-dev" not in content
