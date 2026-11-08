"""Post-processor to customize cloned repos (rename, rebrand)."""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404 -- CLI executes trusted project tools; no shell.
import tomllib
from pathlib import Path

from mattstack.config import BackendFramework, ProjectConfig
from mattstack.templates.dockerfiles import python_minor
from mattstack.utils.console import print_info, print_warning
from mattstack.utils.package_json import write_package_json
from mattstack.utils.process import command_available


def customize_backend(config: ProjectConfig) -> None:
    """Rename the backend project to match the project name."""
    if config.is_nestjs_backend:
        _customize_nestjs_backend(config)
    elif config.is_fastapi_backend:
        _customize_fastapi_backend(config)
    else:
        _customize_django_backend(config)
    _pin_python_version(config)
    _refresh_uv_lock(config.backend_dir)


def _pin_python_version(config: ProjectConfig) -> None:
    """Pin the backend to the image's Python so uv ignores a newer host.

    ``requires-python`` is a floor, so without a pin uv provisions the newest
    release and some wheels, such as ``ormsgpack``, fail to build.
    """
    if config.is_nestjs_backend or not config.backend_dir.is_dir():
        return
    pin = config.backend_dir / ".python-version"
    if pin.exists():
        return
    version = python_minor(config)
    pin.write_text(f"{version}\n")
    print_info(f"Pinned backend Python to {version}")


def _customize_django_backend(config: ProjectConfig) -> None:
    """Rename a Django backend project."""
    pyproject = config.backend_dir / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        previous = content
        content = content.replace(
            'name = "django-ninja-boilerplate"',
            f'name = "{config.name}-backend"',
        )
        content = content.replace(
            'name = "django_ninja_boilerplate"',
            f'name = "{config.python_package_name}_backend"',
        )
        if config.backend_framework == BackendFramework.DJANGO_MATT:
            content = content.replace(
                'name = "django-matt-starter"', f'name = "{config.name}-backend"'
            )
            content = content.replace('name = "myproject"', f'name = "{config.name}-backend"')
            content = content.replace(
                "git+ssh://git@github.com/mattjaikaran/django-matt.git",
                "git+https://github.com/mattjaikaran/django-matt.git",
            )
        pyproject.write_text(content)
        _sync_uv_lock(pyproject, previous)
        print_info(f"Renamed backend to {config.name}-backend")
    if config.backend_framework == BackendFramework.DJANGO_MATT:
        for source in config.backend_dir.rglob("*.py"):
            content = source.read_text()
            if "from django_matt import MattAPI" in content:
                source.write_text(re.sub(r"\bMattAPI\b", "DjangoMattAPI", content))

    # Remove boilerplate cli/ dir if somehow still present
    cli_dir = config.backend_dir / "cli"
    if cli_dir.exists():
        import shutil

        shutil.rmtree(cli_dir)


def _customize_fastapi_backend(config: ProjectConfig) -> None:
    """Rename a FastAPI backend project."""
    pyproject = config.backend_dir / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        previous = content
        content = content.replace(
            'name = "fastapi-postgres-boilerplate"',
            f'name = "{config.name}-backend"',
        )
        pyproject.write_text(content)
        _sync_uv_lock(pyproject, previous)
        print_info(f"Renamed backend to {config.name}-backend")


def _customize_nestjs_backend(config: ProjectConfig) -> None:
    """Rename a NestJS backend project via package.json."""
    package_json = config.backend_dir / "package.json"
    if package_json.exists():
        data = json.loads(package_json.read_text())
        data["name"] = f"{config.name}-backend"
        data["description"] = f"{config.display_name} API (NestJS)"
        write_package_json(package_json, data)
        _sync_bun_lock(config.backend_dir, data["name"])
        print_info(f"Renamed backend to {config.name}-backend")


def customize_frontend(config: ProjectConfig) -> None:
    """Rename the frontend project to match the project name."""
    package_json = config.frontend_dir / "package.json"
    if package_json.exists():
        data = json.loads(package_json.read_text())
        data["name"] = f"{config.name}-frontend"
        write_package_json(package_json, data)
        _sync_bun_lock(config.frontend_dir, data["name"])
        print_info(f"Renamed frontend to {config.name}-frontend")


def _refresh_uv_lock(backend_dir: Path) -> None:
    """Resolve the renamed project into ``uv.lock`` before the initial commit."""
    lock = backend_dir / "uv.lock"
    if not lock.is_file() or not command_available("uv"):
        return
    try:
        result = subprocess.run(  # nosec B603, B607 -- argv; trusted project tool.
            ["uv", "lock"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        print_warning(f"Could not refresh backend/uv.lock: {error}")
        return
    if result.returncode != 0:
        print_warning(
            f"Could not refresh backend/uv.lock; `just setup` will update it: "
            f"{result.stderr.strip()}"
        )
        return
    print_info("Refreshed backend/uv.lock for the generated project")


def _sync_uv_lock(pyproject: Path, previous: str) -> None:
    """Keep the editable project's locked name consistent after a rename."""
    lock = pyproject.with_name("uv.lock")
    if not lock.is_file():
        return
    old = tomllib.loads(previous)["project"]["name"].lower().replace("_", "-")
    new = tomllib.loads(pyproject.read_text())["project"]["name"].lower().replace("_", "-")
    content = lock.read_text()
    updated = re.sub(rf'(?m)^name = "{re.escape(old)}"$', f'name = "{new}"', content)
    if updated != content:
        lock.write_text(updated)


def _sync_bun_lock(directory: Path, name: str) -> None:
    """Keep the root workspace's text lock consistent after a rename."""
    lock = directory / "bun.lock"
    if not lock.is_file():
        return
    content = lock.read_text()
    updated = re.sub(
        r'("workspaces"\s*:\s*\{\s*""\s*:\s*\{[^{}]*"name"\s*:\s*)"[^"]*"',
        lambda match: match[1] + json.dumps(name),
        content,
        count=1,
    )
    if updated != content:
        lock.write_text(updated)
