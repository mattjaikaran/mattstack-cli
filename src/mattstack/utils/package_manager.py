"""Package manager abstraction — detect and wrap bun/npm/yarn/pnpm."""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404 -- CLI executes trusted project tools; no shell.
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class PackageManager(StrEnum):
    BUN = "bun"
    NPM = "npm"
    YARN = "yarn"
    PNPM = "pnpm"


LOCKFILE_MAP: dict[str, PackageManager] = {
    "bun.lockb": PackageManager.BUN,
    "bun.lock": PackageManager.BUN,
    "package-lock.json": PackageManager.NPM,
    "yarn.lock": PackageManager.YARN,
    "pnpm-lock.yaml": PackageManager.PNPM,
}

DEFAULT_PM = PackageManager.BUN


@dataclass
class PMCommand:
    """Resolved package manager command with args."""

    program: str
    args: list[str]

    @property
    def full(self) -> list[str]:
        return [self.program, *self.args]

    def __str__(self) -> str:
        return " ".join(self.full)


@dataclass(frozen=True)
class PMResolution:
    """A resolved package manager and the reason it was chosen."""

    manager: PackageManager
    source: str


def _lockfile_dirs(project_path: Path) -> list[Path]:
    """Return the directories whose lockfiles decide the package manager.

    A component directory (``frontend/`` or ``backend/``) also checks its
    parent, because a workspace keeps one lockfile at the monorepo root.
    """
    dirs = [project_path]
    frontend_dir = project_path / "frontend"
    if frontend_dir.is_dir():
        dirs.insert(0, frontend_dir)
    if project_path.name in ("frontend", "backend"):
        dirs.append(project_path.parent)
    return dirs


def find_lockfile(project_path: Path) -> tuple[PackageManager, Path] | None:
    """Return the first lockfile that decides the package manager, if any."""
    for d in _lockfile_dirs(project_path):
        for lockfile, pm in LOCKFILE_MAP.items():
            if (d / lockfile).exists():
                return pm, d / lockfile
    return None


def detect_package_manager(project_path: Path) -> PackageManager:
    """Detect package manager from lockfiles in project or frontend/ subdirectory."""
    found = find_lockfile(project_path)
    return found[0] if found else DEFAULT_PM


PYTHON_LOCKFILES: dict[str, str] = {
    "uv.lock": "uv",
    "poetry.lock": "poetry",
    "Pipfile.lock": "pipenv",
}


def detect_python_package_manager(backend_dir: Path) -> str:
    """Return the Python package manager that the backend lockfile names (default uv)."""
    for lockfile, pm in PYTHON_LOCKFILES.items():
        if (backend_dir / lockfile).exists():
            return pm
    return "uv"


def _get_user_pm_override() -> PackageManager | None:
    """Return the user's default package manager from ~/.mattstack/config.yaml."""
    try:
        from mattstack.user_config import load_user_config

        config = load_user_config()
        pm_value = config.get("defaults", {}).get("package_manager")  # type: ignore
        if pm_value and isinstance(pm_value, str):
            return PackageManager(pm_value)
    except (ValueError, ImportError):
        pass
    return None


def resolve_package_manager_source(
    project_path: Path,
    override: str | None = None,
) -> PMResolution:
    """Resolve the package manager: explicit > project lockfile > user default > bun.

    A project lockfile records a decision the project already made, so the
    user default applies only to a project without one. Raises ValueError
    for an unknown explicit override instead of silently using another tool.
    """
    if override:
        try:
            return PMResolution(PackageManager(override), "explicit --pm option")
        except ValueError:
            valid = ", ".join(pm.value for pm in PackageManager)
            raise ValueError(f"Unknown package manager '{override}'. Valid: {valid}") from None

    found = find_lockfile(project_path)
    if found:
        return PMResolution(found[0], f"lockfile {found[1]}")

    user_pm = _get_user_pm_override()
    if user_pm:
        return PMResolution(user_pm, "user default (~/.mattstack/config.yaml)")

    return PMResolution(DEFAULT_PM, f"default ({DEFAULT_PM.value})")


def resolve_package_manager(
    project_path: Path,
    override: str | None = None,
) -> PackageManager:
    """Resolve which package manager to use. See resolve_package_manager_source."""
    return resolve_package_manager_source(project_path, override).manager


_EXACT_FLAGS: dict[PackageManager, str] = {
    PackageManager.BUN: "--exact",
    PackageManager.NPM: "--save-exact",
    PackageManager.YARN: "--exact",
    PackageManager.PNPM: "--save-exact",
}


def build_add_cmd(
    pm: PackageManager, packages: list[str], *, dev: bool = False, exact: bool = False
) -> PMCommand:
    """Build an 'add package' command.

    ``exact`` records the resolved version without a range (``1.2.3``, not
    ``^1.2.3``), so an optional tool stays pinned.
    """
    match pm:
        case PackageManager.BUN:
            args = ["add", *packages]
            if dev:
                args.insert(1, "-d")
        case PackageManager.NPM:
            args = ["install", *packages]
            if dev:
                args.append("--save-dev")
        case PackageManager.YARN:
            args = ["add", *packages]
            if dev:
                args.append("--dev")
        case PackageManager.PNPM:
            args = ["add", *packages]
            if dev:
                args.append("-D")
    if exact:
        args.append(_EXACT_FLAGS[pm])
    return PMCommand(program=pm.value, args=args)


def build_remove_cmd(pm: PackageManager, packages: list[str]) -> PMCommand:
    """Build a 'remove package' command."""
    verb = "uninstall" if pm == PackageManager.NPM else "remove"
    return PMCommand(program=pm.value, args=[verb, *packages])


def build_install_cmd(pm: PackageManager) -> PMCommand:
    """Build an 'install all deps' command."""
    return PMCommand(program=pm.value, args=["install"])


def build_run_cmd(
    pm: PackageManager, script: str, extra_args: list[str] | None = None
) -> PMCommand:
    """Build a 'run script' command."""
    args = ["run", script]
    if extra_args:
        args.extend(extra_args)
    return PMCommand(program=pm.value, args=args)


def build_exec_cmd(
    pm: PackageManager, binary: str, extra_args: list[str] | None = None
) -> PMCommand:
    """Build an 'exec binary' command (npx/bunx/pnpm exec/yarn dlx)."""
    match pm:
        case PackageManager.BUN:
            prog, args = "bunx", [binary]
        case PackageManager.NPM:
            prog, args = "npx", [binary]
        case PackageManager.YARN:
            prog, args = "yarn", ["dlx", binary]
        case PackageManager.PNPM:
            prog, args = "pnpm", ["dlx", binary]
    if extra_args:
        args.extend(extra_args)
    return PMCommand(program=prog, args=args)


def build_outdated_cmd(pm: PackageManager) -> PMCommand:
    """Build an 'outdated packages' command. npm, pnpm, and yarn report JSON."""
    match pm:
        case PackageManager.BUN:
            args = ["outdated"]
        case PackageManager.NPM:
            args = ["outdated", "--json"]
        case PackageManager.YARN:
            args = ["outdated", "--json"]
        case PackageManager.PNPM:
            args = ["outdated", "--format", "json"]
    return PMCommand(program=pm.value, args=args)


def build_update_cmd(pm: PackageManager, *, latest: bool = False) -> PMCommand | None:
    """Build an 'update dependencies' command.

    Return None when ``latest`` is set and the manager cannot cross major
    versions in one command (npm).
    """
    match pm:
        case PackageManager.NPM:
            if latest:
                return None
            args = ["update"]
        case PackageManager.YARN:
            args = ["upgrade", *(["--latest"] if latest else [])]
        case PackageManager.BUN | PackageManager.PNPM:
            args = ["update", *(["--latest"] if latest else [])]
    return PMCommand(program=pm.value, args=args)


def build_audit_cmd(pm: PackageManager) -> PMCommand:
    """Build a 'security audit' command. npm, pnpm, and yarn report JSON."""
    args = ["audit"] if pm == PackageManager.BUN else ["audit", "--json"]
    return PMCommand(program=pm.value, args=args)


# (package, current, latest) for an outdated dependency.
OutdatedRow = tuple[str, str, str]
# (package, severity, detail) for an audit advisory.
Advisory = tuple[str, str, str]


def _json_lines(stdout: str) -> list[dict[str, Any]]:
    """Parse newline-delimited JSON (yarn classic), skipping non-JSON lines."""
    records: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _json_object(stdout: str) -> dict[str, Any]:
    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def parse_outdated(pm: PackageManager, stdout: str) -> list[OutdatedRow]:
    """Parse the output of ``build_outdated_cmd(pm)``."""
    if pm in (PackageManager.NPM, PackageManager.PNPM):
        return [
            (name, str(info.get("current", "?")), str(info.get("latest", "?")))
            for name, info in _json_object(stdout).items()
            if isinstance(info, dict)
        ]
    rows: list[OutdatedRow] = []
    if pm == PackageManager.YARN:
        for record in _json_lines(stdout):
            if record.get("type") == "table":
                for row in record.get("data", {}).get("body", []):
                    rows.append((str(row[0]), str(row[1]), str(row[3])))
        return rows
    # bun prints a box table: | Package | Current | Update | Latest |
    for line in stdout.splitlines():
        if "│" not in line and "|" not in line:
            continue
        cells = [cell.strip() for cell in re.split(r"[│|]", line) if cell.strip()]
        if len(cells) < 3 or cells[0].startswith(("Package", "─", "-")):
            continue
        rows.append((cells[0], cells[1], cells[-1]))
    return rows


def parse_audit(pm: PackageManager, stdout: str) -> list[Advisory]:
    """Parse the JSON output of ``build_audit_cmd(pm)`` for npm, pnpm, and yarn."""
    if pm == PackageManager.YARN:
        return [
            _advisory(record.get("data", {}).get("advisory", {}))
            for record in _json_lines(stdout)
            if record.get("type") == "auditAdvisory"
        ]
    data = _json_object(stdout)
    # pnpm (and npm 6) report `advisories`; npm 7+ reports `vulnerabilities`.
    findings = [_advisory(advisory) for advisory in (data.get("advisories") or {}).values()]
    for name, vuln in (data.get("vulnerabilities") or {}).items():
        via = (vuln.get("via") or [""])[0]
        detail = via.get("title", "") if isinstance(via, dict) else str(via)
        findings.append((name, str(vuln.get("severity", "unknown")), detail))
    return findings


def _advisory(advisory: dict[str, Any]) -> Advisory:
    return (
        str(advisory.get("module_name", "?")),
        str(advisory.get("severity", "unknown")),
        str(advisory.get("title", "")),
    )


def run_pm_command(cmd: PMCommand, *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Execute a package manager command, streaming output."""
    return subprocess.run(  # nosec B603 -- Trusted argv and PATH; no shell.
        cmd.full,
        cwd=cwd,
        text=True,
        capture_output=False,
    )
