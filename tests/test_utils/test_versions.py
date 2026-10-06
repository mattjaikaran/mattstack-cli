"""Generated files follow the versions the cloned backend pins."""

from __future__ import annotations

from pathlib import Path

from mattstack.config import ProjectConfig, ProjectType
from mattstack.templates.docker_compose import generate_docker_compose
from mattstack.templates.dockerfiles import generate_backend_dockerfile
from mattstack.utils.versions import snapshot_pins


def test_backend_pins_survive_consolidation(tmp_path: Path) -> None:
    """Consolidation deletes backend/docker-compose.yml and the Dockerfile, so
    the templates must read the snapshot taken right after the clone."""
    backend = tmp_path / "app" / "backend"
    backend.mkdir(parents=True)
    (backend / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.12"\n')
    compose = backend / "docker-compose.yml"
    compose.write_text(
        "services:\n  db:\n    image: ${POSTGRES_IMAGE:-postgres:16-alpine}\n"
        "  valkey:\n    image: valkey/valkey:7-alpine\n"
    )
    dockerfile = backend / "Dockerfile"
    dockerfile.write_text("COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /uvx /bin/\n")
    config = ProjectConfig(
        name="app", path=tmp_path / "app", project_type=ProjectType.BACKEND_ONLY, init_git=False
    )
    config.source_pins = snapshot_pins(config.path)
    compose.unlink()
    dockerfile.unlink()

    rendered = generate_docker_compose(config)
    assert "image: ${POSTGRES_IMAGE:-postgres:16-alpine}" in rendered
    assert "image: valkey/valkey:7-alpine" in rendered
    image = generate_backend_dockerfile(config)
    assert "COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /uvx /bin/" in image
    assert "FROM python:3.12-slim AS base" in image
