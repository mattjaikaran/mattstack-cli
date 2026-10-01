"""Subprocess execution utilities."""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import socket
import subprocess  # nosec B404 -- CLI executes trusted project tools; no shell.
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

LOOPBACK_HOSTS = ("127.0.0.1", "::1")


def command_available(name: str) -> bool:
    """Check if a command is available on PATH."""
    return shutil.which(name) is not None


def port_in_use(port: int, timeout: float = 0.3) -> bool:
    """Check whether anything accepts TCP connections on a loopback port.

    Probes IPv4 and IPv6 loopback, because dev servers on macOS often bind
    only `::1` (localhost) and containers publish on `0.0.0.0`.
    """
    for host in LOOPBACK_HOSTS:
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                if s.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue  # IPv6 disabled or unreachable family
    return False


def get_command_version(
    name: str, args: list[str] | None = None, timeout: float = 5.0
) -> str | None:
    """Get version string from a command; None when missing, failing, or hung."""
    if args is None:
        args = [name, "--version"]
    try:
        result = subprocess.run(  # nosec B603 -- Trusted argv and PATH; no shell.
            args, capture_output=True, text=True, check=True, timeout=timeout
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None


@dataclass
class ManagedProcess:
    """A supervised child process that runs in its own process group."""

    name: str
    cmd: list[str]
    cwd: Path
    env: dict[str, str]
    proc: subprocess.Popen[str] | None = None
    _reader: threading.Thread | None = field(default=None, repr=False)

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.proc else None

    def poll(self) -> int | None:
        return self.proc.poll() if self.proc else None


LineSink = Callable[[str, str], None]


def _default_sink(name: str, line: str) -> None:
    sys.stdout.write(f"[{name}] {line}\n")
    sys.stdout.flush()


class Supervisor:
    """Start, watch, and stop dev server process groups.

    Child output is streamed line by line with a `[name]` prefix. Each child
    gets its own process group (session), so stopping a child also stops
    the wrapper's descendants (`uv` → python → autoreloader, `bun` → vite).
    """

    def __init__(self, sink: LineSink = _default_sink, stop_timeout: float = 10.0) -> None:
        self.processes: list[ManagedProcess] = []
        self._sink = sink
        self._stop_timeout = stop_timeout

    def start(self, name: str, cmd: list[str], cwd: Path, env: dict[str, str]) -> ManagedProcess:
        """Start *cmd*; raises OSError when the executable cannot run."""
        managed = ManagedProcess(name=name, cmd=cmd, cwd=cwd, env=env)
        kwargs: dict[str, object] = {}
        if os.name == "posix":
            kwargs["start_new_session"] = True
        else:  # pragma: no cover - Windows only
            flags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            kwargs["creationflags"] = flags
        managed.proc = subprocess.Popen(  # nosec B603 -- Trusted argv and PATH; no shell.
            cmd,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            errors="replace",
            **kwargs,  # type: ignore[call-overload]
        )
        managed._reader = threading.Thread(target=self._pump, args=(managed,), daemon=True)
        managed._reader.start()
        self.processes.append(managed)
        return managed

    def _pump(self, managed: ManagedProcess) -> None:
        assert managed.proc is not None and managed.proc.stdout is not None  # nosec B101 -- PIPE invariant; not authorization.
        for line in managed.proc.stdout:
            self._sink(managed.name, line.rstrip("\n"))

    def wait_ready(
        self, managed: ManagedProcess, ready: Callable[[], bool], timeout: float
    ) -> bool | None:
        """Wait until *ready* is true.

        Returns True when ready, False when the process exited first, and
        None when the timeout passed while the process is still running.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if managed.poll() is not None:
                self.flush(managed)
                return False
            if ready():
                return True
            time.sleep(0.25)
        return None

    def flush(self, managed: ManagedProcess, timeout: float = 2.0) -> None:
        """Let the reader thread print the remaining output of an exited child."""
        if managed._reader is not None:
            managed._reader.join(timeout)

    def first_exit(self, poll_interval: float = 0.5) -> ManagedProcess:
        """Block until any supervised process exits and return it."""
        while True:
            for managed in self.processes:
                if managed.poll() is not None:
                    self.flush(managed)
                    return managed
            time.sleep(poll_interval)

    def _signal_group(self, managed: ManagedProcess, sig: int) -> None:
        if managed.proc is None:
            return
        try:
            if os.name == "posix":
                os.killpg(managed.proc.pid, sig)
            elif sig == signal.SIGTERM:  # pragma: no cover - Windows only
                managed.proc.terminate()
            else:  # pragma: no cover - Windows only
                managed.proc.kill()
        except (ProcessLookupError, PermissionError):
            pass

    def stop_all(self) -> None:
        """Terminate every process group; kill groups that ignore SIGTERM.

        Groups are signalled even after the wrapper exits, so grandchildren
        such as Django's autoreloader do not survive as orphans. A repeated
        Ctrl+C or SIGTERM during shutdown is ignored, so it cannot skip the
        final SIGKILL and leave groups running.
        """
        with shutdown_shield():
            for managed in self.processes:
                self._signal_group(managed, signal.SIGTERM)
            deadline = time.monotonic() + self._stop_timeout
            for managed in self.processes:
                if managed.proc is None:
                    continue
                remaining = max(0.0, deadline - time.monotonic())
                with contextlib.suppress(subprocess.TimeoutExpired):
                    managed.proc.wait(timeout=remaining)
                kill = signal.SIGKILL if os.name == "posix" else signal.SIGTERM
                self._signal_group(managed, kill)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    managed.proc.wait(timeout=2)
                self.flush(managed, timeout=1.0)


class ProcessTerminationError(Exception):
    """Raised in the main thread when SIGTERM or SIGHUP arrives."""

    def __init__(self, signum: int) -> None:
        super().__init__(signal.Signals(signum).name)
        self.signum = signum


_STOP_SIGNALS = ("SIGINT", "SIGTERM", "SIGHUP")


@contextlib.contextmanager
def _signal_handlers(names: tuple[str, ...], handler: object) -> Iterator[None]:
    """Install *handler* for the named signals, restoring the old ones after.

    Signal handlers can only change in the main thread; elsewhere this is a
    no-op.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous: dict[int, object] = {}
    for sig_name in names:
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            previous[sig] = signal.signal(sig, handler)  # type: ignore[arg-type]
    try:
        yield
    finally:
        for sig, old in previous.items():
            # None means the old handler was installed outside Python.
            signal.signal(sig, signal.SIG_DFL if old is None else old)  # type: ignore[arg-type]


def shutdown_shield() -> contextlib.AbstractContextManager[None]:
    """Ignore SIGINT/SIGTERM/SIGHUP while cleanup must run to completion."""
    return _signal_handlers(_STOP_SIGNALS, signal.SIG_IGN)


def termination_signals() -> contextlib.AbstractContextManager[None]:
    """Turn SIGTERM/SIGHUP into ProcessTerminationError for the duration.

    SIGINT already raises KeyboardInterrupt. Children live in their own
    sessions, so terminal Ctrl+C reaches only mattstack, which then stops
    the children itself.
    """

    def _raise(signum: int, _frame: object) -> None:
        raise ProcessTerminationError(signum)

    return _signal_handlers(("SIGTERM", "SIGHUP"), _raise)
