"""Deps command: dependency management for fullstack monorepos."""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 # Required CLI subprocess support.
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape

from mattstack.commands.deps_components import dependency_components
from mattstack.project import resolve_project
from mattstack.runtime_profiles import backend_sync_args
from mattstack.utils.console import (
    console,
    create_table,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from mattstack.utils.package_manager import (
    OutdatedRow,
    PackageManager,
    PMCommand,
    build_audit_cmd,
    build_outdated_cmd,
    build_update_cmd,
    parse_audit,
    parse_outdated,
    resolve_package_manager,
)

deps_app = typer.Typer(
    name="deps",
    help="Dependency management (check outdated, update, audit).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

Outdated = list[OutdatedRow]
Finding = tuple[str, str, str, str]  # (source, package, severity, detail)


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str] | None:
    """Run ``cmd`` and capture output. Return None when the program is missing."""
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)  # nosec B603 # Argv; trust project tools and PATH.
    except FileNotFoundError:
        print_warning(f"{cmd[0]} is not installed or not on PATH")
        return None


def _print_raw(text: str) -> None:
    """Print tool output verbatim, without Rich markup or highlighting."""
    console.print(text, markup=False, highlight=False)


def _check_backend(backend_dir: Path) -> Outdated | None:
    """Return outdated packages, or None when the check cannot complete."""
    if not (backend_dir / "pyproject.toml").exists():
        return _check_frontend(backend_dir, resolve_package_manager(backend_dir))
    environment = backend_dir / os.environ.get("UV_PROJECT_ENVIRONMENT", ".venv")
    result = _run(
        ["uv", "pip", "list", "--python", str(environment), "--outdated", "--format", "json"],
        backend_dir,
    )
    if result is None:
        return None
    if result.returncode != 0:
        print_error(f"Backend outdated check failed: {result.stderr.strip()}")
        return None
    try:
        packages = json.loads(result.stdout)
        if not isinstance(packages, list) or any(
            not isinstance(package, dict) or not isinstance(package.get("name"), str)
            for package in packages
        ):
            raise ValueError("Expected a package list with names")
    except (ValueError, TypeError):
        print_error("Failed to parse backend outdated output; the check is incomplete")
        return None
    return [(p["name"], p.get("version", "?"), p.get("latest_version", "?")) for p in packages]


def _check_frontend(frontend_dir: Path, pm: PackageManager) -> Outdated | None:
    """Return outdated packages, or None when the check cannot complete."""
    result = _run(build_outdated_cmd(pm).full, frontend_dir)
    if result is None:
        return None
    try:
        rows = parse_outdated(pm, result.stdout)
    except (ValueError, TypeError, AttributeError, IndexError):
        print_error(f"Cannot parse {pm.value} outdated output; the check is incomplete")
        return None
    # JSON package managers exit 1 for outdated packages, not just tool errors.
    if result.returncode != 0 and not rows:
        print_error(f"JavaScript outdated check failed: {result.stderr.strip()}")
        return None
    return rows


def _print_outdated(title: str, rows: Outdated) -> None:
    table = create_table(title, ["Package", "Current", "Latest"])
    for name, current, latest in rows:
        table.add_row(escape(name), escape(current), f"[yellow]{escape(latest)}[/yellow]")
    console.print(table)


@deps_app.command("check")
def check(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
) -> None:
    """Show outdated packages for backend and frontend."""
    start = time.perf_counter()
    backend, frontend = dependency_components(path)

    if backend is None and frontend is None:
        print_error("No backend or frontend found.")
        raise typer.Exit(code=1)

    console.print()
    console.print("[bold cyan]mattstack deps check[/bold cyan]")
    console.print()

    total_outdated = 0
    failed = False

    if backend is not None:
        print_info("Checking backend dependencies...")
        be_outdated = _check_backend(backend)
        if be_outdated is None:
            failed = True
        elif be_outdated:
            _print_outdated("Backend — Outdated Packages", be_outdated)
            total_outdated += len(be_outdated)
        else:
            print_success("Backend dependencies are up to date")
    else:
        print_info("No backend found, skipping")

    if frontend is not None:
        pm = resolve_package_manager(frontend)
        print_info(f"Checking frontend dependencies with {pm.value}...")
        fe_outdated = _check_frontend(frontend, pm)
        if fe_outdated is None:
            failed = True
        elif fe_outdated:
            _print_outdated("Frontend — Outdated Packages", fe_outdated)
            total_outdated += len(fe_outdated)
        else:
            print_success("Frontend dependencies are up to date")
    else:
        print_info("No frontend found, skipping")

    elapsed = time.perf_counter() - start
    console.print()
    if total_outdated:
        print_warning(f"{total_outdated} outdated package(s) found")
    console.print(f"[dim]({elapsed:.1f}s)[/dim]")
    if failed:
        raise typer.Exit(code=1)


def _update_backend(backend_dir: Path, *, major: bool = False) -> bool:
    print_info("Updating backend dependencies...")
    if not (backend_dir / "pyproject.toml").exists():
        return _update_frontend(backend_dir, major=major)
    try:
        project = resolve_project(backend_dir)
        sync_args = backend_sync_args(project.config, backend_dir)
    except (OSError, ValueError) as error:
        print_error(f"Cannot select backend dependencies: {error}")
        return False
    lock_result = _run(["uv", "lock", "--upgrade"], backend_dir)
    if lock_result is None:
        return False
    if lock_result.returncode != 0:
        print_error(f"uv lock failed: {lock_result.stderr.strip()}")
        return False
    sync_result = _run(sync_args, backend_dir)
    if sync_result is None:
        return False
    if sync_result.returncode != 0:
        print_error(f"uv sync failed: {sync_result.stderr.strip()}")
        return False
    print_success("Backend dependencies updated")
    return True


def _update_frontend(frontend_dir: Path, *, major: bool) -> bool:
    pm = resolve_package_manager(frontend_dir)
    cmd: PMCommand | None = build_update_cmd(pm, latest=major)
    if cmd is None:
        print_error(f"{pm.value} cannot update across major versions in one command")
        return False
    print_info(f"Updating JavaScript dependencies: {cmd}")
    result = _run(cmd.full, frontend_dir)
    if result is None:
        return False
    if result.returncode != 0:
        print_error(f"{cmd} failed: {result.stderr.strip()}")
        return False
    print_success("JavaScript dependencies updated")
    return True


@deps_app.command("update")
def update(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
    backend_only: Annotated[
        bool,
        typer.Option("--backend-only", help="Update backend only"),
    ] = False,
    frontend_only: Annotated[
        bool,
        typer.Option("--frontend-only", help="Update frontend only"),
    ] = False,
    major: Annotated[
        bool,
        typer.Option("--major", help="Include major version updates"),
    ] = False,
) -> None:
    """Update dependencies for backend and/or frontend."""
    start = time.perf_counter()
    backend, frontend = dependency_components(path)

    run_be = backend is not None and not frontend_only
    run_fe = frontend is not None and not backend_only

    if not run_be and not run_fe:
        print_error("No backend or frontend found to update.")
        raise typer.Exit(code=1)

    console.print()
    console.print("[bold cyan]mattstack deps update[/bold cyan]")
    console.print()

    results: list[tuple[str, bool]] = []
    if run_be and backend is not None:
        results.append(("backend", _update_backend(backend, major=major)))
    if run_fe and frontend is not None:
        results.append(("frontend", _update_frontend(frontend, major=major)))

    elapsed = time.perf_counter() - start

    table = create_table("Update Results", ["Component", "Status"])
    all_ok = True
    for name, ok in results:
        all_ok &= ok
        status = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
        table.add_row(name, status)
    console.print()
    console.print(table)
    console.print(f"[dim]({elapsed:.1f}s)[/dim]")

    if not all_ok:
        raise typer.Exit(code=1)


def _audit_backend(backend_dir: Path) -> tuple[list[Finding], bool]:
    """Return vulnerabilities and whether the scanner failed to verify the backend."""
    if not (backend_dir / "pyproject.toml").exists():
        return _audit_frontend(backend_dir, source="backend")
    print_info("Auditing backend dependencies...")
    result = _run(
        [
            "uv",
            "run",
            "--no-sync",
            "python",
            "-m",
            "pip_audit",
            "--skip-editable",
            "--format",
            "json",
        ],
        backend_dir,
    )
    if result is None:
        return [], True
    try:
        data = json.loads(result.stdout)
        dependencies = data["dependencies"]
        if not isinstance(dependencies, list):
            raise ValueError("Expected a dependency list")
        if any(
            not isinstance(dep, dict)
            or not isinstance(dep.get("name"), str)
            or not isinstance(dep.get("vulns"), list)
            or dep.get("skip_reason")
            for dep in dependencies
        ):
            raise ValueError("Incomplete dependency records")
        findings = [
            ("backend", dep["name"], (vuln.get("fix_versions") or ["?"])[0], vuln["id"])
            for dep in dependencies
            for vuln in dep.get("vulns", [])
        ]
    except (ValueError, KeyError, TypeError, AttributeError):
        print_error(
            "Backend audit is incomplete. Install pip-audit with `uv add --dev pip-audit` "
            "and retry `mattstack deps audit`."
        )
        _print_raw(result.stderr.strip() or result.stdout.strip())
        return [], True
    failed = result.returncode != 0 and not findings
    if failed:
        print_error(f"Backend audit failed: {result.stderr.strip()}")
    return findings, failed


def _audit_frontend(frontend_dir: Path, *, source: str = "frontend") -> tuple[list[Finding], bool]:
    """Audit JavaScript deps. Return (findings, unparsed_issues)."""
    pm = resolve_package_manager(frontend_dir)
    cmd = build_audit_cmd(pm)
    print_info(f"Auditing {source} dependencies: {cmd}")
    result = _run(cmd.full, frontend_dir)
    if result is None:
        return [], True
    if pm != PackageManager.BUN:
        try:
            findings: list[Finding] = [
                (source, *advisory) for advisory in parse_audit(pm, result.stdout)
            ]
        except (ValueError, TypeError, AttributeError):
            print_error(f"Cannot parse {pm.value} audit output; the audit is incomplete")
            _print_raw(result.stderr.strip() or result.stdout.strip())
            return [], True
        if result.returncode != 0 and not findings:
            print_warning(f"{cmd} failed: {result.stderr.strip() or result.stdout.strip()}")
            return [], True
        return findings, False
    # bun audit prints a human report and exits non-zero when it finds issues.
    if result.returncode == 0:
        return [], False
    _print_raw(result.stdout.strip() or result.stderr.strip())
    print_warning("bun audit reported problems (see output above)")
    return [], True


@deps_app.command("audit")
def audit(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Project path"),
    ] = None,
) -> None:
    """Run security audit on dependencies."""
    start = time.perf_counter()
    backend, frontend = dependency_components(path)

    if backend is None and frontend is None:
        print_error("No backend or frontend found.")
        raise typer.Exit(code=1)

    console.print()
    console.print("[bold cyan]mattstack deps audit[/bold cyan]")
    console.print()

    findings: list[Finding] = []
    unparsed_issues = False
    if backend is not None:
        be_findings, be_failed = _audit_backend(backend)
        findings.extend(be_findings)
        unparsed_issues |= be_failed
    if frontend is not None:
        fe_findings, fe_failed = _audit_frontend(frontend)
        findings.extend(fe_findings)
        unparsed_issues |= fe_failed

    elapsed = time.perf_counter() - start

    if findings:
        table = create_table(
            "Security Findings",
            ["Source", "Package", "Severity/Fix", "ID/Detail"],
        )
        for source, pkg, severity, detail in findings:
            table.add_row(source, escape(pkg), f"[red]{escape(severity)}[/red]", escape(detail))
        console.print(table)
        print_warning(f"{len(findings)} vulnerability(ies) found")
    elif not unparsed_issues:
        print_success("No vulnerabilities found")

    console.print(f"[dim]({elapsed:.1f}s)[/dim]")
    if findings or unparsed_issues:
        raise typer.Exit(code=1)
