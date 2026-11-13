#!/usr/bin/env python3
"""Boot each frontend preset's dev server and check the shell, a route and the API proxy.

Scaffolds each preset into a temporary directory, installs its frontend from
the lockfile, starts the real `bun run dev`, and fails when the shell does not
load, a route does not resolve, the log shows a router transform error, or
(where the preset proxies `/api` to a backend) the proxy path is answered with
the SPA's HTML. "vite started" and "HTTP 200" alone are not proof.

This is a network-bound smoke check, not a gauntlet gate: it needs network
access and `bun` on PATH, needs port 3000 free, and never starts a backend.

Usage:
    python scripts/smoke_frontend_dev.py
    python scripts/smoke_frontend_dev.py --preset starter-fullstack --preset simple-frontend
    python scripts/smoke_frontend_dev.py --keep
"""

from __future__ import annotations

import argparse
import http.client
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Preset -> whether the frontend proxies /api to a backend that must answer it.
PRESET_PROXIES_API: dict[str, bool] = {
    "starter-fullstack": True,
    "rsbuild-fullstack": True,
    "kibo-fullstack": True,
    "simple-frontend": False,
    "nextjs-fullstack": False,
}
DEV_PORT = 3000
ROUTE_ERROR = "Error transforming route file"
TAIL_LINES = 20
REQUEST_TIMEOUT = 5
SETTLE_SECONDS = 2
POLL_SECONDS = 0.5
STOP_GRACE_SECONDS = 10


class DevServer(Protocol):
    """A running dev server listening on DEV_PORT."""

    def get(self, path: str) -> tuple[int, str]:
        """Return ``(status, body)``; status 0 means no HTTP response."""

    def log(self) -> str:
        """Return the dev server output so far."""


@dataclass(frozen=True)
class _LiveServer:
    log_path: Path

    def get(self, path: str) -> tuple[int, str]:
        conn = http.client.HTTPConnection("127.0.0.1", DEV_PORT, timeout=REQUEST_TIMEOUT)
        try:
            conn.request("GET", path)
            response = conn.getresponse()
            return response.status, response.read().decode(errors="replace")
        except (OSError, http.client.HTTPException) as exc:
            return 0, f"{type(exc).__name__}: {exc}"
        finally:
            conn.close()

    def log(self) -> str:
        return self.log_path.read_text(errors="replace")


def _kill_group(pid: int, sig: signal.Signals) -> None:
    with suppress(ProcessLookupError):
        os.killpg(pid, sig)


@contextmanager
def dev_server(cwd: Path, env: dict[str, str]) -> Iterator[DevServer]:
    """Run `bun run dev` in ``cwd``; always kill its whole process group on exit."""
    fd, name = tempfile.mkstemp(prefix="smoke-frontend-dev-", suffix=".log")
    os.close(fd)
    log_path = Path(name)
    try:
        # The child writes through its own descriptor; reading by path keeps
        # the file offset untouched.
        with log_path.open("w") as log_file:
            proc = subprocess.Popen(
                ["bun", "run", "dev"],
                cwd=cwd,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        try:
            yield _LiveServer(log_path)
        finally:
            _stop(proc)
    finally:
        log_path.unlink(missing_ok=True)


def _stop(proc: subprocess.Popen[bytes]) -> None:
    """Terminate the process group; escalate to SIGKILL after the grace period."""
    _kill_group(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=STOP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        _kill_group(proc.pid, signal.SIGKILL)
        proc.wait()
    # The leader may exit while vite's children keep the port; clear the group.
    _kill_group(proc.pid, signal.SIGKILL)


def _tail(output: str, lines: int = TAIL_LINES) -> list[str]:
    """Return the last ``lines`` non-empty lines of ``output``."""
    return [line for line in output.splitlines() if line.strip()][-lines:]


def _text(value: str | bytes | None) -> str:
    """Return captured output as text, tolerating bytes from a timed-out process."""
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def _run(
    runner: Callable[..., subprocess.CompletedProcess[str]],
    cmd: list[str],
    cwd: Path,
    timeout: int,
    env: dict[str, str],
) -> tuple[int | None, str]:
    """Run one step and return ``(exit code, combined output)``; ``None`` means timeout."""
    try:
        result = runner(
            cmd,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return None, _text(exc.output) + _text(exc.stderr)
    return result.returncode, _text(result.stdout) + _text(result.stderr)


def _port_in_use() -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", DEV_PORT)) == 0


def _prepare(
    preset: str,
    root: Path,
    args: argparse.Namespace,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    env: dict[str, str],
) -> bool:
    """Scaffold ``preset`` under ``root`` and install its frontend; False after printing FAIL."""
    name = f"smoke-{preset}"
    steps = [
        (
            "init",
            [
                sys.executable,
                "-m",
                "mattstack",
                "init",
                name,
                "-p",
                preset,
                "-o",
                str(root),
            ],
            root,
        ),
        ("bun install", ["bun", "install", "--frozen-lockfile"], root / name / "frontend"),
    ]
    for step, cmd, cwd in steps:
        code, output = _run(runner, cmd, cwd, args.timeout, env)
        if code != 0:
            if code is None:
                print(f"FAIL {preset}: {step} timed out after {args.timeout}s")
            else:
                print(f"FAIL {preset}: {step} exited {code}")
            for line in _tail(output):
                print(f"    {line}")
            return False
    return True


def _wait_ready(dev: DevServer, timeout: int) -> str | None:
    """Poll ``GET /`` until it returns 200; return that body, or None after ``timeout``."""
    deadline = time.monotonic() + timeout
    while True:
        status, body = dev.get("/")
        if status == 200:
            return body
        if time.monotonic() >= deadline:
            return None
        time.sleep(POLL_SECONDS)


def _check_dev_server(dev: DevServer, proxies_api: bool, ready_timeout: int) -> list[str]:
    """Run the checks against a live server; return failure descriptions (empty means pass)."""
    shell = _wait_ready(dev, ready_timeout)
    if shell is None:
        return [f"dev server not ready after {ready_timeout}s"]

    failures: list[str] = []
    if "<html" not in shell.lower():
        failures.append("shell: / is 200 but its body has no <html")
    dashboard_status, _ = dev.get("/dashboard")
    if dashboard_status != 200:
        failures.append(f"route: /dashboard returned {dashboard_status}")
    time.sleep(SETTLE_SECONDS)
    if ROUTE_ERROR in dev.log():
        failures.append(f"router: log contains {ROUTE_ERROR!r}")
    if proxies_api:
        status, body = dev.get("/api/health/")
        if status == 0:
            failures.append(f"proxy: /api/health/ got no response ({body})")
        elif "<html" in body.lower():
            failures.append(f"proxy: /api/health/ answered with the SPA HTML (status {status})")
    return failures


def _smoke_preset(
    preset: str,
    args: argparse.Namespace,
    env: dict[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]],
    server: Callable[..., AbstractContextManager[DevServer]],
) -> bool:
    started = time.monotonic()
    proxies_api = PRESET_PROXIES_API[preset]
    with tempfile.TemporaryDirectory(prefix=f"smoke-{preset}-", delete=not args.keep) as tmp:
        root = Path(tmp)
        ok = _prepare(preset, root, args, runner, env)
        if ok:
            with server(root / f"smoke-{preset}" / "frontend", env) as dev:
                failures = _check_dev_server(dev, proxies_api, args.ready_timeout)
                for failure in failures:
                    print(f"FAIL {preset}: {failure}")
                if failures:
                    for line in _tail(dev.log()):
                        print(f"    {line}")
            ok = not failures
        if args.keep:
            print(f"Kept {tmp}")

    if ok:
        print(f"PASS {preset} ({time.monotonic() - started:.1f}s)")
    return ok


def main(
    argv: list[str] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    server: Callable[..., AbstractContextManager[DevServer]] = dev_server,
) -> int:
    parser = argparse.ArgumentParser(
        description="Boot each frontend preset's dev server and smoke-check it."
    )
    parser.add_argument(
        "--preset",
        action="append",
        metavar="NAME",
        help=f"Preset to check (repeatable; default: {', '.join(PRESET_PROXIES_API)})",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep each temporary directory and print its path",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        metavar="SECONDS",
        help="Timeout for each init or install step (default: 600)",
    )
    parser.add_argument(
        "--ready-timeout",
        type=int,
        default=60,
        metavar="SECONDS",
        help="Seconds to wait for / to return 200 (default: 60)",
    )
    args = parser.parse_args(argv)

    known = list(PRESET_PROXIES_API)
    presets = args.preset or known
    unknown = [preset for preset in presets if preset not in PRESET_PROXIES_API]
    if unknown:
        print(f"Unknown preset(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Valid presets: {', '.join(known)}", file=sys.stderr)
        return 2
    if shutil.which("bun") is None:
        print("bun is required: https://bun.sh", file=sys.stderr)
        return 2
    if _port_in_use():
        print(
            f"port {DEV_PORT} is in use; the dev server needs port {DEV_PORT}",
            file=sys.stderr,
        )
        return 2

    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_COUNT"] = "0"

    failures = 0
    for preset in presets:
        if not _smoke_preset(preset, args, env, runner, server):
            failures += 1
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
