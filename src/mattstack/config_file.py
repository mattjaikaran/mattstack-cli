"""mattstack.yml control-plane configuration and persisted stack metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from mattstack.utils.console import print_error


@dataclass
class DepsConfig:
    """Dependency management settings."""

    mode: str = "approval"  # approval | allow | deny
    manifest: str = "DEPENDENCIES.md"


@dataclass
class ScopeConfig:
    """Scope enforcement settings."""

    enforce: bool = True


@dataclass
class BoardConfig:
    """Task board integration settings."""

    backend: str = "none"
    url: str = ""
    api_key_env: str = "AXIS_API_KEY"
    project_slug: str = "default"


@dataclass
class NotifyConfig:
    """Notification integration settings."""

    backend: str = "none"
    webhook_url_env: str = "DEPLOY_WEBHOOK_URL"
    chat_id_env: str = "TELEGRAM_CHAT_ID"


@dataclass
class MattstackConfig:
    """Control-plane configuration loaded from mattstack.yml."""

    version: int = 1
    strict: bool = True
    protect_main: bool = False
    required_reviews: int = 1
    coverage_floor: int = 80
    file_length: int = 400
    deps: DepsConfig = field(default_factory=DepsConfig)
    scope: ScopeConfig = field(default_factory=ScopeConfig)
    board: BoardConfig = field(default_factory=BoardConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)


def _read_yaml(path: Path) -> Any:
    """Read and parse ``path``; raise ``ValueError`` when unreadable or invalid."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"Cannot read {path}: {e}") from e
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e


def load_config(path: Path) -> MattstackConfig:
    """Load mattstack.yml, tolerating missing, partial, or invalid files.

    Any absent key (or an unreadable/invalid file) falls back to its default,
    so callers always receive a fully-populated :class:`MattstackConfig`.
    """
    if not path.exists():
        return MattstackConfig()

    try:
        data: Any = _read_yaml(path)
    except ValueError as e:
        print_error(str(e))
        return MattstackConfig()

    if not isinstance(data, dict):
        return MattstackConfig()

    return _from_dict(data)


def load_project_section(path: Path) -> dict[str, Any]:
    """Return the ``project:`` stack metadata from mattstack.yml, or {}.

    Missing, unreadable, or invalid files yield {} so detection can fall back
    to the filesystem.
    """
    if not path.is_file():
        return {}
    try:
        data = _read_yaml(path)
    except ValueError as e:
        print_error(str(e))
        return {}
    if not isinstance(data, dict):
        return {}
    return dict(_as_dict(data.get("project")))


def write_project_section(path: Path, section: dict[str, Any]) -> None:
    """Replace the top-level ``project:`` block in mattstack.yml with ``section``.

    Every other key, comment, and line is kept byte-for-byte. Raises
    ``ValueError`` instead of overwriting a file that is unreadable, invalid,
    or not a mapping.
    """
    lines: list[str] = []
    if path.exists():
        data = _read_yaml(path)
        if data is not None and not isinstance(data, dict):
            raise ValueError(f"{path} must contain a YAML mapping")
        lines = _without_top_level_key(path.read_text(encoding="utf-8").splitlines(), "project")
    while lines and not lines[-1].strip():
        lines.pop()
    block = yaml.safe_dump({"project": section}, sort_keys=False, default_flow_style=False)
    prefix = "\n".join(lines) + "\n\n" if lines else ""
    path.write_text(prefix + block, encoding="utf-8")


def _without_top_level_key(lines: list[str], key: str) -> list[str]:
    """Drop the block that starts at top-level ``key:`` up to the next top-level line.

    A column-0 comment also ends the block, because it introduces the next key.
    """
    kept: list[str] = []
    skipping = False
    for line in lines:
        if line and not line[0].isspace():
            skipping = not line.startswith("#") and line.split(":", 1)[0].strip() == key
        if not skipping:
            kept.append(line)
    return kept


def _from_dict(data: Any) -> MattstackConfig:
    deps = _as_dict(data.get("deps"))
    scope = _as_dict(data.get("scope"))
    board = _as_dict(data.get("board"))
    notify = _as_dict(data.get("notify"))

    return MattstackConfig(
        version=data.get("version", 1),
        strict=data.get("strict", True),
        protect_main=data.get("protect_main", False),
        required_reviews=data.get("required_reviews", 1),
        coverage_floor=data.get("coverage_floor", 80),
        file_length=data.get("file_length", 400),
        deps=DepsConfig(
            mode=deps.get("mode", "approval"),
            manifest=deps.get("manifest", "DEPENDENCIES.md"),
        ),
        scope=ScopeConfig(enforce=scope.get("enforce", True)),
        board=BoardConfig(
            backend=board.get("backend", "none"),
            url=board.get("url", ""),
            api_key_env=board.get("api_key_env", "AXIS_API_KEY"),
            project_slug=board.get("project_slug", "default"),
        ),
        notify=NotifyConfig(
            backend=notify.get("backend", "none"),
            webhook_url_env=notify.get("webhook_url_env", "DEPLOY_WEBHOOK_URL"),
            chat_id_env=notify.get("chat_id_env", "TELEGRAM_CHAT_ID"),
        ),
    )


def _as_dict(value: Any) -> Any:
    """Return ``value`` as a mapping, falling back to {} for non-mappings."""
    return value if isinstance(value, dict) else {}
