"""Read tool and service versions from a project's own lockfiles and images.

Generated files must not hardcode versions that the cloned components already
pin. Each reader returns only versions it finds; a missing key means "not
recorded", never a guessed default. Sources are checked backend first, then
frontend, then the project root, so templates follow the components.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable
from pathlib import Path

_Add = Callable[[str, Path, str | None], None]
PYTHON_PACKAGES = ("ruff", "mypy", "django")
JS_PACKAGES = ("react", "tailwindcss", "zod", "typescript")
# Pins when neither a component nor the generated root records a version.
# They match django-ninja-boilerplate's Dockerfile (uv) and a released Bun.
UV_FALLBACK = "0.12.1"
BUN_FALLBACK = "1.3.14"
# Sources that record a range (``>=3.13``) carry this suffix; see ``is_floor``.
FLOOR_SUFFIX = "#range"
# Image repository -> version key. pgvector tags look like ``pg17``.
_IMAGE_KEYS = {
    "postgres": "postgres",
    "pgvector/pgvector": "postgres",
    "postgis/postgis": "postgres",
    "valkey/valkey": "valkey",
    "redis": "redis",
    "oven/bun": "bun",
    "node": "node",
    "python": "python",
    "ghcr.io/astral-sh/uv": "uv",
}
_IMAGE_RE = re.compile(
    r"(?:image:|FROM|--from=)\s*(?:\$\{[A-Z_]+:-)?([a-z0-9./_-]+):([A-Za-z0-9._-]+)"
)
_VERSION_RE = re.compile(r"\d+(?:\.\d+)*")
_ARG_RE = re.compile(r"^ARG (PYTHON|UV|BUN|NODE)_VERSION=(\d+(?:\.\d+)*)", re.M)
_COMPOSE_GLOBS = ("docker-compose*.yml", "compose*.yml")
_DOCKERFILE_GLOBS = ("Dockerfile*", "docker/*/Dockerfile*")


def read_versions(project_root: Path) -> dict[str, str]:
    """Return one version per key, preferring backend, then frontend, then root."""
    return {key: next(iter(found.values())) for key, found in version_sources(project_root).items()}


def version_sources(project_root: Path) -> dict[str, dict[str, str]]:
    """Return ``{key: {relative source: version}}`` for every recorded version."""
    found: dict[str, dict[str, str]] = {}

    def add(key: str, source: Path, version: str | None) -> None:
        if version:
            relative = source.relative_to(project_root).as_posix()
            found.setdefault(key, {}).setdefault(relative, version)

    for component in (project_root / "backend", project_root / "frontend", project_root):
        if not component.is_dir():
            continue
        _python_sources(component, add)
        _js_sources(component, add)
        for pattern in (*_COMPOSE_GLOBS, *_DOCKERFILE_GLOBS):
            for path in sorted(component.glob(pattern)):
                for key, version in _image_versions(_read(path)):
                    add(key, path, version)
    return found


def image_tag(project_root: Path, repository: str) -> str | None:
    """Return the first tag that a component's Compose file uses for ``repository``."""
    for component in (project_root / "backend", project_root):
        for pattern in _COMPOSE_GLOBS:
            for path in sorted(component.glob(pattern)):
                for repo, tag in _IMAGE_RE.findall(_read(path)):
                    if repo == repository:
                        return str(tag)
    return None


def major(version: str | None) -> str | None:
    """Return the leading numeric part of ``version`` (``"17"`` for ``"17.2"``)."""
    match = _VERSION_RE.search(version or "")
    return match.group(0).split(".")[0] if match else None


def snapshot_pins(project_root: Path) -> dict[str, str]:
    """Return versions plus ``image:<repository>`` tags, before consolidation runs."""
    pins = read_versions(project_root)
    for component in (project_root / "backend", project_root):
        for pattern in _COMPOSE_GLOBS:
            for path in sorted(component.glob(pattern)):
                for repo, tag in _IMAGE_RE.findall(_read(path)):
                    pins.setdefault(f"image:{repo}", str(tag))
    return pins


def bun_pin(component: Path) -> str | None:
    """Return the exact Bun version in ``packageManager`` (``bun@1.2.3``), if any."""
    try:
        data = json.loads(_read(component / "package.json") or "{}")
    except ValueError:
        return None
    manager = str(data.get("packageManager", "")) if isinstance(data, dict) else ""
    match = re.fullmatch(r"bun@(\d+\.\d+\.\d+)", manager.split("+", 1)[0])
    return match.group(1) if match else None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _python_sources(component: Path, add: _Add) -> None:
    pin = component / ".python-version"
    add("python", pin, _bare(_read(pin).strip()))
    pyproject = component / "pyproject.toml"
    try:
        project = tomllib.loads(_read(pyproject)).get("project", {})
    except tomllib.TOMLDecodeError:
        project = {}
    _add_spec(add, "python", pyproject, str(project.get("requires-python", "")))
    lock = component / "uv.lock"
    try:
        packages = tomllib.loads(_read(lock)).get("package", [])
    except tomllib.TOMLDecodeError:
        packages = []
    for package in packages:
        if isinstance(package, dict) and package.get("name") in PYTHON_PACKAGES:
            add(str(package["name"]), lock, str(package.get("version", "")))


def _js_sources(component: Path, add: _Add) -> None:
    manifest = component / "package.json"
    try:
        data = json.loads(_read(manifest) or "{}")
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        return
    lock = component / "bun.lock"
    locked = _read(lock)
    for name in JS_PACKAGES:
        match = re.search(rf'^\s*"{re.escape(name)}": \["{re.escape(name)}@([^"]+)"', locked, re.M)
        add(name, lock, match.group(1) if match else None)
        for section in ("dependencies", "devDependencies"):
            deps = data.get(section)
            if isinstance(deps, dict):
                _add_spec(add, name, manifest, str(deps.get(name, "")))
    manager = str(data.get("packageManager", ""))
    if manager.startswith("bun@"):
        add("bun", manifest, _bare(manager.removeprefix("bun@")))
    engines = data.get("engines")
    if isinstance(engines, dict):
        _add_spec(add, "node", manifest, str(engines.get("node", "")))
        _add_spec(add, "bun", manifest, str(engines.get("bun", "")))
    for name in (".nvmrc", ".node-version"):
        add("node", component / name, _bare(_read(component / name).strip()))


def _add_spec(add: _Add, key: str, path: Path, spec: str) -> None:
    """Record an exact pin under ``path``; a range under ``path#range`` (``is_floor``)."""
    exact = re.fullmatch(r"=*\s*v?\d+(?:\.\d+)*", spec.strip())
    add(key, path if exact else path.with_name(f"{path.name}{FLOOR_SUFFIX}"), _bare(spec))


def is_floor(source: str) -> bool:
    """Return whether ``source`` records a range floor (``>=3.13``, ``^19.1``), not a pin."""
    return source.endswith(FLOOR_SUFFIX)


def _image_versions(text: str) -> list[tuple[str, str]]:
    versions = []
    for repo, tag in _IMAGE_RE.findall(text):
        key = _IMAGE_KEYS.get(repo)
        version = _bare(tag)
        if key and version:
            versions.append((key, version))
    for name, version in _ARG_RE.findall(text):
        versions.append((name.lower(), version))
    return versions


def _bare(spec: str) -> str | None:
    """Return the version in a pin, range floor, or image tag (``>=3.13`` -> ``3.13``)."""
    match = _VERSION_RE.search(spec)
    return match.group(0) if match else None
