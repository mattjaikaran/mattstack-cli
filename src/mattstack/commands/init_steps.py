"""The next-steps summary ``mattstack init`` prints after generating a project."""

from __future__ import annotations

from pathlib import Path

from mattstack.config import BackendFramework, ProjectConfig
from mattstack.project import parse_env_file
from mattstack.runtime_profiles import task_summary
from mattstack.templates.frontend_runtime import FRONTEND_PORT
from mattstack.utils.console import console, print_success


def _env_ports(root: Path) -> dict[str, int]:
    """Return valid integer values from the generated root ``.env``, by env name."""
    ports: dict[str, int] = {}
    for name, raw in parse_env_file(root / ".env").items():
        try:
            port = int(raw.strip())
        except ValueError:
            continue
        if 0 < port < 65536:
            ports[name] = port
    return ports


def print_next_steps(config: ProjectConfig) -> None:
    """Print the commands and the host ports the generated project uses."""
    console.print()
    print_success(f"Project '{config.name}' created successfully!")
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  [cyan]cd {config.name}[/cyan]")
    console.print("  [cyan]just setup[/cyan]")
    if config.has_backend:
        infrastructure = "db redis" if config.use_redis else "db"
        console.print(f"  [cyan]docker compose up -d --wait {infrastructure}[/cyan]")
        console.print("  [cyan]just backend-migrate[/cyan]")
        if config.backend_framework in {
            BackendFramework.DJANGO_NINJA,
            BackendFramework.DJANGO_MATT,
        }:
            console.print("  [cyan]just superuser-host[/cyan]")
        if config.task_backend.value != "none":
            console.print(f"  [cyan]just backend-worker[/cyan]  # {task_summary(config)}")
        if config.use_realtime:
            console.print("  [cyan]just up-realtime[/cyan]  # Centrifugo; see CLAUDE.md")
    console.print("  [cyan]mattstack dev --mode host[/cyan]")
    ports = _env_ports(config.path)
    if config.has_backend:
        api_port = ports.get("API_PORT", config.backend_api_port)
        console.print(f"  API: http://localhost:{api_port}{config.api_prefix}")
    if config.has_frontend:
        frontend_port = ports.get("FRONTEND_PORT", FRONTEND_PORT)
        console.print(f"  Frontend: http://localhost:{frontend_port}")
    console.print()
