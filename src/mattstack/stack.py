"""The stack of an existing project, for commands that write stack-specific files.

`add`, `upgrade`, `rules`, and `workflow` write files whose content depends
on the backend and frontend frameworks. They build that content from this
module, which reads persisted `mattstack.yml` metadata first and manifest
detection second (see `mattstack.project`). A framework that cannot be
determined stays unknown: callers must refuse instead of assuming
django-ninja or react-vite.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import typer

from mattstack.config import ProjectConfig, ProjectType
from mattstack.project import EnvFileError, ResolvedProject, resolve_project
from mattstack.stack_detection import has_backend_manifest
from mattstack.templates.stack_facts import Toolchain
from mattstack.utils.console import print_error
from mattstack.utils.package_manager import (
    detect_python_package_manager,
    resolve_package_manager,
)


def unknown_framework_message(components: list[str]) -> str:
    """Explain which framework is unknown and where to record it."""
    keys = " and ".join(f"`project.{component}.framework`" for component in components)
    return (
        f"Cannot determine the {' and '.join(components)} framework. Set {keys} in mattstack.yml."
    )


@dataclass(frozen=True)
class ProjectStack:
    """Components that exist in a project, with their resolved frameworks."""

    project: ResolvedProject
    has_backend: bool
    has_frontend: bool
    has_ios: bool

    @property
    def root(self) -> Path:
        return self.project.root

    @property
    def monorepo_layout(self) -> bool:
        """True when every present component lives in `backend/` or `frontend/`."""
        backend_ok = not self.has_backend or self.project.backend_dir == self.root / "backend"
        frontend_ok = not self.has_frontend or self.project.frontend_dir == self.root / "frontend"
        return backend_ok and frontend_ok

    def unknown_components(self) -> list[str]:
        """Return the present components whose framework is unknown."""
        unknown: list[str] = []
        if self.has_backend and self.project.backend_framework is None:
            unknown.append("backend")
        if self.has_frontend and self.project.frontend_framework is None:
            unknown.append("frontend")
        return unknown

    def config(
        self,
        *,
        has_backend: bool | None = None,
        has_frontend: bool | None = None,
        has_ios: bool | None = None,
    ) -> ProjectConfig:
        """Return a ProjectConfig for the components that exist (or will exist).

        Persisted choices (name, variant, Celery, Redis, deployment) come from
        the resolved project. Frameworks of unknown components keep the
        ProjectConfig defaults, so check ``unknown_components()`` first.
        """
        backend = self.has_backend if has_backend is None else has_backend
        frontend = self.has_frontend if has_frontend is None else has_frontend
        ios = self.has_ios if has_ios is None else has_ios
        base = self.project.config
        updates: dict[str, object] = {
            "path": self.root,
            "project_type": _project_type(backend, frontend),
            "include_ios": ios,
            "init_git": False,
            "dry_run": False,
        }
        if self.project.backend_framework is not None:
            updates["backend_framework"] = self.project.backend_framework
        if self.project.frontend_framework is not None:
            updates["frontend_framework"] = self.project.frontend_framework
        return replace(base, **updates)  # type: ignore[arg-type]

    def toolchain(self) -> Toolchain:
        """Return the package managers this project already uses."""
        project = self.project
        python_pm = detect_python_package_manager(project.backend_dir)
        if self.has_frontend:
            js_dir = project.frontend_dir
        elif self.has_backend:
            js_dir = project.backend_dir
        else:
            js_dir = self.root
        return Toolchain(python_pm=python_pm, js_pm=resolve_package_manager(js_dir).value)


def _project_type(has_backend: bool, has_frontend: bool) -> ProjectType:
    if has_backend and not has_frontend:
        return ProjectType.BACKEND_ONLY
    if has_frontend and not has_backend:
        return ProjectType.FRONTEND_ONLY
    return ProjectType.FULLSTACK


def load_stack(path: Path) -> ProjectStack:
    """Resolve the project at ``path`` and report which components exist.

    Exits with code 1 when the root .env cannot be parsed.
    """
    try:
        project = resolve_project(path)
    except EnvFileError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None
    # Presence comes from the filesystem, so stale metadata cannot claim a
    # component that was removed. Metadata only names the framework.
    backend_dir = project.backend_dir
    has_backend = has_backend_manifest(backend_dir) or (
        project.backend_framework is not None and (backend_dir / "package.json").is_file()
    )
    has_frontend = (project.frontend_dir / "package.json").is_file() and (
        project.frontend_dir != backend_dir or project.frontend_framework is not None
    )
    has_ios = (project.root / "ios").is_dir()
    return ProjectStack(
        project=project,
        has_backend=has_backend,
        has_frontend=has_frontend,
        has_ios=has_ios,
    )
