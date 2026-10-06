"""Env command: environment variable management for .env files."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.markup import escape

from mattstack.project import find_project_root, parse_env_file
from mattstack.stack import load_stack
from mattstack.utils.console import console, create_table, print_error, print_info, print_success
from mattstack.utils.env_secrets import (
    BACKEND_SCRIPT,
    SecretsScriptError,
    fill_secrets,
    run_backend_script,
    write_private_file,
)


def _frontend_env_file(frontend: Path) -> Path:
    """Return the frontend env file in use: .env.local, else .env, else .env.local."""
    for name in (".env.local", ".env"):
        if (frontend / name).exists():
            return frontend / name
    return frontend / ".env.local"


def _find_env_pairs(path: Path) -> list[tuple[Path, Path]]:
    """Find (example, actual) pairs: .env.example -> .env, etc."""
    pairs: list[tuple[Path, Path]] = []
    frontend = path / "frontend"
    candidates = [
        (path / ".env.example", path / ".env"),
        (path / "backend" / ".env.example", path / "backend" / ".env"),
        (frontend / ".env.example", _frontend_env_file(frontend)),
    ]
    for example_path, actual_path in candidates:
        if example_path.exists():
            pairs.append((example_path, actual_path))
    return pairs


def _mask_value(value: str) -> str:
    """Mask value: show first 3 chars + ***; an empty value shows as (empty)."""
    if not value:
        return "(empty)"
    if len(value) <= 3:
        return "*" * len(value)
    return value[:3] + "***"


def run_env_check(path: Path) -> None:
    """Compare .env.example vs .env; exit 1 when any example variable is missing."""
    path = path.resolve()
    if not path.is_dir():
        print_error(f"Directory not found: {path}")
        raise typer.Exit(code=1)

    pairs = _find_env_pairs(path)
    if not pairs:
        print_info("No .env.example files found.")
        return

    console.print()
    console.print("[bold cyan]mattstack env check[/bold cyan]")
    console.print()

    any_missing = False
    for example_path, actual_path in pairs:
        rel_ex = example_path.relative_to(path)
        rel_act = actual_path.relative_to(path)
        example_vars = parse_env_file(example_path)
        actual_vars = parse_env_file(actual_path)

        missing = [k for k in example_vars if k not in actual_vars]
        empty = [k for k in example_vars if actual_vars.get(k) == ""]
        extra = [k for k in actual_vars if k not in example_vars]

        if not missing and not empty and not extra:
            print_success(f"{rel_ex} ↔ {rel_act}: OK (all vars present, no extras)")
            continue

        any_missing = any_missing or bool(missing)
        table = create_table(f"{rel_ex} vs {rel_act}", ["Type", "Variables"])
        if missing:
            table.add_row(f"[red]Missing in {rel_act}[/red]", ", ".join(missing))
        if empty:
            table.add_row(f"[yellow]Empty in {rel_act}[/yellow]", ", ".join(empty))
        if extra:
            table.add_row(f"[dim]Extra in {rel_act}[/dim]", ", ".join(extra))
        console.print(table)
        console.print()

    if any_missing:
        print_error("Missing variables. Run 'mattstack env sync' to copy them from .env.example")
        raise typer.Exit(code=1)
    print_success("No variables missing")


def run_env_sync(path: Path) -> None:
    """Append missing vars to .env, copying each default from .env.example."""
    path = path.resolve()
    if not path.is_dir():
        print_error(f"Directory not found: {path}")
        raise typer.Exit(code=1)

    pairs = _find_env_pairs(path)
    if not pairs:
        print_info("No .env.example files found.")
        return

    console.print()
    console.print("[bold cyan]mattstack env sync[/bold cyan]")
    console.print()

    for example_path, actual_path in pairs:
        example_vars = parse_env_file(example_path)
        actual_vars = parse_env_file(actual_path)
        missing = [k for k in example_vars if k not in actual_vars]

        if not missing:
            print_info(f"{actual_path.relative_to(path)}: already in sync")
            continue

        # Build new content: keep existing, add missing with default/empty
        lines: list[str] = (
            actual_path.read_text(encoding="utf-8").splitlines() if actual_path.exists() else []
        )

        # Add missing vars
        for key in missing:
            default = example_vars.get(key, "")
            lines.append(f"{key}={default}")

        actual_path.parent.mkdir(parents=True, exist_ok=True)
        actual_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print_success(f"{actual_path.relative_to(path)}: added {len(missing)} vars")


def run_env_secrets(path: Path) -> None:
    """Create missing root .env files from their examples with generated secrets.

    Each file gets mode 0600. Existing files stay unchanged; only names print.
    A backend with ``scripts/env_secrets.py`` generates them itself.
    """
    console.print()
    console.print("[bold cyan]mattstack env secrets[/bold cyan]")
    console.print()
    stack = load_stack(path)
    backend = stack.project.backend_dir
    ninja = stack.has_backend and stack.config().is_ninja_backend
    delegate = ninja or (backend / BACKEND_SCRIPT).is_file()
    found = False
    for name in (".env", ".env.production"):
        example = path / f"{name}.example"
        if not example.is_file():
            continue
        found = True
        if (path / name).exists():
            print_info(f"Kept existing {name}; generated no new secrets")
        elif delegate:
            try:
                print_success(f"{name}: {run_backend_script(backend, path / name, example)}")
            except SecretsScriptError as exc:
                print_error(str(exc))
                raise typer.Exit(code=1) from exc
        else:
            content, names = fill_secrets(example.read_text(encoding="utf-8"))
            write_private_file(path / name, content)
            print_success(f"Created {name} (mode 0600): {', '.join(names) or 'no secrets'}")
    if not found:
        print_error(f"No .env.example or .env.production.example in {path}")
        raise typer.Exit(code=1)


def run_env_show(path: Path) -> None:
    """Show current .env vars with values masked."""
    path = path.resolve()
    if not path.is_dir():
        print_error(f"Directory not found: {path}")
        raise typer.Exit(code=1)

    env_files = [
        path / ".env",
        path / "backend" / ".env",
        path / "frontend" / ".env.local",
        path / "frontend" / ".env",
    ]

    console.print()
    console.print("[bold cyan]mattstack env show[/bold cyan]")
    console.print()

    found_any = False
    for env_path in env_files:
        if not env_path.exists():
            continue
        found_any = True
        vars_dict = parse_env_file(env_path)
        table = create_table(str(env_path.relative_to(path)), ["Variable", "Value (masked)"])
        for k, v in sorted(vars_dict.items()):
            table.add_row(k, escape(_mask_value(v)))
        console.print(table)
        console.print()

    if not found_any:
        print_info("No .env files found.")


def run_env(
    action: str,
    path: Path,
) -> None:
    """Dispatch to check, sync, show, or secrets for the project that contains ``path``."""
    action = action.lower().strip()
    if action not in ("check", "sync", "show", "secrets"):
        print_error(f"Unknown action: {action}. Use: check, sync, show, secrets")
        raise typer.Exit(code=1)
    if path.is_dir():
        path = find_project_root(path)
    if action == "check":
        run_env_check(path)
    elif action == "sync":
        run_env_sync(path)
    elif action == "secrets":
        run_env_secrets(path)
    else:
        run_env_show(path)
