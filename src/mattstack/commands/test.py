"""Test command: unified test runner for fullstack monorepos."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import typer

from mattstack.utils.console import console, create_table, print_error, print_info, print_success
from mattstack.utils.jobs import (
    COMMAND_NOT_FOUND,
    LabeledJob,
    missing_command_message,
    run_labeled_jobs,
)
from mattstack.utils.package_manager import (
    build_run_cmd,
    resolve_package_manager,
)


def _has_backend(path: Path) -> bool:
    """Check if project has a Python backend with pytest."""
    backend_dir = path / "backend"
    return (backend_dir / "pyproject.toml").exists()


def _has_frontend(path: Path) -> bool:
    """Check if project has a frontend with test script."""
    frontend_dir = path / "frontend"
    pkg = frontend_dir / "package.json"
    if not pkg.exists():
        return False
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
        return "test" in scripts or "test:coverage" in scripts
    except (json.JSONDecodeError, OSError):
        return False


def _backend_test_cmd(coverage: bool) -> list[str]:
    args = ["uv", "run", "pytest", "-v"]
    if coverage:
        args.extend(["--cov", "--cov-report=term-missing"])
    return args


def _frontend_test_cmd(frontend_dir: Path, coverage: bool) -> list[str] | None:
    """Return the frontend test command, or None when package.json lacks a test script."""
    pm = resolve_package_manager(frontend_dir)
    pkg = json.loads((frontend_dir / "package.json").read_text(encoding="utf-8"))
    scripts = pkg.get("scripts", {})
    if coverage and "test:coverage" in scripts:
        return build_run_cmd(pm, "test:coverage").full
    if "test" in scripts:
        return build_run_cmd(pm, "test").full
    return None


def _run_inherited(argv: list[str], cwd: Path) -> int:
    """Run ``argv`` with the terminal's stdio; report a missing executable."""
    try:
        return subprocess.run(argv, cwd=cwd, text=True).returncode
    except FileNotFoundError:
        print_error(missing_command_message(argv[0]))
        return COMMAND_NOT_FOUND


def run_test(
    path: Path,
    backend_only: bool = False,
    frontend_only: bool = False,
    coverage: bool = False,
    parallel: bool = False,
) -> None:
    """Run tests across backend and frontend."""
    path = path.resolve()
    if not path.is_dir():
        print_error(f"Directory not found: {path}")
        raise typer.Exit(code=1)

    has_be = _has_backend(path)
    has_fe = _has_frontend(path)

    run_backend = (backend_only or (not frontend_only and has_be)) and has_be
    run_frontend = (frontend_only or (not backend_only and has_fe)) and has_fe

    if not run_backend and not run_frontend:
        print_error("No backend or frontend tests found.")
        raise typer.Exit(code=1)

    console.print()
    console.print("[bold cyan]mattstack test[/bold cyan]")
    console.print()

    start = time.perf_counter()
    results: list[tuple[str, int]] = []
    backend_cmd = _backend_test_cmd(coverage)
    frontend_dir = path / "frontend"
    frontend_cmd = _frontend_test_cmd(frontend_dir, coverage) if run_frontend else None
    if run_frontend and frontend_cmd is None:
        print_error("No 'test' or 'test:coverage' script in frontend/package.json")

    if parallel and run_backend and run_frontend and frontend_cmd is not None:
        print_info("Running backend and frontend tests in parallel...")
        be_code, fe_code = run_labeled_jobs(
            [
                LabeledJob("[backend]", [backend_cmd], path / "backend"),
                LabeledJob("[frontend]", [frontend_cmd], frontend_dir),
            ]
        )
        results = [("backend", be_code), ("frontend", fe_code)]
    else:
        if run_backend:
            print_info("Running backend tests...")
            results.append(("backend", _run_inherited(backend_cmd, path / "backend")))

        if run_frontend:
            if frontend_cmd is None:
                results.append(("frontend", 1))
            else:
                print_info("Running frontend tests...")
                results.append(("frontend", _run_inherited(frontend_cmd, frontend_dir)))

    # Summary table
    table = create_table("Test Results", ["Component", "Status"])
    all_ok = True
    for name, code in results:
        ok = code == 0
        all_ok &= ok
        status = "[green]PASS[/green]" if ok else "[red]FAIL[/red]"
        table.add_row(name, status)
    elapsed = time.perf_counter() - start
    console.print()
    console.print(table)
    console.print(f"[dim]({elapsed:.1f}s)[/dim]")

    if not all_ok:
        raise typer.Exit(code=1)
    print_success("All tests passed")
