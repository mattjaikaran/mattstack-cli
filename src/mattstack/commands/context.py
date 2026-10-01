"""Context command group: dump project context for AI agents."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from mattstack.commands.context_builders import (
    build_full_context,
    build_models_context,
    build_routes_context,
    build_stack_context,
    build_types_context,
)
from mattstack.commands.context_format import FORMATS, apply_format, truncate_to_tokens
from mattstack.project import EnvFileError, find_project_root
from mattstack.utils.console import err_console, print_error, print_success, write_raw

context_app = typer.Typer(
    help="Dump project context for AI agents (Claude, Cursor, etc.).",
    no_args_is_help=True,
)

WATCH_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".next",
        "dist",
        "build",
        "coverage",
        "htmlcov",
    }
)


def _output(text: str, output_file: str | None) -> None:
    if output_file:
        out = Path(output_file)
        try:
            out.write_text(text, encoding="utf-8")
        except OSError as exc:
            print_error(f"Cannot write {out}: {exc.strerror or exc}")
            raise typer.Exit(code=1) from None
        print_success(f"Context written to {out}")
    else:
        write_raw(text)


# ── watch helper ──────────────────────────────────────────────────────────────


def _watch_snapshot(path: Path) -> dict[str, float]:
    """Map watched source files to mtimes, skipping vendor and build directories."""
    snap: dict[str, float] = {}
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in WATCH_SKIP_DIRS]
        for name in filenames:
            if name.endswith((".py", ".ts")):
                file = os.path.join(dirpath, name)
                try:
                    snap[file] = os.path.getmtime(file)
                except OSError:
                    continue
    return snap


def _watch_loop(
    path: Path,
    builder: Callable[[Path], dict[str, Any]],
    fmt: str,
    max_tokens: int | None,
    output: str | None = None,
) -> None:
    """Poll for file changes and re-emit context; status lines go to stderr."""
    import datetime

    def _emit() -> None:
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        err_console.print(f"\n[dim]── {stamp} ──[/dim]")
        _emit_context(path, builder, fmt, output, max_tokens)

    _emit()
    snap = _watch_snapshot(path)
    err_console.print("[dim]Watching for changes... (Ctrl-C to stop)[/dim]")
    try:
        while True:
            time.sleep(1)
            new_snap = _watch_snapshot(path)
            if new_snap != snap:
                snap = new_snap
                _emit()
    except KeyboardInterrupt:
        pass


def _project_root(path: Path | None, fmt: str) -> Path:
    """Validate the format and path, then return the enclosing project root."""
    if fmt not in FORMATS:
        print_error(f"Unknown format: '{fmt}'. Valid: {', '.join(FORMATS)}")
        raise typer.Exit(code=2)
    target = path or Path.cwd()
    if not target.is_dir():
        print_error(f"Directory not found: {target}")
        raise typer.Exit(code=1)
    return find_project_root(target)


def _emit_context(
    root: Path,
    builder: Callable[[Path], dict[str, Any]],
    fmt: str,
    output: str | None,
    max_tokens: int | None,
) -> None:
    try:
        ctx = builder(root)
    except EnvFileError as error:
        print_error(str(error))
        raise typer.Exit(code=1) from error
    if max_tokens:
        ctx = truncate_to_tokens(ctx, max_tokens, fmt)
    _output(apply_format(ctx, fmt), output)


# ── common options ────────────────────────────────────────────────────────────

_FMT_HELP = "Output format: markdown (default), json, claude"
_PATH_HELP = "Project path (default: current directory)"
_OUTPUT_HELP = "Write output to a file"
_MAX_TOKENS_HELP = "Truncate output to approximately N tokens"
_WATCH_HELP = "Re-emit context on file changes (poll mode)"


# ── subcommands ───────────────────────────────────────────────────────────────


@context_app.command("stack")
def cmd_stack(
    path: Annotated[Path | None, typer.Argument(help=_PATH_HELP)] = None,
    fmt: Annotated[str, typer.Option("--format", "-f", help=_FMT_HELP)] = "markdown",
    output: Annotated[str | None, typer.Option("--output", "-o", help=_OUTPUT_HELP)] = None,
    max_tokens: Annotated[int | None, typer.Option("--max-tokens", help=_MAX_TOKENS_HELP)] = None,
) -> None:
    """Tech stack summary (languages, frameworks, tools)."""
    _emit_context(_project_root(path, fmt), build_stack_context, fmt, output, max_tokens)


@context_app.command("models")
def cmd_models(
    path: Annotated[Path | None, typer.Argument(help=_PATH_HELP)] = None,
    fmt: Annotated[str, typer.Option("--format", "-f", help=_FMT_HELP)] = "markdown",
    output: Annotated[str | None, typer.Option("--output", "-o", help=_OUTPUT_HELP)] = None,
    max_tokens: Annotated[int | None, typer.Option("--max-tokens", help=_MAX_TOKENS_HELP)] = None,
) -> None:
    """All Django models with field types as structured output."""
    _emit_context(_project_root(path, fmt), build_models_context, fmt, output, max_tokens)


@context_app.command("routes")
def cmd_routes(
    path: Annotated[Path | None, typer.Argument(help=_PATH_HELP)] = None,
    fmt: Annotated[str, typer.Option("--format", "-f", help=_FMT_HELP)] = "markdown",
    output: Annotated[str | None, typer.Option("--output", "-o", help=_OUTPUT_HELP)] = None,
    max_tokens: Annotated[int | None, typer.Option("--max-tokens", help=_MAX_TOKENS_HELP)] = None,
) -> None:
    """All API routes with methods, paths, controller, and auth."""
    _emit_context(_project_root(path, fmt), build_routes_context, fmt, output, max_tokens)


@context_app.command("types")
def cmd_types(
    path: Annotated[Path | None, typer.Argument(help=_PATH_HELP)] = None,
    fmt: Annotated[str, typer.Option("--format", "-f", help=_FMT_HELP)] = "markdown",
    output: Annotated[str | None, typer.Option("--output", "-o", help=_OUTPUT_HELP)] = None,
    max_tokens: Annotated[int | None, typer.Option("--max-tokens", help=_MAX_TOKENS_HELP)] = None,
) -> None:
    """All TypeScript interfaces and Zod schemas."""
    _emit_context(_project_root(path, fmt), build_types_context, fmt, output, max_tokens)


@context_app.command("full")
def cmd_full(
    path: Annotated[Path | None, typer.Argument(help=_PATH_HELP)] = None,
    fmt: Annotated[str, typer.Option("--format", "-f", help=_FMT_HELP)] = "markdown",
    output: Annotated[str | None, typer.Option("--output", "-o", help=_OUTPUT_HELP)] = None,
    max_tokens: Annotated[int | None, typer.Option("--max-tokens", help=_MAX_TOKENS_HELP)] = None,
    watch: Annotated[bool, typer.Option("--watch", "-w", help=_WATCH_HELP)] = False,
) -> None:
    """Stack + models + routes + types — full AI agent context."""
    root = _project_root(path, fmt)
    if watch:
        _watch_loop(root, build_full_context, fmt, max_tokens, output)
        return
    _emit_context(root, build_full_context, fmt, output, max_tokens)


# ── legacy run_context kept for backward compat ───────────────────────────────


def run_context(
    path: Path,
    json_output: bool = False,
    output_file: str | None = None,
) -> None:
    """Legacy entry point: dump project context (stack only)."""
    fmt = "json" if json_output else "markdown"
    _emit_context(_project_root(path, fmt), build_stack_context, fmt, output_file, None)
