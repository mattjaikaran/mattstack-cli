"""Lint command: unified linter for fullstack monorepos."""

from __future__ import annotations

import json
import subprocess  # nosec B404 # Required CLI subprocess support.
import time
from collections.abc import Sequence
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
    """Check if project has a Python backend."""
    backend_dir = path / "backend"
    return (backend_dir / "pyproject.toml").exists()


def _has_frontend(path: Path) -> bool:
    """Check if project has a frontend with lint script."""
    frontend_dir = path / "frontend"
    pkg = frontend_dir / "package.json"
    if not pkg.exists():
        return False
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
        return "lint" in scripts or ("lint:fix" in scripts)
    except (json.JSONDecodeError, OSError):
        return False


def _backend_lint_steps(fix: bool, format_check: bool) -> list[list[str]]:
    """Return ruff check (and optionally ruff format) commands for the backend."""
    check_args = ["uv", "run", "ruff", "check", "."]
    if fix:
        check_args.append("--fix")
    steps = [check_args]
    if format_check:
        fmt_args = ["uv", "run", "ruff", "format"]
        if not fix:
            fmt_args.append("--check")
        fmt_args.append(".")
        steps.append(fmt_args)
    return steps


def _frontend_lint_cmd(frontend_dir: Path, fix: bool) -> list[str] | None:
    """Return the frontend lint command, or None when package.json lacks the script."""
    pm = resolve_package_manager(frontend_dir)
    pkg = json.loads((frontend_dir / "package.json").read_text(encoding="utf-8"))
    scripts = pkg.get("scripts", {})
    script = "lint:fix" if (fix and "lint:fix" in scripts) else "lint"
    if script not in scripts:
        return None
    return build_run_cmd(pm, script).full


def _frontend_format_cmd(frontend_dir: Path, fix: bool) -> list[str] | None:
    """Use the frontend's own formatter, without assuming a specific binary."""
    scripts = json.loads((frontend_dir / "package.json").read_text()).get("scripts", {})
    script = "format" if fix else "format:check"
    if script not in scripts:
        return None
    return build_run_cmd(resolve_package_manager(frontend_dir), script).full


def _run_steps(steps: Sequence[Sequence[str]], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run ``steps`` in order with captured output; combine their results."""
    results: list[subprocess.CompletedProcess[str]] = []
    for argv in steps:
        try:
            results.append(subprocess.run(list(argv), cwd=cwd, text=True, capture_output=True))  # nosec B603 # Argv; trust project tools and PATH.
        except FileNotFoundError:
            message = missing_command_message(argv[0])
            results.append(subprocess.CompletedProcess(list(argv), COMMAND_NOT_FOUND, "", message))
            break
    combined_code = next((r.returncode for r in results if r.returncode != 0), 0)
    return subprocess.CompletedProcess(
        args=[],
        returncode=combined_code,
        stdout="\n".join(r.stdout for r in results if r.stdout),
        stderr="\n".join(r.stderr for r in results if r.stderr),
    )


def _missing_script_message(fix: bool) -> str:
    script = "lint:fix' or 'lint" if fix else "lint"
    return f"No '{script}' script in frontend/package.json"


def run_lint(
    path: Path,
    fix: bool = False,
    format_check: bool = False,
    backend_only: bool = False,
    frontend_only: bool = False,
    parallel: bool = False,
) -> None:
    """Run linters across backend and frontend."""
    path = path.resolve()
    if not path.is_dir():
        print_error(f"Directory not found: {path}")
        raise typer.Exit(code=1)

    has_be = _has_backend(path)
    has_fe = _has_frontend(path)

    run_backend = (backend_only or (not frontend_only and has_be)) and has_be
    run_frontend = (frontend_only or (not backend_only and has_fe)) and has_fe

    if not run_backend and not run_frontend:
        print_error("No backend or frontend to lint.")
        raise typer.Exit(code=1)

    console.print()
    console.print("[bold cyan]mattstack lint[/bold cyan]")
    console.print()

    start = time.perf_counter()
    results: list[tuple[str, int]] = []
    backend_steps = _backend_lint_steps(fix, format_check)
    frontend_dir = path / "frontend"
    frontend_cmd = _frontend_lint_cmd(frontend_dir, fix) if run_frontend else None
    if run_frontend and frontend_cmd is None:
        print_error(_missing_script_message(fix))
    frontend_steps = [frontend_cmd] if frontend_cmd is not None else []
    if run_frontend and format_check:
        format_cmd = _frontend_format_cmd(frontend_dir, fix)
        if format_cmd is not None:
            frontend_steps.append(format_cmd)

    if parallel and run_backend and run_frontend and frontend_cmd is not None:
        print_info("Linting backend and frontend in parallel...")
        be_code, fe_code = run_labeled_jobs(
            [
                LabeledJob("[backend]", backend_steps, path / "backend"),
                LabeledJob("[frontend]", frontend_steps, frontend_dir),
            ]
        )
        results = [("backend", be_code), ("frontend", fe_code)]
    else:
        if run_backend:
            print_info("Linting backend...")
            results.append(("backend", _report(_run_steps(backend_steps, path / "backend"))))

        if run_frontend:
            if frontend_cmd is None:
                results.append(("frontend", 1))
            else:
                print_info("Linting frontend...")
                results.append(("frontend", _report(_run_steps(frontend_steps, frontend_dir))))

    elapsed = time.perf_counter() - start

    table = create_table("Lint Results", ["Component", "Status"])
    all_ok = True
    for name, code in results:
        ok = code == 0
        all_ok &= ok
        status = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
        table.add_row(name, status)
    console.print()
    console.print(table)
    console.print(f"[dim]({elapsed:.1f}s)[/dim]")

    if not all_ok:
        if not fix:
            console.print("[dim]Tip: run `mattstack lint --fix` to auto-fix issues[/dim]")
        raise typer.Exit(code=1)
    print_success("All lint checks passed")


def _report(result: subprocess.CompletedProcess[str]) -> int:
    """Print captured tool output verbatim and return its exit code."""
    if result.returncode == COMMAND_NOT_FOUND:
        print_error(result.stderr)
        return result.returncode
    if result.stdout:
        console.print(result.stdout, markup=False, highlight=False, emoji=False)
    if result.stderr:
        console.print(result.stderr, markup=False, highlight=False, emoji=False)
    return result.returncode
