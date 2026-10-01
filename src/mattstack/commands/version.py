"""Version command with update check."""

from __future__ import annotations

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
