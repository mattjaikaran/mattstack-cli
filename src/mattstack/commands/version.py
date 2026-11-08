"""Version command with update check."""

from __future__ import annotations

import importlib.metadata
import json

import httpx

from mattstack import __version__
from mattstack.utils.console import console, is_quiet


def check_pypi_version(package: str = "mattstack") -> str | None:
    """Check PyPI for the latest version. Returns None on any failure."""
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        resp = httpx.get(
            url, headers={"Accept": "application/json"}, timeout=3, follow_redirects=True
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        return None
    return str(data.get("info", {}).get("version"))


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a version string like '0.1.0' into a tuple of ints."""
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts)


def installed_commit() -> str | None:
    """Return the short commit for a VCS install, or None for a PyPI or editable install."""
    try:
        distribution = importlib.metadata.distribution("mattstack")
    except importlib.metadata.PackageNotFoundError:
        return None
    try:
        raw = distribution.read_text("direct_url.json")
    except (OSError, UnicodeDecodeError):
        return None
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    vcs_info = data.get("vcs_info")
    if not isinstance(vcs_info, dict):
        return None
    commit_id = vcs_info.get("commit_id")
    if not isinstance(commit_id, str) or not commit_id:
        return None
    return commit_id[:7]


def version_line() -> str:
    """Return the one-line version, with the commit when installed from a VCS URL."""
    commit = installed_commit()
    return f"mattstack {__version__}" + (f" (commit {commit})" if commit else "")


def run_version() -> None:
    """Show version with optional update check."""
    console.print(f"mattstack [bold]{__version__}[/bold]")
    if is_quiet():
        return

    latest = check_pypi_version()
    if latest and latest != __version__:
        current = _parse_version(__version__)
        remote = _parse_version(latest)
        if remote > current:
            console.print()
            console.print(
                f"[yellow]Update available:[/yellow] "
                f"{__version__} → [bold green]{latest}[/bold green]"
            )
            console.print("[dim]Run: uv tool upgrade mattstack[/dim]")

    console.print("[dim]Tip: mattstack completions --install for shell completions[/dim]")
