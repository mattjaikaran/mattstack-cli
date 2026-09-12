"""Subprocess boundary to the Gauntlet CLI.

MattStack does not implement checks. It calls `gauntlet check` and parses
the JSON document that Gauntlet writes to stdout.

The project's `gauntlet.toml` supplies the caller settings through its
`[integrations]` table. See `docs/spec/gauntlet-toml.md` in the Gauntlet
repository.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mattstack.gauntlet.models import RunResult, RunStatus, SchemaError

# Config file locations, in precedence order. Gauntlet reads both.
CONFIG_PATHS = ("gauntlet.toml", ".gauntlet/gauntlet.toml")

# Tier to run for an on-demand audit. The `full` tier runs the deterministic
# checks, plan conformance, and the AI review board.
DEFAULT_TIER = "full"

# Exit codes whose findings may not be trusted. From
# `docs/spec/exit-codes.md`, code 4 means Gauntlet failed at its own job and
# code 5 means the run was cut short. Both override a blocking failure, so
# the findings they emit are incomplete. mattstack reports them instead of
# presenting a partial run as a normal result.
UNUSABLE_EXIT_CODES = frozenset({4, 5})

# Wall-clock ceiling for the subprocess. Gauntlet enforces its own tier
# budget; this is only a safety net so mattstack never hangs.
DEFAULT_TIMEOUT_SECONDS = 900.0


class GauntletError(RuntimeError):
    """Gauntlet ran but mattstack could not use its output."""


class GauntletUnavailableError(GauntletError):
    """The Gauntlet binary is not on PATH or at the configured location."""

    def __init__(self, binary: str, *, skip_if_absent: bool) -> None:
        super().__init__(f"Gauntlet binary not found: {binary}")
        self.binary = binary
        self.skip_if_absent = skip_if_absent


@dataclass(frozen=True)
class GauntletConfig:
    """Caller settings from the `[integrations]` table."""

    binary_path: str = "gauntlet"
    skip_if_absent: bool = True
    default_target: str | None = None


def find_config_file(project_path: Path) -> Path | None:
    """Return the project's `gauntlet.toml`, or ``None`` when absent."""
    for relative in CONFIG_PATHS:
        candidate = project_path / relative
        if candidate.is_file():
            return candidate
    return None


def load_config(project_path: Path) -> GauntletConfig:
    """Read `[integrations]` from the project's config file.

    Returns defaults when the file is missing, the file is unreadable, or
    the table is absent. A project with no config file does not opt in to
    skipping, so an explicit `mattstack audit` fails when Gauntlet is
    missing. A `gauntlet.toml` that omits the field opts in, which matches
    the Gauntlet default for `skip_if_absent`.
    """
    config_path = find_config_file(project_path)
    if config_path is None:
        return GauntletConfig(skip_if_absent=False)

    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return GauntletConfig(skip_if_absent=False)

    integrations = raw.get("integrations")
    if not isinstance(integrations, Mapping):
        return GauntletConfig()

    binary = integrations.get("binary_path")
    skip = integrations.get("skip_if_absent")
    target = integrations.get("default_target")
    return GauntletConfig(
        binary_path=binary if isinstance(binary, str) and binary else "gauntlet",
        skip_if_absent=skip if isinstance(skip, bool) else True,
        default_target=target if isinstance(target, str) and target else None,
    )


def resolve_binary(config: GauntletConfig, project_path: Path) -> str | None:
    """Return an executable path for Gauntlet, or ``None`` when absent.

    A `binary_path` with a separator is resolved against the project
    directory. A bare name is looked up on PATH.
    """
    candidate = config.binary_path
    if "/" in candidate or "\\" in candidate:
        expanded = Path(candidate).expanduser()
        resolved = expanded if expanded.is_absolute() else project_path / expanded
        return str(resolved) if resolved.is_file() else None
    return shutil.which(candidate)


def _parse_payload(stdout: str) -> Mapping[str, Any] | None:
    """Parse a Gauntlet JSON document from stdout.

    Gauntlet writes only JSON to stdout in `--json` mode. This tolerates a
    stray leading line by falling back to the outermost brace pair.
    """
    text = stdout.strip()
    if not text:
        return None

    def _load(candidate: str) -> Mapping[str, Any] | None:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, Mapping) else None

    direct = _load(text)
    if direct is not None:
        return direct

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    return _load(text[start : end + 1])


def _failure_message(returncode: int, stderr: str) -> str:
    """Build a one-line explanation for a run with no parsable output."""
    detail = stderr.strip().splitlines()
    first = detail[0] if detail else ""
    reasons = {
        1: "Gauntlet rejected the command or config (usage error)",
        4: "Gauntlet hit an internal error",
        5: "Gauntlet exceeded its tier budget (timeout)",
    }
    reason = reasons.get(returncode, f"Gauntlet exited with code {returncode}")
    return f"{reason}: {first}" if first else reason


def check(
    project_path: Path,
    *,
    tier: str = DEFAULT_TIER,
    target: Path | None = None,
    config: GauntletConfig | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> RunResult:
    """Run `gauntlet check --tier=<tier> --json` and parse the result.

    Raises:
        GauntletUnavailableError: the binary is not installed.
        GauntletError: the run produced no parsable output, or Gauntlet
            exited with a code that makes its findings unusable.
    """
    settings = config if config is not None else load_config(project_path)
    binary = resolve_binary(settings, project_path)
    if binary is None:
        raise GauntletUnavailableError(settings.binary_path, skip_if_absent=settings.skip_if_absent)

    resolved_target = target or project_path
    command = [binary, "check", f"--tier={tier}", "--json", f"--target={resolved_target}"]

    try:
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"Gauntlet did not finish within {timeout:g}s"
        raise GauntletError(msg) from exc
    except OSError as exc:
        raise GauntletUnavailableError(
            settings.binary_path, skip_if_absent=settings.skip_if_absent
        ) from exc

    # An internal error or timeout invalidates the run, even when the JSON
    # document parses. Report it; do not present partial findings as a pass.
    if completed.returncode in UNUSABLE_EXIT_CODES:
        raise GauntletError(_failure_message(completed.returncode, completed.stderr))

    payload = _parse_payload(completed.stdout)
    if payload is None:
        raise GauntletError(_failure_message(completed.returncode, completed.stderr))

    try:
        result = RunResult.from_json(payload)
    except SchemaError as exc:
        raise GauntletError(str(exc)) from exc

    if result.status is RunStatus.ERROR:
        raise GauntletError(_failure_message(completed.returncode, completed.stderr))
    return result
