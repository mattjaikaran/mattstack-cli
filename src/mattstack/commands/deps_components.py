"""Select supported dependency manifests from the resolved project."""

from pathlib import Path

from mattstack.config import BackendFramework
from mattstack.project import resolve_project


def dependency_components(path: Path | None) -> tuple[Path | None, Path | None]:
    """Return backend and frontend directories with supported manifests."""
    project = resolve_project((path or Path.cwd()).resolve())
    backend = (
        project.backend_dir
        if (project.backend_dir / "pyproject.toml").exists()
        or (
            project.backend_framework == BackendFramework.NESTJS
            and (project.backend_dir / "package.json").exists()
        )
        else None
    )
    frontend = project.frontend_dir if (project.frontend_dir / "package.json").exists() else None
    return backend, frontend
