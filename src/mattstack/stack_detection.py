"""Conservative filesystem detection of backend and frontend stacks.

Every detector returns ``None`` for anything it does not recognise, so callers
can refuse instead of guessing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mattstack.config import BackendFramework, FrontendFramework

PYTHON_MANIFESTS = ("pyproject.toml", "requirements.txt")
_SETTINGS_DEFAULT = re.compile(r"""DJANGO_SETTINGS_MODULE["']\s*,\s*["']([A-Za-z_][\w.]*)["']""")
# path("api/", api.urls) — the NinjaAPI / MattAPI mount; admin.site.urls is skipped.
_API_MOUNT = re.compile(
    r"""path\(\s*r?["']([^"']*)["']\s*,\s*(?!admin\.site\.)[A-Za-z_][\w.]*\.urls\s*[,)]"""
)


def read_text(path: Path) -> str:
    """Return the file text, or "" when it is missing or unreadable."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _package_json(directory: Path) -> dict[str, Any]:
    try:
        data = json.loads((directory / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _deps(pkg: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key in ("dependencies", "devDependencies"):
        value = pkg.get(key)
        if isinstance(value, dict):
            merged.update(value)
    return merged


def mentions_package(text: str, package: str) -> bool:
    """True when ``package`` appears as a whole dependency name in ``text``."""
    pattern = rf"(?<![A-Za-z0-9_.-]){re.escape(package)}(?![A-Za-z0-9_.-])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def python_manifest_text(backend: Path) -> str:
    return "\n".join(read_text(backend / name) for name in PYTHON_MANIFESTS)


def has_backend_manifest(backend: Path) -> bool:
    """True for a Django/Python backend or a NestJS package in ``backend``."""
    if (backend / "manage.py").is_file() or any(
        (backend / name).is_file() for name in PYTHON_MANIFESTS
    ):
        return True
    return "@nestjs/core" in _deps(_package_json(backend))


def detect_backend_framework(backend: Path) -> BackendFramework | None:
    if not has_backend_manifest(backend):
        return None
    if "@nestjs/core" in _deps(_package_json(backend)):
        return BackendFramework.NESTJS
    text = python_manifest_text(backend)
    if mentions_package(text, "django-matt"):
        return BackendFramework.DJANGO_MATT
    if mentions_package(text, "fastapi"):
        return BackendFramework.FASTAPI
    if mentions_package(text, "django-ninja") or mentions_package(text, "django-ninja-extra"):
        return BackendFramework.DJANGO_NINJA
    return None


def detect_frontend_framework(frontend: Path) -> FrontendFramework | None:
    pkg = _package_json(frontend)
    if not pkg:
        return None
    deps = _deps(pkg)

    def has_config(stem: str) -> bool:
        return any(
            (frontend / f"{stem}.config.{ext}").is_file() for ext in ("ts", "js", "mjs", "cjs")
        )

    if "next" in deps or has_config("next"):
        return FrontendFramework.NEXTJS
    if "@rsbuild/core" in deps or has_config("rsbuild"):
        if "@dnd-kit/core" in deps or "recharts" in deps:
            return FrontendFramework.REACT_RSBUILD_KIBO
        return FrontendFramework.REACT_RSBUILD
    if "vite" in deps or has_config("vite"):
        scripts = pkg.get("scripts")
        if isinstance(scripts, dict) and "type-check" in scripts:
            return FrontendFramework.REACT_VITE
        return FrontendFramework.REACT_VITE_STARTER
    return None


def settings_module_from_manage(backend: Path) -> str | None:
    match = _SETTINGS_DEFAULT.search(read_text(backend / "manage.py"))
    return match.group(1) if match else None


def api_prefix_from_urls(backend: Path, settings_module: str | None) -> str | None:
    """Return the URL prefix of the API mounted in the root urls.py, if found."""
    packages = ["api", "app", "config", "core"]
    if settings_module:
        packages.insert(0, settings_module.split(".", 1)[0])
    for package in dict.fromkeys(packages):
        match = _API_MOUNT.search(read_text(backend / package / "urls.py"))
        if match:
            return "/" + match.group(1).strip("/") if match.group(1).strip("/") else "/"
    return None
