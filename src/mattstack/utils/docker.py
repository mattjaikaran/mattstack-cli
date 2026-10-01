"""Docker detection and Compose query utilities.

Every helper uses the ordinary Docker CLI and the active Docker context, so
Docker Desktop, OrbStack, Colima, and remote engines behave the same.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_QUERY_TIMEOUT = 20


def docker_available() -> bool:
    return shutil.which("docker") is not None


def docker_compose_available() -> bool:
    """Check if docker compose (v2 plugin) is available."""
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=_QUERY_TIMEOUT,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def docker_running() -> bool:
    """Check if the Docker daemon of the active context answers."""
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            capture_output=True,
            text=True,
            timeout=_QUERY_TIMEOUT,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def docker_unavailable_reason() -> str | None:
    """Explain why Compose commands cannot run, or return None when they can."""
    if not docker_available():
        return "docker is not installed (no `docker` on PATH)"
    if not docker_compose_available():
        return "docker compose v2 is not available (`docker compose version` failed)"
    if not docker_running():
        return "Docker daemon is not running for the current docker context (`docker info` failed)"
    return None


@dataclass(frozen=True)
class ComposeContainer:
    """One container row from `docker compose ps --format json`."""

    service: str
    name: str
    state: str
    health: str

    @property
    def healthy(self) -> bool:
        """Running, and either healthy or without a healthcheck."""
        return self.state == "running" and self.health in ("", "healthy")

    @property
    def summary(self) -> str:
        return f"{self.state} ({self.health})" if self.health else self.state


def parse_compose_ps(output: str) -> list[ComposeContainer]:
    """Parse `docker compose ps --format json` output.

    Compose before v2.21 prints one JSON array; later versions print one
    JSON object per line (NDJSON). Both forms are accepted.
    """
    text = output.strip()
    if not text:
        return []
    rows: list[object]
    if text.startswith("["):
        loaded = json.loads(text)
        rows = loaded if isinstance(loaded, list) else []
    else:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    containers: list[ComposeContainer] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        containers.append(
            ComposeContainer(
                service=str(row.get("Service", "")),
                name=str(row.get("Name", "")),
                state=str(row.get("State", "")).lower(),
                health=str(row.get("Health", "")).lower(),
            )
        )
    return containers


def compose_ps(path: Path) -> tuple[list[ComposeContainer] | None, str]:
    """Return all project containers (running or not) and an error message.

    The container list is None when the query failed; the message then
    explains why.
    """
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--all", "--format", "json"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=_QUERY_TIMEOUT,
        )
    except FileNotFoundError:
        return None, "docker is not installed (no `docker` on PATH)"
    except subprocess.TimeoutExpired:
        return None, "`docker compose ps` timed out; is the Docker daemon responsive?"
    if result.returncode != 0:
        return None, (result.stderr or result.stdout).strip() or "docker compose ps failed"
    try:
        return parse_compose_ps(result.stdout), ""
    except json.JSONDecodeError as exc:
        return None, f"unreadable `docker compose ps` output: {exc}"
