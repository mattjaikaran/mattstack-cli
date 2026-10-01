"""Dev command: start the project's dev stack in host or container mode.

Host mode (default) starts only the Compose infrastructure (db, redis),
waits for it to be healthy, then runs the backend and frontend dev servers
on the host under supervision. Container mode starts the Compose app
services (api-dev, frontend-dev), follows their logs, and stops them on
Ctrl+C or when one of them stops; it runs nothing on the host. Each
configured port therefore gets exactly one listener.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 # Required CLI subprocess support.
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import typer

from mattstack.config import BackendFramework, FrontendFramework
from mattstack.project import EnvFileError, ResolvedProject, compose_services, resolve_project
from mattstack.utils.console import (
    console,
    create_table,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from mattstack.utils.docker import compose_ps, docker_available, docker_unavailable_reason
from mattstack.utils.package_manager import PackageManager, build_run_cmd, resolve_package_manager
from mattstack.utils.process import (
    ManagedProcess,
    ProcessTerminationError,
    Supervisor,
    port_in_use,
    shutdown_shield,
    termination_signals,
)

MODES = ("host", "container")
INFRA_SERVICES = ("db", "redis")
APP_SERVICES = {"backend": "api-dev", "frontend": "frontend-dev"}
DJANGO_FRAMEWORKS = (BackendFramework.DJANGO_NINJA, BackendFramework.DJANGO_MATT)
VITE_FRAMEWORKS = (FrontendFramework.REACT_VITE, FrontendFramework.REACT_VITE_STARTER)
READY_TIMEOUT = 180.0
COMPOSE_UP_TIMEOUT = 900
COMPOSE_STOP_TIMEOUT = 120
CONTAINER_POLL_INTERVAL = 2.0


@dataclass
class HostApp:
    """A dev server to run on the host."""

    name: str
    cmd: list[str]
    cwd: Path
    port: int
    env: dict[str, str]


def _parse_services(services_str: str | None) -> set[str]:
    """Parse --services option into a set of service names."""
    if not services_str:
        return {"docker", "backend", "frontend"}
    return {s.strip().lower() for s in services_str.split(",") if s.strip()}


def _scripts(package_json: Path) -> dict[str, str]:
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
    return scripts if isinstance(scripts, dict) else {}


def _backend_app(project: ResolvedProject) -> HostApp | None:
    """Build the host backend command for the detected framework."""
    backend, port, framework = project.backend_dir, project.api_port, project.backend_framework
    env = dict(project.env)
    env.setdefault("PYTHONUNBUFFERED", "1")
    cmd: list[str]
    if framework in DJANGO_FRAMEWORKS or (framework is None and (backend / "manage.py").is_file()):
        if not (backend / "manage.py").is_file():
            return None
        if project.settings_module:
            env.setdefault("DJANGO_SETTINGS_MODULE", project.settings_module)
        cmd = ["uv", "run", "python", "manage.py", "runserver", f"127.0.0.1:{port}"]
    elif framework == BackendFramework.FASTAPI:
        if not (backend / "app" / "main.py").is_file():
            return None
        cmd = ["uv", "run", "uvicorn", "app.main:app", "--reload"]
        cmd += ["--host", "127.0.0.1", "--port", str(port)]
    elif framework == BackendFramework.NESTJS:
        if "start:dev" not in _scripts(backend / "package.json"):
            return None
        env["PORT"] = str(port)
        cmd = build_run_cmd(resolve_package_manager(backend), "start:dev").full
    else:
        return None
    return HostApp("backend", cmd, backend, port, env)


def _frontend_app(project: ResolvedProject) -> HostApp | None:
    """Build the host frontend command, pinned to the configured port."""
    frontend, port = project.frontend_dir, project.frontend_port
    if project.frontend_framework is None and frontend == project.backend_dir:
        return None  # the backend's own package.json, not a frontend
    dev_script = _scripts(frontend / "package.json").get("dev")
    if not isinstance(dev_script, str):
        return None
    pm = resolve_package_manager(frontend)
    extra: list[str] = []
    has_port_flag = "--port" in dev_script or " -p " in f" {dev_script} "
    if project.frontend_framework is not None and not has_port_flag:
        extra = ["--port", str(port)]
        if project.frontend_framework in VITE_FRAMEWORKS:
            extra.append("--strictPort")  # never silently move to the next port
        if pm == PackageManager.NPM:
            extra = ["--", *extra]
    env = {**project.env, "PORT": str(port)}
    return HostApp("frontend", build_run_cmd(pm, "dev", extra).full, frontend, port, env)


def _service_ports(project: ResolvedProject) -> dict[str, int]:
    return {
        "db": project.db_port,
        "redis": project.redis_port,
        "api-dev": project.api_port,
        "frontend-dev": project.frontend_port,
    }


def _running_compose_services(path: Path, defined: set[str]) -> set[str]:
    """Running services of this project; empty when Compose is absent or unreachable."""
    if not defined or not docker_available():
        return set()
    containers, _ = compose_ps(path)
    return {c.service for c in containers or [] if c.state == "running"}


def _require_docker() -> None:
    reason = docker_unavailable_reason()
    if reason:
        print_error(f"Cannot start Docker services: {reason}")
        print_info("Start Docker (or your docker context's engine), or run with --no-docker.")
        raise typer.Exit(code=1)


def _compose_up(path: Path, services: list[str]) -> None:
    """Start *services* detached and wait until they are running/healthy."""
    print_info(f"Starting Docker services: {', '.join(services)} (waiting for health)...")
    cmd = ["docker", "compose", "up", "-d", "--wait", *services]
    try:
        result = subprocess.run(cmd, cwd=path, timeout=COMPOSE_UP_TIMEOUT)  # nosec B603 # Argv; trust project tools and PATH.
    except subprocess.TimeoutExpired:
        print_error(f"`{' '.join(cmd)}` did not finish within {COMPOSE_UP_TIMEOUT}s")
        raise typer.Exit(code=1) from None
    if result.returncode != 0:
        print_error(f"`{' '.join(cmd)}` failed (exit {result.returncode}). Recent logs:")
        subprocess.run(["docker", "compose", "logs", "--tail", "40", *services], cwd=path)  # nosec B603, B607 # Argv; trust project tools and PATH.
        raise typer.Exit(code=1)
    print_success(f"Docker services ready: {', '.join(services)}")


def _conflicts(
    project: ResolvedProject, defined: set[str], compose_targets: list[str], apps: list[HostApp]
) -> list[str]:
    """Describe ports that would get a second listener if we started now."""
    ports = _service_ports(project)
    busy_compose = [s for s in compose_targets if s in ports and port_in_use(ports[s])]
    busy_apps = [app for app in apps if port_in_use(app.port)]
    if not busy_compose and not busy_apps:
        return []
    running = _running_compose_services(project.root, defined)
    messages = [
        f"Port {ports[svc]} for Compose service '{svc}' is already used by another process."
        for svc in busy_compose
        if svc not in running
    ]
    for app in busy_apps:
        owner = APP_SERVICES[app.name]
        if owner in running:
            hint = f"Compose service '{owner}' is running; stop it with "
            hint += f"`docker compose stop {owner}` or use --mode container."
        else:
            hint = f"Stop the process on port {app.port} or change the port in .env."
        messages.append(f"Port {app.port} for host {app.name} is already in use. {hint}")
    return messages


def _plan_host_apps(project: ResolvedProject, requested: set[str]) -> list[HostApp]:
    apps: list[HostApp] = []
    for name, build in (("backend", _backend_app), ("frontend", _frontend_app)):
        if name not in requested:
            continue
        app = build(project)
        if app is None:
            print_info(f"No runnable {name} found (framework or dev script missing), skipping")
        else:
            apps.append(app)
    return apps


def _supervise(apps: list[HostApp]) -> None:
    """Start host apps one by one, then keep them running until one exits."""
    supervisor = Supervisor()
    exit_code = 0
    with termination_signals():
        try:
            for app in apps:
                print_info(f"Starting {app.name}: {' '.join(app.cmd)}")
                try:
                    managed = supervisor.start(app.name, app.cmd, app.cwd, app.env)
                except OSError as exc:
                    print_error(f"Cannot start {app.name}: {exc}")
                    raise typer.Exit(code=1) from None
                ready = supervisor.wait_ready(
                    managed, partial(port_in_use, app.port), READY_TIMEOUT
                )
                if ready is False:
                    print_error(
                        f"{app.name} exited with code {managed.poll()} before listening on "
                        f"port {app.port}. See its log lines above."
                    )
                    raise typer.Exit(code=1)
                if ready is None:
                    print_warning(
                        f"{app.name} is not listening on port {app.port} after "
                        f"{READY_TIMEOUT:.0f}s; still running, watch its logs."
                    )
                else:
                    url = f"http://localhost:{app.port}"
                    print_success(f"{app.name} ready on {url} (PID {managed.pid})")
            console.print(
                "[dim]Press Ctrl+C to stop host dev servers. Docker services keep "
                "running; stop them with `docker compose stop`.[/dim]"
            )
            crashed = supervisor.first_exit()
            print_error(f"{crashed.name} exited with code {crashed.poll()}; stopping the others.")
            exit_code = 1
        except KeyboardInterrupt:
            print_info("Stopping host dev servers...")
            exit_code = 130
        except ProcessTerminationError as exc:
            print_info(f"Received {exc}; stopping host dev servers...")
            exit_code = 128 + exc.signum
        finally:
            supervisor.stop_all()
    raise typer.Exit(code=exit_code)


def _stop_containers(root: Path, services: list[str]) -> None:
    """Stop the app containers this run started; leave infrastructure running."""
    print_info(f"Stopping containers: {', '.join(services)}...")
    cmd = ["docker", "compose", "stop", *services]
    try:
        result = subprocess.run(cmd, cwd=root, timeout=COMPOSE_STOP_TIMEOUT)  # nosec B603 # Argv; trust project tools and PATH.
    except (subprocess.TimeoutExpired, OSError) as exc:
        print_error(f"`{' '.join(cmd)}` failed: {exc}")
        return
    if result.returncode != 0:
        print_error(f"`{' '.join(cmd)}` failed (exit {result.returncode})")


def _watch_containers(root: Path, services: list[str], logs: ManagedProcess) -> int:
    """Block until an app container stops running or the log stream ends."""
    while True:
        time.sleep(CONTAINER_POLL_INTERVAL)
        containers, error = compose_ps(root)
        if containers is None:
            print_error(f"Cannot query containers: {error}")
            return 1
        by_service = {c.service: c for c in containers}
        for service in services:
            container = by_service.get(service)
            if container is None or container.state != "running":
                state = container.summary if container else "removed"
                print_error(f"Container {service} is {state}; stopping app containers.")
                return 1
        if logs.poll() is not None:
            print_error("`docker compose logs -f` ended; is the Docker daemon still running?")
            return 1


def _run_containers(project: ResolvedProject, targets: list[str]) -> None:
    """Start Compose services; supervise app containers with visible logs."""
    root = project.root
    app_services = [s for s in targets if s in APP_SERVICES.values()]
    if not app_services:  # infrastructure only: nothing to supervise
        _compose_up(root, targets)
        _print_summary(project, "container", targets)
        return
    supervisor = Supervisor()
    exit_code = 0
    with termination_signals():
        try:
            _compose_up(root, targets)
            _print_summary(project, "container", targets)
            logs_cmd = ["docker", "compose", "logs", "-f", "--tail", "50", *app_services]
            logs = supervisor.start("compose", logs_cmd, root, dict(os.environ))
            console.print(
                f"[dim]Press Ctrl+C to stop {', '.join(app_services)}. Infrastructure keeps "
                "running; stop it with `docker compose stop`.[/dim]"
            )
            exit_code = _watch_containers(root, app_services, logs)
        except KeyboardInterrupt:
            exit_code = 130
        except ProcessTerminationError as exc:
            print_info(f"Received {exc}")
            exit_code = 128 + exc.signum
        finally:
            with shutdown_shield():
                supervisor.stop_all()
                _stop_containers(root, app_services)
    raise typer.Exit(code=exit_code)


def _print_summary(project: ResolvedProject, mode: str, compose: list[str]) -> None:
    table = create_table(f"Dev services ({mode} mode)", ["Service", "Runs in", "Port"])
    ports = _service_ports(project)
    for svc in compose:
        port = ports.get(svc)
        table.add_row(svc, "docker compose", str(port) if port else "-")
    console.print(table)


def run_dev(
    path: Path,
    services: str | None = None,
    no_docker: bool = False,
    mode: str | None = None,
) -> None:
    """Start development services in host or container mode."""
    path = path.resolve()
    if not path.is_dir():
        print_error(f"Directory not found: {path}")
        raise typer.Exit(code=1)
    try:
        project = resolve_project(path)
    except EnvFileError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from None
    mode = (mode or project.execution_mode or "host").lower()
    if mode not in MODES:
        print_error(f"Unknown mode '{mode}'. Use one of: {', '.join(MODES)}")
        raise typer.Exit(code=1)

    requested = _parse_services(services)
    if no_docker:
        if mode == "container":
            print_error("--no-docker cannot be combined with container mode")
            raise typer.Exit(code=1)
        requested.discard("docker")

    console.print()
    console.print(f"[bold cyan]mattstack dev[/bold cyan] [dim]({mode} mode)[/dim]")
    console.print()

    defined = compose_services(project.root)
    compose_targets = [s for s in INFRA_SERVICES if s in defined] if "docker" in requested else []
    apps: list[HostApp] = []
    if mode == "container":
        compose_targets += [
            APP_SERVICES[name]
            for name in ("backend", "frontend")
            if name in requested and APP_SERVICES[name] in defined
        ]
    else:
        apps = _plan_host_apps(project, requested)
    if "docker" in requested and not defined:
        print_info("No Compose file with services found, skipping Docker")

    if not compose_targets and not apps:
        print_error("No services to start. Check --services, --mode, and project structure.")
        raise typer.Exit(code=1)

    if compose_targets:
        _require_docker()
    conflicts = _conflicts(project, defined, compose_targets, apps)
    if conflicts:
        for message in conflicts:
            print_error(message)
        raise typer.Exit(code=1)

    if mode == "container":
        _run_containers(project, compose_targets)
        return
    if compose_targets:
        _compose_up(project.root, compose_targets)
        _print_summary(project, mode, compose_targets)
    if apps:
        _supervise(apps)
