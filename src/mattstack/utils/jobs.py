"""Run labeled command jobs (lint, test) with streamed, markup-safe output."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from rich.text import Text

from mattstack.utils.console import console, print_error

COMMAND_NOT_FOUND = 127

_INSTALL_HINTS: dict[str, str] = {
    "uv": "Install uv: https://docs.astral.sh/uv/getting-started/installation/",
    "bun": "Install bun: https://bun.sh/docs/installation",
    "npm": "Install Node.js: https://nodejs.org/",
    "pnpm": "Install pnpm: https://pnpm.io/installation",
    "yarn": "Install yarn: https://yarnpkg.com/getting-started/install",
}


def missing_command_message(executable: str) -> str:
    """Return an actionable message for an executable that is not on PATH."""
    hint = _INSTALL_HINTS.get(Path(executable).name, "Install it or add it to PATH.")
    return f"Command not found: {executable}. {hint}"


@dataclass(frozen=True)
class LabeledJob:
    """Sequential command steps run in ``cwd``; output lines are prefixed with ``label``."""

    label: str
    steps: Sequence[Sequence[str]]
    cwd: Path


class _JobRunner:
    """Tracks live child processes so cancellation never leaves orphans."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._procs: list[subprocess.Popen[str]] = []
        self._cancelled = False

    def _print_line(self, label: str, line: str) -> None:
        text = Text.assemble((label, "dim"), " ", line.rstrip("\r\n"))
        with self._lock:
            console.print(text, soft_wrap=True, highlight=False)

    def _spawn(self, argv: Sequence[str], cwd: Path) -> subprocess.Popen[str] | None:
        with self._lock:
            if self._cancelled:
                return None
            # Own process group per step so cancel() also reaches descendants
            # (uv/bun wrappers spawn children that inherit the stdout pipe).
            proc = subprocess.Popen(
                list(argv),
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            self._procs.append(proc)
            return proc

    def run(self, job: LabeledJob) -> int:
        """Run every step of ``job``; return 0 only when all steps succeed."""
        exit_code = 0
        for argv in job.steps:
            try:
                proc = self._spawn(argv, job.cwd)
            except FileNotFoundError:
                print_error(f"{job.label} {missing_command_message(argv[0])}")
                return COMMAND_NOT_FOUND
            if proc is None:
                return 1
            if proc.stdout is not None:
                for line in proc.stdout:
                    self._print_line(job.label, line)
            proc.wait()
            code = proc.returncode if proc.returncode is not None else 1
            if code != 0:
                exit_code = code
        return exit_code

    def cancel(self) -> None:
        """Stop spawning new steps and terminate every child process group."""
        with self._lock:
            self._cancelled = True
            procs = list(self._procs)
        for proc in procs:
            _signal_group(proc, signal.SIGTERM)
        for proc in procs:
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=5)
        # Descendants can outlive their wrapper and keep the pipe open.
        for proc in procs:
            _signal_group(proc, signal.SIGKILL)
            proc.wait()


def _signal_group(proc: subprocess.Popen[str], sig: signal.Signals) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, sig)


def run_labeled_jobs(jobs: Sequence[LabeledJob]) -> list[int]:
    """Run ``jobs`` concurrently, streaming labeled output; return exit codes in order.

    A missing executable yields ``COMMAND_NOT_FOUND`` for that job only. An
    interrupt or unexpected error terminates all children before re-raising.
    """
    runner = _JobRunner()
    with ThreadPoolExecutor(max_workers=max(1, len(jobs))) as executor:
        futures = [executor.submit(runner.run, job) for job in jobs]
        try:
            return [future.result() for future in futures]
        except BaseException:
            runner.cancel()
            raise
