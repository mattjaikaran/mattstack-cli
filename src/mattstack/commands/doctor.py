"""Doctor command: validate development environment."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import typer
from rich.markup import escape

from mattstack.project import EnvFileError, ResolvedProject, compose_services, resolve_project
from mattstack.utils.console import console, create_table, write_raw
from mattstack.utils.docker import docker_available, docker_compose_available, docker_running
from mattstack.utils.process import command_available, get_command_version, port_in_use

INSTALL_HINTS: dict[str, str] = {
    "git": "brew install git",
    "uv": "curl -LsSf https://astral.sh/uv/install.sh | sh",
    "bun": "curl -fsSL https://bun.sh/install | bash",
    "make": "xcode-select --install",
}

STATUS_STYLE = {
    "ok": "[green]OK[/green]",
    "fail": "[red]FAIL[/red]",
    "optional": "[yellow]OPTIONAL[/yellow]",
    "info": "[blue]INFO[/blue]",
}


@dataclass
class DoctorCheck:
    check: str
    status: str  # ok | fail | optional | info
    detail: str


def _first_line(text: str | None) -> str:
    return text.split("\n")[0] if text else ""


def _is_project(project: ResolvedProject) -> bool:
    root = project.root
    return (
        (root / "mattstack.yml").is_file()
        or project.backend_dir.is_dir()
        or (project.frontend_dir.is_dir())
    )


def _tool_checks() -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    checks.append(
        DoctorCheck("Python >= 3.12", "ok" if sys.version_info >= (3, 12) else "fail", py_version)
    )
    for cmd in ("git", "uv", "bun", "make"):
        if command_available(cmd):
            checks.append(DoctorCheck(cmd, "ok", _first_line(get_command_version(cmd))))
        else:
            hint = INSTALL_HINTS.get(cmd, "")
            detail = f"not installed — install: {hint}" if hint else "not installed"
            checks.append(DoctorCheck(cmd, "fail", detail))
    return checks


def _docker_checks(required: bool) -> list[DoctorCheck]:
    """Docker rows; failures count only when the project needs Docker."""
    missing = "fail" if required else "optional"
    installed = docker_available()
    compose = installed and docker_compose_available()
    running = installed and docker_running()
    return [
        DoctorCheck(
            "docker", "ok" if installed else missing, "installed" if installed else "not installed"
        ),
        DoctorCheck(
            "docker compose",
            "ok" if compose else missing,
            "available" if compose else "not available (`docker compose version` failed)",
        ),
        DoctorCheck(
            "Docker daemon",
            "ok" if running else missing,
            "running"
            if running
            else "not running for the current docker context (`docker info` failed)",
        ),
    ]


def _security_checks() -> list[DoctorCheck]:
    pip_audit = command_available("pip-audit")
    npm = command_available("npm")
    return [
        DoctorCheck(
            "pip-audit",
            "ok" if pip_audit else "optional",
            _first_line(get_command_version("pip-audit"))
            if pip_audit
            else "not installed — install: uv tool install pip-audit",
        ),
        DoctorCheck(
            "npm audit",
            "ok" if npm else "optional",
            "bundled with npm/bun" if npm else "npm not installed (optional for vuln scanning)",
        ),
    ]


def _port_checks(
    project: ResolvedProject, is_project: bool, defined: set[str]
) -> list[DoctorCheck]:
    """Informational: a port in use is normal while the project is running."""
    ports: list[tuple[int, str]] = []
    if "db" in defined or not is_project:
        ports.append((project.db_port, "PostgreSQL"))
    if "redis" in defined or not is_project:
        ports.append((project.redis_port, "Redis"))
    if project.backend_dir.is_dir() or not is_project:
        ports.append((project.api_port, "API"))
    if project.frontend_dir.is_dir() or not is_project:
        ports.append((project.frontend_port, "Frontend dev server"))
    return [
        DoctorCheck(
            f"Port {port} ({label})",
            "info",
            "in use (expected while the project is running)" if port_in_use(port) else "free",
        )
        for port, label in ports
    ]


def collect_doctor(path: Path) -> list[DoctorCheck]:
    """Collect tool, Docker, and port checks for the project at *path*."""
    path = path.expanduser().resolve()
    if not path.is_dir():
        return [DoctorCheck("Project directory", "fail", f"Directory not found: {path}")]
    try:
        project = resolve_project(path.resolve())
    except EnvFileError as exc:
        env_check = DoctorCheck("project .env", "fail", str(exc))
        return [*_tool_checks(), *_docker_checks(True), *_security_checks(), env_check]
    is_project = _is_project(project)
    defined = compose_services(project.root)
    docker_required = bool(defined) or not is_project
    return [
        *_tool_checks(),
        *_docker_checks(docker_required),
        *_security_checks(),
        *_port_checks(project, is_project, defined),
    ]


def run_doctor(path: Path | None = None, json_output: bool = False) -> None:
    """Check required tools, Docker, and the project's ports."""
    checks = collect_doctor(path or Path.cwd())
    all_ok = all(c.status != "fail" for c in checks)

    if json_output:
        write_raw(json.dumps({"ok": all_ok, "checks": [asdict(c) for c in checks]}, indent=2))
    else:
        console.print()
        console.print("[bold cyan]mattstack doctor[/bold cyan]")
        console.print()
        table = create_table("Environment Check", ["Check", "Status", "Details"])
        for c in checks:
            table.add_row(c.check, STATUS_STYLE[c.status], escape(c.detail))
        console.print(table)
        console.print()
        if all_ok:
            console.print("[bold green]All checks passed![/bold green]")
        else:
            msg = "Some checks failed. Fix the FAIL rows before using mattstack."
            console.print(f"[bold yellow]{msg}[/bold yellow]")

    if not all_ok:
        raise typer.Exit(code=1)
