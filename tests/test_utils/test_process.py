"""Tests for process utilities: port probing and dev server supervision."""

from __future__ import annotations

import contextlib
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

from mattstack.utils.process import (
    ProcessTerminationError,
    Supervisor,
    port_in_use,
    termination_signals,
)


def _listen(family: int, host: str) -> socket.socket:
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.bind((host, 0))
    sock.listen()
    return sock


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_port_in_use_detects_ipv4_listener() -> None:
    with _listen(socket.AF_INET, "127.0.0.1") as sock:
        port = sock.getsockname()[1]
        assert port_in_use(port) is True
    assert port_in_use(port) is False


def test_port_in_use_detects_ipv6_only_listener() -> None:
    if not socket.has_ipv6:
        pytest.skip("IPv6 unavailable")
    try:
        sock = _listen(socket.AF_INET6, "::1")
    except OSError:
        pytest.skip("IPv6 loopback unavailable")
    with sock:
        assert port_in_use(sock.getsockname()[1]) is True


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-only")
def test_stop_all_kills_grandchildren_of_exited_wrapper(tmp_path: Path) -> None:
    """A wrapper like `uv run` may exit while its server child keeps running."""
    pid_file = tmp_path / "grandchild.pid"
    script = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
        "print('wrapper up', flush=True)\n"
    )
    lines: list[tuple[str, str]] = []
    supervisor = Supervisor(sink=lambda name, line: lines.append((name, line)), stop_timeout=2)
    argv = [sys.executable, "-c", script]
    wrapper = supervisor.start("wrapper", argv, tmp_path, dict(os.environ))
    assert wrapper.proc is not None
    wrapper.proc.wait(timeout=10)
    deadline = time.monotonic() + 10
    while not pid_file.exists() or not pid_file.read_text():
        assert time.monotonic() < deadline
        time.sleep(0.05)
    grandchild = int(pid_file.read_text())

    supervisor.stop_all()

    deadline = time.monotonic() + 5
    while _pid_alive(grandchild) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _pid_alive(grandchild)
    assert ("wrapper", "wrapper up") in lines


def test_wait_ready_reports_exit_before_ready(tmp_path: Path) -> None:
    lines: list[tuple[str, str]] = []
    supervisor = Supervisor(sink=lambda name, line: lines.append((name, line)))
    managed = supervisor.start(
        "api",
        [sys.executable, "-c", "print('boom: settings missing'); raise SystemExit(3)"],
        tmp_path,
        dict(os.environ),
    )
    assert supervisor.wait_ready(managed, lambda: False, timeout=10) is False
    assert managed.poll() == 3
    assert ("api", "boom: settings missing") in lines


STUBBORN = (
    "import signal, time\n"
    "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    "print('armed', flush=True)\n"
    "time.sleep(60)\n"
)


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-only")
@pytest.mark.parametrize("repeat", [signal.SIGINT, signal.SIGTERM])
def test_repeated_signal_during_shutdown_still_kills_stubborn_group(
    tmp_path: Path, repeat: int
) -> None:
    """A second Ctrl+C/SIGTERM while waiting must not skip the final SIGKILL."""
    lines: list[tuple[str, str]] = []
    supervisor = Supervisor(sink=lambda name, line: lines.append((name, line)), stop_timeout=1.5)
    argv = [sys.executable, "-c", STUBBORN]
    managed = supervisor.start("stubborn", argv, tmp_path, dict(os.environ))
    assert managed.proc is not None
    try:
        deadline = time.monotonic() + 10
        while ("stubborn", "armed") not in lines:
            assert time.monotonic() < deadline
            time.sleep(0.05)
        timer = threading.Timer(0.3, os.kill, (os.getpid(), repeat))
        with termination_signals():
            timer.start()
            try:
                supervisor.stop_all()
            except (KeyboardInterrupt, ProcessTerminationError):
                pytest.fail("repeated signal interrupted shutdown")
            finally:
                timer.join()
        assert managed.proc.poll() == -signal.SIGKILL
    finally:
        if managed.proc.poll() is None:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(managed.proc.pid, signal.SIGKILL)
            managed.proc.wait(timeout=5)
