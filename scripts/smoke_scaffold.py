#!/usr/bin/env python3
"""Scaffold presets into temporary directories and run each project's `just ci`.

This is a network-bound smoke check, not a gauntlet gate: it clones the
selected source repositories and needs `just`, `uv` and `bun` on PATH.
It also checks that each `just <recipe>` cited in an AGENTS.md resolves from the root.

Usage:
    python scripts/smoke_scaffold.py
    python scripts/smoke_scaffold.py --preset starter-api --preset starter-frontend
    python scripts/smoke_scaffold.py --all
    python scripts/smoke_scaffold.py --keep
"""

from __future__ import annotations

import argparse
import os
import re
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

# Component AGENTS.md files cite recipes as `just <recipe>`. Each file's recipes
# carry its directory prefix at the root (see templates/root_agents_md.py).
AGENTS_RECIPE_PREFIXES: dict[str, str] = {
    "AGENTS.md": "",
    "backend/AGENTS.md": "backend-",
    "frontend/AGENTS.md": "frontend-",
}
# A citation opens a code span or a line. The lookahead rejects placeholders such
# as `backend-<recipe>`, which the pattern would otherwise read as `backend`.
_RECIPE_CITATION = re.compile(
    r"(?:^|`)\s*just\s+([a-z][a-z0-9]*(?:-[a-z0-9]+)*)(?![-<\w])",
    re.M,
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


def _unresolved_recipes(
    project: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    timeout: int,
    env: dict[str, str],
) -> list[str]:
    """Return one line per recipe cited in an AGENTS.md that the root justfile lacks."""
    cited: list[tuple[str, str, str]] = []  # (file, name as written, root recipe)
    for relative, prefix in AGENTS_RECIPE_PREFIXES.items():
        path = project / relative
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            cited += [(relative, name, prefix + name) for name in _RECIPE_CITATION.findall(text)]
    if not cited:
        return []
    code, output = _run(runner, ["just", "--summary"], project, timeout, env)
    if code != 0:
        return [f"just --summary exited {code}"]
    defined = set(output.split())
    return [
        f"{relative}: `just {name}` needs root recipe `{recipe}`"
        for relative, name, recipe in cited
        if recipe not in defined
    ]


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
            if failure is None:
                unresolved = _unresolved_recipes(root / name, runner, args.timeout, env)
                if unresolved:
                    failure = ("AGENTS.md recipes", 1, "\n".join(unresolved))

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
