"""YAML config file parser for mattstack init --config."""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from mattstack.config import (
    BackendFramework,
    DeploymentTarget,
    FrontendFramework,
    ProjectConfig,
    ProjectType,
    Variant,
    normalize_name,
)
from mattstack.utils.console import print_error


def load_config_file(config_path: Path, output_path: Path) -> ProjectConfig | None:
    """Parse a YAML config file into a ProjectConfig."""
    if not config_path.exists():
        print_error(f"Config file not found: {config_path}")
        return None

    try:
        data = yaml.safe_load(config_path.read_text())
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as e:
        print_error(f"Could not read YAML configuration: {e}")
        return None

    if not isinstance(data, dict):
        print_error("Config file must be a YAML mapping")
        return None

    raw_name = data.get("name")
    if not isinstance(raw_name, str) or not normalize_name(raw_name):
        print_error("Config file must include a nonempty string 'name'")
        return None
    name = normalize_name(raw_name)

    try:
        project_type = ProjectType(data.get("type", "fullstack"))
    except ValueError:
        valid = ", ".join(e.value for e in ProjectType)
        print_error(f"Invalid project type: '{data.get('type')}'. Valid: {valid}")
        return None

    try:
        variant = Variant(data.get("variant", "starter"))
    except ValueError:
        valid = ", ".join(e.value for e in Variant)
        print_error(f"Invalid variant: '{data.get('variant')}'. Valid: {valid}")
        return None

    backend = data.get("backend", {})
    frontend = data.get("frontend", {})
    author = data.get("author", {})
    if not all(isinstance(section, dict) for section in (backend, frontend, author)):
        print_error("backend, frontend, and author must be YAML mappings")
        return None
    for key, section, default in (
        ("ios", data, False),
        ("celery", backend, True),
        ("redis", backend, True),
    ):
        if not isinstance(section.get(key, default), bool):
            print_error(f"'{key}' must be true or false")
            return None
    try:
        backend_fw = BackendFramework(backend.get("framework", "django-ninja"))
    except ValueError:
        print_error(f"Invalid backend framework: '{backend.get('framework')}'")
        return None

    try:
        frontend_fw = FrontendFramework(frontend.get("framework", "react-vite"))
    except ValueError:
        valid = ", ".join(e.value for e in FrontendFramework)
        print_error(f"Invalid frontend framework: '{frontend.get('framework')}'. Valid: {valid}")
        return None

    try:
        deployment = DeploymentTarget(data.get("deployment", "docker"))
    except ValueError:
        valid = ", ".join(e.value for e in DeploymentTarget)
        print_error(f"Invalid deployment target: '{data.get('deployment')}'. Valid: {valid}")
        return None

    return ProjectConfig(
        name=name,
        path=output_path / name,
        project_type=project_type,
        variant=variant,
        frontend_framework=frontend_fw,
        backend_framework=backend_fw,
        include_ios=data.get("ios", False),
        use_celery=backend.get("celery", True),
        use_redis=backend.get("redis", True),
        deployment=deployment,
        author_name=author.get("name", ""),
        author_email=author.get("email", ""),
    )
