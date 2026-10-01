"""Health command: check only the services this project defines."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
import typer
from rich.markup import escape

from mattstack.project import EnvFileError, ResolvedProject, compose_services, resolve_project
from mattstack.utils.console import console, create_table, print_error, write_raw
from mattstack.utils.docker import compose_ps, docker_unavailable_reason
from mattstack.utils.process import port_in_use

INFRA_SERVICES = ("db", "redis")
APP_SERVICES = ("api-dev", "frontend-dev")
HEALTH_PATHS = ("/api/health/",)
HTTP_TIMEOUT = 5


@dataclass
class Check:
    service: str
    status: str  # "UP" or "DOWN"
    detail: str
    ms: float


def _check_port(port: int) -> tuple[str, str]:
    """Report whether something listens on the port (IPv4 or IPv6 loopback)."""
    if port_in_use(port):
        return "UP", f"Listening on port {port}"
    return "DOWN", f"Nothing listening on port {port}"


def _http_status(url: str) -> tuple[int | None, str]:
    """Return (HTTP status, error). Status is None when no HTTP response came back."""
    try:
        resp = httpx.get(url, timeout=HTTP_TIMEOUT, follow_redirects=True)
    except (httpx.RequestError, httpx.InvalidURL) as exc:
        return None, str(exc) or type(exc).__name__
    return resp.status_code, ""


def _check_backend_live(project: ResolvedProject) -> tuple[str, str]:
    """Prefer the readiness endpoint; fall back to "the server answers HTTP"."""
    base = f"http://localhost:{project.api_port}"
    prefix = project.api_prefix.rstrip("/")
    paths = list(HEALTH_PATHS)
    if prefix and f"{prefix}/health/" not in paths:
        paths.append(f"{prefix}/health/")
    for path in paths:
        status, error = _http_status(base + path)
        if status is None:
            return "DOWN", f"{base}: {error}"
        if status != 404:
            state = "UP" if 200 <= status < 300 else "DOWN"
            return state, f"HTTP {status} {path}"
    status, error = _http_status(f"{base}{prefix}/docs" if prefix else base + "/")
    if status is None:
        return "DOWN", f"{base}: {error}"
    if status >= 500:
        return "DOWN", f"HTTP {status}; no readiness endpoint at {', '.join(paths)}"
    return "UP", f"HTTP {status}; no readiness endpoint at {', '.join(paths)}"


def _check_frontend_live(project: ResolvedProject) -> tuple[str, str]:
    url = f"http://localhost:{project.frontend_port}/"
    status, error = _http_status(url)
    if status is None:
        return "DOWN", f"{url}: {error}"
    return ("UP" if status < 500 else "DOWN"), f"HTTP {status}"


def _expected_containers(project: ResolvedProject, defined: set[str]) -> list[str]:
    """Compose services that must be running in the project's execution mode."""
    expected = [s for s in INFRA_SERVICES if s in defined]
    if project.execution_mode == "container":
        expected += [s for s in APP_SERVICES if s in defined]
    return expected


def _docker_checks(project: ResolvedProject, expected: list[str]) -> list[Check]:
    t0 = time.perf_counter()
    reason = docker_unavailable_reason()
    if reason:
        return [Check("Docker", "DOWN", reason, _ms(t0))]
    containers, error = compose_ps(project.root)
    if containers is None:
        return [Check("Docker", "DOWN", error, _ms(t0))]
    by_service = {c.service: c for c in containers}
    checks: list[Check] = []
    for service in expected:
        container = by_service.get(service)
        if container is None:
            checks.append(Check(f"container {service}", "DOWN", "not created", _ms(t0)))
            continue
        status = "UP" if container.healthy else "DOWN"
        checks.append(Check(f"container {service}", status, container.summary, _ms(t0)))
    return checks


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000


def _timed(service: str, fn: Callable[[], tuple[str, str]]) -> Check:
    t0 = time.perf_counter()
    status, detail = fn()
    return Check(service, status, detail, _ms(t0))


def _has_backend(project: ResolvedProject) -> bool:
    return project.backend_framework is not None or (project.backend_dir / "manage.py").is_file()


def _has_frontend(project: ResolvedProject) -> bool:
    if project.frontend_framework is not None:
        return True
    has_manifest = (project.frontend_dir / "package.json").is_file()
    return has_manifest and project.frontend_dir != project.backend_dir


def collect_health(project: ResolvedProject, live: bool = False) -> list[Check]:
    """Run the checks that apply to this project's services and ports."""
    defined = compose_services(project.root)
    checks: list[Check] = []
    expected = _expected_containers(project, defined)
    if expected:
        checks += _docker_checks(project, expected)
    if "db" in defined:
        checks.append(_timed("PostgreSQL", lambda: _check_port(project.db_port)))
    if "redis" in defined:
        checks.append(_timed("Redis", lambda: _check_port(project.redis_port)))
    if _has_backend(project):
        backend_fn = (
            (lambda: _check_backend_live(project))
            if live
            else (lambda: _check_port(project.api_port))
        )
        checks.append(_timed("Backend", backend_fn))
    if _has_frontend(project):
        frontend_fn = (
            (lambda: _check_frontend_live(project))
            if live
            else (lambda: _check_port(project.frontend_port))
        )
        checks.append(_timed("Frontend", frontend_fn))
    return checks


def run_health(
    path: Path,
    live: bool = False,
    json_output: bool = False,
) -> None:
    """Run health checks on project services; exit 1 when any is down."""
    path = path.resolve()
    if not path.is_dir():
        print_error(f"Directory not found: {path}")
        raise typer.Exit(code=1)
    try:
        project = resolve_project(path)
    except EnvFileError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None

    start = time.perf_counter()
    if not json_output:
        console.print()
        console.print("[bold cyan]mattstack health[/bold cyan]")
        console.print()
    checks = collect_health(project, live=live)
    elapsed = time.perf_counter() - start
    healthy = bool(checks) and all(c.status == "UP" for c in checks)

    if json_output:
        payload = {
            "project": str(project.root),
            "mode": project.execution_mode,
            "healthy": healthy,
            "checks": [asdict(c) | {"ms": round(c.ms)} for c in checks],
        }
        write_raw(json.dumps(payload, indent=2))
    elif not checks:
        print_error(f"No project services found in {project.root}")
    else:
        table = create_table("Health Check", ["Service", "Status", "Details", "Time"])
        for c in checks:
            color = "green" if c.status == "UP" else "red"
            status_fmt = f"[{color}]{c.status}[/{color}]"
            table.add_row(c.service, status_fmt, escape(c.detail), f"{c.ms:.0f}ms")
        console.print(table)
        up_count = sum(1 for c in checks if c.status == "UP")
        console.print()
        console.print(f"[bold]{up_count}/{len(checks)} services healthy[/bold]")
        console.print(f"[dim]({elapsed:.1f}s)[/dim]")

    if not healthy:
        raise typer.Exit(code=1)
