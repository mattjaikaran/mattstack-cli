#!/usr/bin/env python3
"""Scaffold presets into temporary directories and run each project's `just ci`.

This is a network-bound smoke check, not a gauntlet gate: it clones the
selected source repositories and needs `just`, `uv` and `bun` on PATH.

Usage:
    python scripts/smoke_scaffold.py
    python scripts/smoke_scaffold.py --preset starter-api --preset starter-frontend
    python scripts/smoke_scaffold.py --all
    python scripts/smoke_scaffold.py --keep
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from mattstack.presets import PRESETS

DEFAULT_PRESETS = ("starter-fullstack", "starter-api", "starter-frontend")
TAIL_LINES = 20

# Backend files the monorepo must not carry (see consolidate._BACKEND_AGENT_PATHS).
BACKEND_LEFTOVERS = (
    "AGENTS.md",
    "CLAUDE.md",
    "docs/tickets",
    "scripts/tickets.py",
    "scripts/worker_once.py",
)


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


def main(
    argv: list[str] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold presets and run `just ci` in each generated project."
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--preset",
        action="append",
        metavar="NAME",
        help=f"Preset to smoke (repeatable; default: {', '.join(DEFAULT_PRESETS)})",
    )
    selection.add_argument(
        "--all",
        action="store_true",
        help="Smoke every preset in mattstack.presets.PRESETS",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep each temporary directory and print its path",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=900,
        metavar="SECONDS",
        help="Timeout for each init or `just ci` step (default: 900)",
    )
    args = parser.parse_args(argv)

    known = list(PRESETS)
    presets = known if args.all else list(args.preset or DEFAULT_PRESETS)
    unknown = [preset for preset in presets if preset not in PRESETS]
    if unknown:
        print(f"Unknown preset(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Valid presets: {', '.join(known)}", file=sys.stderr)
        return 2

    if shutil.which("just") is None:
        print(
            "just is required: https://github.com/casey/just#installation",
            file=sys.stderr,
        )
        return 2

    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_COUNT"] = "0"

    failures = 0
    for preset in presets:
        started = time.monotonic()
        name = f"smoke-{preset}"
        with tempfile.TemporaryDirectory(prefix=f"{name}-", delete=not args.keep) as tmp:
            root = Path(tmp)
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
                ("just ci", ["just", "ci"], root / name),
            ]
            failure: tuple[str, int | None, str] | None = None
            for step, cmd, cwd in steps:
                code, output = _run(runner, cmd, cwd, args.timeout, env)
                if code != 0:
                    failure = (step, code, output)
                    break
            if failure is None:
                leftover = [
                    rel for rel in BACKEND_LEFTOVERS if (root / name / "backend" / rel).exists()
                ]
                if leftover:
                    failure = ("backend files", 1, "present: " + ", ".join(leftover))

        elapsed = time.monotonic() - started
        if failure is None:
            print(f"PASS {preset} ({elapsed:.1f}s)")
        else:
            step, code, output = failure
            failures += 1
            if code is None:
                print(f"FAIL {preset}: {step} timed out after {args.timeout}s")
            else:
                print(f"FAIL {preset}: {step} exited {code}")
            for line in _tail(output):
                print(f"    {line}")
        if args.keep:
            print(f"Kept {tmp}")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
