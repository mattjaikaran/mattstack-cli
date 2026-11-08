"""Pick free host ports for a generated project's root ``.env``.

The root Compose file publishes the API, frontend, PostgreSQL, and Redis on
``127.0.0.1``. When a host service already owns one of the defaults (Homebrew
PostgreSQL on 5432, for example), Compose cannot bind it, and host-mode
commands reach that service instead of the container.
"""

from __future__ import annotations

import socket
from collections.abc import Mapping
from pathlib import Path

HOST = "127.0.0.1"
SEARCH_LIMIT = 100


def free_port(preferred: int) -> int:
    """Return ``preferred`` when it can bind on loopback, else the next free port."""
    for port in range(preferred, preferred + SEARCH_LIMIT):
        if _bindable(port):
            return port
    return preferred


def free_host_ports(preferred: Mapping[str, int]) -> dict[str, int]:
    """Return one free port per env name, never repeating a chosen port."""
    chosen: dict[str, int] = {}
    for name, port in preferred.items():
        candidate = free_port(port)
        while candidate in chosen.values():
            candidate = free_port(candidate + 1)
        chosen[name] = candidate
    return chosen


def write_env_ports(path: Path, ports: Mapping[str, int]) -> None:
    """Replace the named port values in an env file; keep every other line."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, _ = line.partition("=")
        lines.append(f"{name}={ports[name]}" if separator and name in ports else line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _bindable(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((HOST, port))
        except OSError:
            return False
    return True
