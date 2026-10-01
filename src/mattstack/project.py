"""Resolve an existing mattstack project: root, components, env, and stack metadata.

Persisted ``project:`` metadata in mattstack.yml wins over filesystem detection.
Detection is conservative: an unrecognised framework is ``None``, never a guess.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mattstack.config import (
    BackendFramework,
    DeploymentTarget,
    FrontendFramework,
    ProjectConfig,
    ProjectType,
    Variant,
    normalize_name,
)
from mattstack.config_file import load_project_section, write_project_section
from mattstack.runtime_profiles import apply_runtime_metadata, runtime_kwargs
from mattstack.stack_detection import (
    PYTHON_MANIFESTS,
    api_prefix_from_urls,
    detect_backend_framework,
    detect_frontend_framework,
    has_backend_manifest,
    python_manifest_text,
    read_text,
    settings_module_from_manage,
)
from mattstack.utils.console import print_warning

CONFIG_FILENAME = "mattstack.yml"
COMPOSE_FILENAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
EXECUTION_MODES = ("host", "container")
DEFAULT_API_PREFIX = "/api"

_ENV_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
_VAR_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^${}]*))?\}")


@dataclass(frozen=True)
class ResolvedProject:
    """Effective view of a project. ``env`` holds secrets: never print it."""

    root: Path
    backend_dir: Path
    frontend_dir: Path
    env: dict[str, str] = field(repr=False)
    backend_framework: BackendFramework | None
    frontend_framework: FrontendFramework | None
    config: ProjectConfig
    api_port: int
    frontend_port: int
    db_port: int
    redis_port: int
    api_prefix: str
    settings_module: str | None
    execution_mode: str


def _is_component_root(path: Path) -> bool:
    backend = path / "backend"
    return (
        (path / CONFIG_FILENAME).is_file()
        or (backend / "manage.py").is_file()
        or any((backend / name).is_file() for name in (*PYTHON_MANIFESTS, "package.json"))
        or (path / "frontend" / "package.json").is_file()
    )


def _has_manifest(path: Path) -> bool:
    names = ("manage.py", *PYTHON_MANIFESTS, "package.json")
    return any((path / name).is_file() for name in names)


def find_project_root(path: Path) -> Path:
    """Return the project root for ``path`` or the nearest ancestor that is one.

    A directory holding mattstack.yml or backend/frontend components wins over a
    root-only manifest, so ``backend/`` or ``frontend/src`` resolve to the
    monorepo root. The walk stops at the enclosing git repository root. When
    nothing matches, the resolved ``path`` itself is returned.
    """
    start = path.expanduser().resolve()
    if start.is_file():
        start = start.parent
    chain: list[Path] = []
    for candidate in (start, *start.parents):
        chain.append(candidate)
        if (candidate / ".git").exists():
            break
    for check in (_is_component_root, _has_manifest):
        for candidate in chain:
            if check(candidate):
                return candidate
    return start


class EnvFileError(ValueError):
    """The root .env or mattstack.yml project metadata is malformed or unresolvable."""


def _unquote(raw: str) -> tuple[str, bool]:
    """Return the value and whether it may be expanded (not single-quoted)."""
    value = raw.strip()
    if value[:1] in ("'", '"'):
        quote = value[0]
        end = value.find(quote, 1)
        while quote == '"' and end > 0 and value[end - 1] == "\\":
            end = value.find(quote, end + 1)
        if end > 0:
            inner = value[1:end]
            if quote == '"':
                inner = inner.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
            return inner, quote == '"'
        return value, True
    return re.split(r"\s+#", value, maxsplit=1)[0].strip(), True


def _parse_entries(path: Path) -> list[tuple[str, str, bool]]:
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print_warning(f"Cannot read {path}: {e}")
        return []
    entries: list[tuple[str, str, bool]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ENV_LINE.match(stripped)
        if match:
            entries.append((match.group(1), *_unquote(match.group(2))))
    return entries


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a dotenv file into raw values, without executing or expanding anything.

    Supports ``export KEY=value``, whitespace around ``=``, single or double
    quotes, and trailing `` # comments`` on unquoted values. A missing file
    yields {}; an unreadable one warns and yields {}.
    """
    return {key: value for key, value, _ in _parse_entries(path)}


def _expand(key: str, value: str, lookup: dict[str, str]) -> str:
    """Expand ``${VAR}`` and ``${VAR:-default}``; raise on anything unresolved."""

    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        current = lookup.get(name)
        if current:
            return current
        if default is not None:
            return default
        if current is None:
            raise EnvFileError(
                f".env: {key} references ${{{name}}}, which is not exported "
                "and not defined on an earlier line"
            )
        return current

    expanded = _VAR_REF.sub(replace, value)
    if "${" in _VAR_REF.sub("", value):
        raise EnvFileError(
            f".env: {key} has a malformed reference; only ${{VAR}} and ${{VAR:-default}} work"
        )
    return expanded


def project_environment(root: Path) -> dict[str, str]:
    """Return root .env values overlaid by the current process environment.

    Unquoted and double-quoted values expand ``${VAR}`` and ``${VAR:-default}``
    against the process environment first, then keys from earlier lines.
    Nothing is executed, single-quoted values stay literal, and a malformed,
    forward, self-referencing, or undefined reference raises ``EnvFileError``.
    """
    parsed: dict[str, str] = {}
    for key, value, expandable in _parse_entries(root / ".env"):
        parsed[key] = _expand(key, value, {**parsed, **os.environ}) if expandable else value
    return {**parsed, **os.environ}


def compose_services(root: Path) -> set[str]:
    """Return service names from the root compose file; empty when absent or invalid."""
    for name in COMPOSE_FILENAMES:
        path = root / name
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(read_text(path))
        except yaml.YAMLError:
            return set()
        services = data.get("services") if isinstance(data, dict) else None
        return {str(key) for key in services} if isinstance(services, dict) else set()
    return set()


def _enum(enum_type: Any, value: Any) -> Any:
    try:
        return enum_type(value) if value is not None else None
    except ValueError:
        return None


def _port(*values: Any) -> int | None:
    for value in values:
        try:
            port = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if 0 < port < 65536:
            return port
    return None


def _component_dir(root: Path, section: dict[str, Any], default: Path) -> Path:
    raw = section.get("dir")
    if isinstance(raw, str) and raw:
        candidate = (root / raw).resolve()
        if candidate == root or root in candidate.parents:
            return candidate
    return default


def _bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _section(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    """Return a copy of ``mapping[key]`` when it is a mapping, else {}."""
    value = mapping.get(key)
    return dict(value) if isinstance(value, dict) else {}


def resolve_project(path: Path) -> ResolvedProject:
    """Resolve root, components, frameworks, env, and ports for ``path``.

    Raises ``EnvFileError`` when the root .env has an unresolvable reference.
    """
    root = find_project_root(path)
    meta = load_project_section(root / CONFIG_FILENAME)
    backend_meta = _section(meta, "backend")
    frontend_meta = _section(meta, "frontend")
    ports_meta = _section(meta, "ports")

    default_backend = root / "backend"
    if not default_backend.is_dir() and has_backend_manifest(root):
        default_backend = root
    backend_dir = _component_dir(root, backend_meta, default_backend)
    default_frontend = root / "frontend"
    if not (default_frontend / "package.json").is_file() and detect_frontend_framework(root):
        default_frontend = root
    frontend_dir = _component_dir(root, frontend_meta, default_frontend)

    has_backend = has_backend_manifest(backend_dir)
    has_frontend = (frontend_dir / "package.json").is_file() and (
        frontend_dir != backend_dir or detect_frontend_framework(frontend_dir) is not None
    )
    backend_fw = _enum(BackendFramework, backend_meta.get("framework")) or (
        detect_backend_framework(backend_dir) if has_backend else None
    )
    frontend_fw = _enum(FrontendFramework, frontend_meta.get("framework")) or (
        detect_frontend_framework(frontend_dir) if has_frontend else None
    )

    project_type = _enum(ProjectType, meta.get("type"))
    if project_type is None:
        if has_backend and has_frontend:
            project_type = ProjectType.FULLSTACK
        elif has_frontend:
            project_type = ProjectType.FRONTEND_ONLY
        else:
            project_type = ProjectType.BACKEND_ONLY

    services = compose_services(root)
    manifest = python_manifest_text(backend_dir) if has_backend else ""
    ios_dir = root / "ios"
    detected_ios = ios_dir.is_dir() and any(ios_dir.glob("*.xcodeproj"))
    raw_name = meta.get("name")
    name = raw_name if isinstance(raw_name, str) else ""

    env = project_environment(root)
    default_api = 4000 if backend_fw == BackendFramework.NESTJS else 8000
    persisted_settings = backend_meta.get("settings_module")
    settings_module = (
        env.get("DJANGO_SETTINGS_MODULE")
        or (persisted_settings if isinstance(persisted_settings, str) else None)
        or (settings_module_from_manage(backend_dir) if has_backend else None)
    )
    prefix = backend_meta.get("api_prefix")
    if not (isinstance(prefix, str) and prefix):
        prefix = (
            api_prefix_from_urls(backend_dir, settings_module) if has_backend else None
        ) or DEFAULT_API_PREFIX
    mode = meta.get("execution_mode")
    try:
        config = ProjectConfig(
            name=normalize_name(name) or normalize_name(root.name) or "project",
            path=root,
            project_type=project_type,
            variant=_enum(Variant, meta.get("variant")) or Variant.STARTER,
            frontend_framework=frontend_fw or FrontendFramework.REACT_VITE,
            backend_framework=backend_fw or BackendFramework.DJANGO_NINJA,
            include_ios=_bool(meta.get("ios"), detected_ios),
            deployment=_enum(DeploymentTarget, meta.get("deployment")) or DeploymentTarget.DOCKER,
            init_git=False,
            api_prefix=prefix,
            **runtime_kwargs(backend_meta, backend_fw, env, manifest, services),
        )
    except ValueError as error:
        raise EnvFileError(f"{error}. Fix mattstack.yml or .env, then rerun") from None
    return ResolvedProject(
        root=root,
        backend_dir=backend_dir,
        frontend_dir=frontend_dir,
        env=env,
        backend_framework=backend_fw,
        frontend_framework=frontend_fw,
        config=config,
        api_port=_port(env.get("API_PORT"), ports_meta.get("api")) or default_api,
        frontend_port=_port(env.get("FRONTEND_PORT"), ports_meta.get("frontend")) or 3000,
        db_port=_port(env.get("DB_PORT"), ports_meta.get("db")) or 5432,
        redis_port=_port(env.get("REDIS_PORT"), ports_meta.get("redis")) or 6379,
        api_prefix=prefix,
        settings_module=str(settings_module) if settings_module else None,
        execution_mode=mode if mode in EXECUTION_MODES else "host",
    )


def save_project_config(config: ProjectConfig) -> None:
    """Persist non-secret stack metadata under ``project:`` in mattstack.yml.

    Scaffold choices, including ``config.api_prefix``, overwrite older values;
    user-tunable values (ports, settings module, execution mode) keep any
    existing setting. All other mattstack.yml keys and comments are retained.
    Raises ``ValueError`` rather than overwrite an unreadable or invalid file.
    """
    path = config.path / CONFIG_FILENAME
    existing = load_project_section(path)

    section: dict[str, Any] = dict(existing)
    section.update(
        {
            "name": config.name,
            "type": config.project_type.value,
            "variant": config.variant.value,
            "ios": config.include_ios,
            "deployment": config.deployment.value,
        }
    )
    section.setdefault("execution_mode", "host")

    if config.has_backend:
        backend = _section(existing, "backend")
        backend.update(
            {
                "framework": config.backend_framework.value,
                "dir": "backend",
                "redis": config.use_redis,
                "api_prefix": config.api_prefix,
            }
        )
        apply_runtime_metadata(backend, config)
        if config.is_django_backend:
            backend.setdefault("settings_module", f"{config.wsgi_app}.settings")
        section["backend"] = backend
    else:
        section.pop("backend", None)

    if config.has_frontend:
        frontend = _section(existing, "frontend")
        frontend.update({"framework": config.frontend_framework.value, "dir": "frontend"})
        section["frontend"] = frontend
    else:
        section.pop("frontend", None)

    ports = _section(existing, "ports")
    defaults = {"frontend": 3000, "db": 5432, "redis": 6379}
    if config.has_backend:
        defaults["api"] = config.backend_api_port
    for key, value in defaults.items():
        ports.setdefault(key, value)
    section["ports"] = ports

    write_project_section(path, section)
