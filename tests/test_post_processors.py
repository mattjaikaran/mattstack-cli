"""Tests for post-processor modules."""

from __future__ import annotations

import json
from pathlib import Path

from mattstack.config import ProjectConfig, ProjectType, Variant
from mattstack.post_processors.b2b import print_b2b_instructions
from mattstack.post_processors.consolidate import consolidate_backend, consolidate_frontend
from mattstack.post_processors.customizer import customize_backend, customize_frontend
from mattstack.post_processors.frontend_config import setup_frontend_monorepo


def _make_config(tmp_path: Path, **kwargs) -> ProjectConfig:
    defaults = {
        "name": "test-proj",
        "path": tmp_path / "test-proj",
        "project_type": ProjectType.FULLSTACK,
        "variant": Variant.STARTER,
    }
    defaults.update(kwargs)
    return ProjectConfig(**defaults)


# --- setup_frontend_monorepo ---


def test_setup_frontend_monorepo_creates_env(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.frontend_dir.mkdir(parents=True)
    setup_frontend_monorepo(config)

    env_file = config.frontend_dir / ".env"
    assert env_file.exists()
    content = env_file.read_text()
    assert "VITE_MODE=django-spa" in content
    assert "VITE_API_BASE_URL=http://localhost:8000/api/v1" in content


def test_setup_frontend_monorepo_creates_env_monorepo(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.frontend_dir.mkdir(parents=True)
    setup_frontend_monorepo(config)

    env_mono = config.frontend_dir / ".env.monorepo"
    assert env_mono.exists()
    content = env_mono.read_text()
    assert "VITE_MODE=django-spa" in content


def test_setup_frontend_monorepo_creates_vite_config(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.frontend_dir.mkdir(parents=True)
    setup_frontend_monorepo(config)

    vite_config = config.frontend_dir / "vite.config.monorepo.ts"
    assert vite_config.exists()
    content = vite_config.read_text()
    assert "defineConfig" in content
    assert "proxy" in content
    assert '"http://localhost:8000"' in content


def test_setup_frontend_monorepo_noop_for_backend_only(tmp_path: Path) -> None:
    config = _make_config(tmp_path, project_type=ProjectType.BACKEND_ONLY)
    config.path.mkdir(parents=True)
    setup_frontend_monorepo(config)

    # Should not create any files since there's no frontend
    env_file = config.frontend_dir / ".env"
    assert not env_file.exists()


def test_setup_frontend_monorepo_noop_for_frontend_only(tmp_path: Path) -> None:
    config = _make_config(tmp_path, project_type=ProjectType.FRONTEND_ONLY)
    config.path.mkdir(parents=True)
    setup_frontend_monorepo(config)

    # Should not create any files since there's no backend
    env_file = config.frontend_dir / ".env"
    assert not env_file.exists()


# --- print_b2b_instructions ---


def test_print_b2b_instructions_runs_without_error(tmp_path: Path) -> None:
    config = _make_config(tmp_path, variant=Variant.B2B)
    # Should not raise any exception
    print_b2b_instructions(config)


def test_print_b2b_instructions_with_starter(tmp_path: Path) -> None:
    config = _make_config(tmp_path, variant=Variant.STARTER)
    # Should still work regardless of variant
    print_b2b_instructions(config)


# --- customize_backend ---


def test_customize_backend_updates_pyproject_name(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.backend_dir.mkdir(parents=True)

    pyproject = config.backend_dir / "pyproject.toml"
    pyproject.write_text('[project]\nname = "django-ninja-boilerplate"\n')

    customize_backend(config)

    content = pyproject.read_text()
    assert 'name = "test-proj-backend"' in content
    assert "django-ninja-boilerplate" not in content


def test_customize_backend_updates_python_package_name(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.backend_dir.mkdir(parents=True)

    pyproject = config.backend_dir / "pyproject.toml"
    pyproject.write_text('[project]\nname = "django_ninja_boilerplate"\n')

    customize_backend(config)

    content = pyproject.read_text()
    assert 'name = "test_proj_backend"' in content


def test_customize_backend_no_pyproject_is_noop(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.backend_dir.mkdir(parents=True)
    # Should not raise when pyproject.toml doesn't exist
    customize_backend(config)


def test_customize_backend_removes_cli_dir(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.backend_dir.mkdir(parents=True)

    cli_dir = config.backend_dir / "cli"
    cli_dir.mkdir()
    (cli_dir / "some_file.py").write_text("# placeholder")

    customize_backend(config)

    assert not cli_dir.exists()


# --- customize_frontend ---


def test_customize_frontend_updates_package_json(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.frontend_dir.mkdir(parents=True)

    package_json = config.frontend_dir / "package.json"
    package_json.write_text(json.dumps({"name": "react-boilerplate", "version": "0.1.0"}))

    customize_frontend(config)

    data = json.loads(package_json.read_text())
    assert data["name"] == "test-proj-frontend"
    assert data["version"] == "0.1.0"


def test_customize_frontend_no_package_json_is_noop(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.frontend_dir.mkdir(parents=True)
    # Should not raise when package.json doesn't exist
    customize_frontend(config)


# --- consolidate_monorepo ---


def _populate_backend_standalone(backend: Path) -> None:
    backend.mkdir(parents=True, exist_ok=True)
    for f in [
        "Makefile",
        "docker-compose.yml",
        "docker-compose.prod.yml",
        "docker-compose.single.yml",
        ".env",
        ".env.example",
        ".env.development",
        ".env.deploy.example",
        "Dockerfile",
        "Dockerfile.uv",
        "README.md",
        "CLAUDE.md",
        ".cursorrules",
        ".gitignore",
        ".dockerignore",
        ".pre-commit-config.yaml",
        "CHANGELOG.md",
    ]:
        (backend / f).write_text("x")
    for d in [
        "cli",
        "docker",
        "deploy",
        "nginx",
        "env",
        "media",
        "files",
        ".claude",
        ".cursor",
        ".vscode",
        ".omp",
        ".agents",
        ".continue",
        ".kiro",
        ".windsurf",
        ".tanstack",
    ]:
        (backend / d).mkdir(parents=True, exist_ok=True)
    # Files that must be preserved
    (backend / "pyproject.toml").write_text("[project]\n")
    (backend / "manage.py").write_text("x")
    (backend / "api").mkdir()
    (backend / "core").mkdir()


def _populate_frontend_standalone(frontend: Path) -> None:
    frontend.mkdir(parents=True, exist_ok=True)
    for f in [
        "Makefile",
        "docker-compose.yml",
        "docker-compose.monorepo.yml",
        ".env",
        ".env.example",
        "env.example",
        "env.monorepo.example",
        "Dockerfile",
        "Dockerfile.dev",
        "README.md",
        "CLAUDE.md",
        ".gitignore",
        ".dockerignore",
        "DEPLOYMENT.md",
        "nginx.conf",
    ]:
        (frontend / f).write_text("x")
    for d in ["nginx", "docs", "dist", ".claude", ".cursor", ".vscode", ".omp"]:
        (frontend / d).mkdir(parents=True, exist_ok=True)
    # Files that must be preserved
    (frontend / "package.json").write_text('{"name": "test"}\n')
    (frontend / "src").mkdir()
    (frontend / "vite.config.ts").write_text("export default {}")
    (frontend / "tsconfig.json").write_text("{}")
    (frontend / "eslint.config.js").write_text("export default []")
    (frontend / ".prettierrc").write_text("{}")


def test_consolidate_backend_removes_standalone_files(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    _populate_backend_standalone(config.backend_dir)

    consolidate_backend(config)

    for f in [
        "Makefile",
        "docker-compose.yml",
        "docker-compose.prod.yml",
        ".env",
        ".env.example",
        "Dockerfile",
        "Dockerfile.uv",
        "CLAUDE.md",
        ".gitignore",
        ".dockerignore",
        ".pre-commit-config.yaml",
    ]:
        assert not (config.backend_dir / f).exists(), f"{f} should be removed"
    for d in ["cli", "docker", "deploy", "nginx", "env", "media", "files", ".claude"]:
        assert not (config.backend_dir / d).exists(), f"{d}/ should be removed"
    assert (config.backend_dir / "pyproject.toml").exists()
    assert (config.backend_dir / "manage.py").exists()
    assert (config.backend_dir / "api").exists()
    assert (config.backend_dir / "core").exists()
    # backend/pyproject.toml declares readme = "README.md". Removing it makes
    # the package unbuildable, so consolidation must keep it.
    assert (config.backend_dir / "README.md").exists()


def test_consolidate_frontend_removes_standalone_files(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    _populate_frontend_standalone(config.frontend_dir)

    consolidate_frontend(config)

    for f in [
        "Makefile",
        "docker-compose.yml",
        ".env",
        ".env.example",
        "env.example",
        "Dockerfile",
        "Dockerfile.dev",
        "CLAUDE.md",
        ".gitignore",
        ".dockerignore",
        "DEPLOYMENT.md",
        "nginx.conf",
    ]:
        assert not (config.frontend_dir / f).exists(), f"{f} should be removed"
    for d in ["nginx", "docs", "dist", ".claude"]:
        assert not (config.frontend_dir / d).exists(), f"{d}/ should be removed"
    assert (config.frontend_dir / "package.json").exists()
    assert (config.frontend_dir / "src").exists()
    assert (config.frontend_dir / "vite.config.ts").exists()
    assert (config.frontend_dir / "tsconfig.json").exists()
    assert (config.frontend_dir / "eslint.config.js").exists()
    assert (config.frontend_dir / ".prettierrc").exists()
    assert (config.frontend_dir / "README.md").exists()
