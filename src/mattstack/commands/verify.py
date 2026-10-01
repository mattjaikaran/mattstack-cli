"""Verify command: scope enforcement (design doc §6)."""

from __future__ import annotations

import fnmatch
import os
import subprocess  # nosec B404 # Required CLI subprocess support.
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import typer

from mattstack.utils.console import print_error, print_success

GIT_TIMEOUT = 30

DEFAULT_SCOPE_FILE = "SCOPE.md"


@dataclass
class ScopeResult:
    """Outcome of a scope check over changed files."""

    changed: list[str] = field(default_factory=list)
    in_scope: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)


def parse_scope_file(content: str) -> list[str]:
    """Parse a scope file into path/glob entries (comments and blanks ignored)."""
    entries: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
    return entries


def is_in_scope(file: str, scope: Sequence[str]) -> bool:
    """Return True when ``file`` matches any scope entry.

    A trailing ``/`` means directory-prefix match; otherwise glob, exact, or
    path-prefix matching applies.
    """
    if file == ".." or file.startswith("../") or os.path.isabs(file):
        return False
    for entry in scope:
        entry = entry.strip()
        if not entry:
            continue
        if entry.endswith("/"):
            if file.startswith(entry):
                return True
        elif fnmatch.fnmatch(file, entry) or file == entry or file.startswith(entry + "/"):
            return True
    return False


def verify_scope(changed: Sequence[str], scope: Sequence[str]) -> ScopeResult:
    """Split ``changed`` files into in-scope and out-of-scope buckets."""
    result = ScopeResult(changed=list(changed))
    for file in changed:
        bucket = result.in_scope if is_in_scope(file, scope) else result.out_of_scope
        bucket.append(file)
    return result


class GitError(RuntimeError):
    """Git could not report changes; the scope check must not pass."""


def _git(args: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=GIT_TIMEOUT,
        )
    except FileNotFoundError:
        raise GitError("git is not installed or not on PATH") from None
    except subprocess.TimeoutExpired:
        raise GitError(f"git {args[0]} timed out after {GIT_TIMEOUT}s") from None
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or f"exit code {exc.returncode}"
        raise GitError(f"git {args[0]} failed: {detail}") from None
    return proc.stdout


def repo_root(path: Path) -> Path:
    """Return the top-level directory of the Git work tree containing ``path``."""
    top = _git(["rev-parse", "--show-toplevel"], path).strip()
    if not top:
        raise GitError(f"Not inside a Git work tree: {path}")
    return Path(top).resolve()


def parse_porcelain_z(output: str) -> list[str]:
    """Parse ``git status --porcelain -z`` into repo-root-relative paths.

    Rename and copy records carry the original path as an extra NUL-separated
    field; both the new and the original path count as changed.
    """
    files: list[str] = []
    records = output.split("\0")
    i = 0
    while i < len(records):
        record = records[i]
        i += 1
        if len(record) < 4:
            continue
        status, file = record[:2], record[3:]
        files.append(file)
        if "R" in status or "C" in status:
            if i < len(records) and records[i]:
                files.append(records[i])
            i += 1
    return files


def changed_files(path: Path) -> list[str]:
    """Return changed and untracked files relative to ``path``.

    Files outside ``path`` come back with ``..`` segments so they never match
    scope entries declared for ``path``. Raises ``GitError`` when Git fails.
    """
    path = path.resolve()
    root = repo_root(path)
    output = _git(["status", "--porcelain", "-z", "--untracked-files=all"], root)
    files: list[str] = []
    for file in parse_porcelain_z(output):
        rel = Path(os.path.relpath(root / file, path)).as_posix()
        if rel not in files:
            files.append(rel)
    return files


def run_verify(path: Path, scope_file: Path | None = None) -> None:
    """Enforce that changed files stay within the declared plan scope.

    Scope entries are relative to the plan root ``path``, which may be a
    subdirectory of the Git work tree; changes outside it are out of scope.
    """
    path = path.resolve()
    if not path.is_dir():
        print_error(f"Directory not found: {path}")
        raise typer.Exit(code=1)

    scope_path = scope_file or (path / DEFAULT_SCOPE_FILE)
    if not scope_path.is_absolute():
        scope_path = path / scope_path
    scope_path = scope_path.resolve()
    if not scope_path.is_file():
        print_error(f"Scope file not found: {scope_path}")
        raise typer.Exit(code=1)

    scope = parse_scope_file(scope_path.read_text(encoding="utf-8"))
    if not scope:
        print_error(f"Scope file is empty: {scope_path}")
        raise typer.Exit(code=1)

    try:
        changed = changed_files(path)
    except GitError as exc:
        print_error(f"Scope check failed: {exc}")
        raise typer.Exit(code=1) from None
    result = verify_scope(changed, scope)

    if result.out_of_scope:
        for file in result.out_of_scope:
            print_error(f"Out of scope: {file}")
        print_error(f"{len(result.out_of_scope)} file(s) outside the declared plan scope")
        raise typer.Exit(code=1)

    print_success(f"Scope check passed ({len(result.changed)} changed file(s) in scope)")
