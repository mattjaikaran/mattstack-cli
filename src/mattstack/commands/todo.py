"""Todo command: task SSOT (tasks/todo.md -> tasks/completed.md)."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from mattstack.utils.console import print_error, print_success

todo_app = typer.Typer(
    name="todo",
    help="Task SSOT: move checked items to completed, sync to board.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

TODO_FILE = "tasks/todo.md"
COMPLETED_FILE = "tasks/completed.md"

_CHECK_RE = re.compile(r"^\s*-\s+\[( |x|X)\]\s+(.+?)\s*$")


@dataclass
class TodoItem:
    """A markdown checklist item parsed from todo.md."""

    text: str
    checked: bool
    raw_line: str


def parse_todo_items(content: str) -> list[TodoItem]:
    """Parse ``- [ ]`` / ``- [x]`` checklist lines from todo.md content."""
    items: list[TodoItem] = []
    for line in content.splitlines():
        match = _CHECK_RE.match(line)
        if match:
            items.append(
                TodoItem(
                    text=match.group(2),
                    checked=match.group(1).lower() == "x",
                    raw_line=line,
                )
            )
    return items


def open_todo_items(content: str) -> list[str]:
    """Return the text of every unchecked item."""
    return [item.text for item in parse_todo_items(content) if not item.checked]


def read_open_tasks(path: Path) -> list[str]:
    """Read unchecked task titles from ``<path>/tasks/todo.md``."""
    todo = path / TODO_FILE
    if not todo.exists():
        return []
    return open_todo_items(todo.read_text(encoding="utf-8"))


def get_commit_sha(path: Path) -> str:
    """Return the short HEAD commit SHA, or ``unknown`` outside a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
    return result.stdout.strip()


def move_item(
    todo_path: Path,
    completed_path: Path,
    needle: str,
    today: date,
    sha: str,
) -> str:
    """Move the checked item matching ``needle`` from todo.md to completed.md.

    Raises :class:`ValueError` when no item matches or the match is not
    checked. Returns the moved item text.
    """
    content = todo_path.read_text(encoding="utf-8") if todo_path.exists() else ""
    lines = content.splitlines()

    target_index: int | None = None
    item_text = ""
    for index, line in enumerate(lines):
        match = _CHECK_RE.match(line)
        if not match or needle not in match.group(2):
            continue
        if match.group(1).lower() != "x":
            raise ValueError(f"Todo item {match.group(2)!r} is not checked; check it before moving")
        target_index = index
        item_text = match.group(2)
        break

    if target_index is None:
        raise ValueError(f"No todo item matches {needle!r}")

    del lines[target_index]
    while lines and not lines[-1].strip():
        lines.pop()
    todo_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    entry = f"- {item_text} ({today.isoformat()} · {sha})"
    existing = completed_path.read_text(encoding="utf-8") if completed_path.exists() else ""
    completed_path.parent.mkdir(parents=True, exist_ok=True)
    if existing.strip():
        completed_path.write_text(existing.rstrip("\n") + "\n" + entry + "\n", encoding="utf-8")
    else:
        completed_path.write_text(entry + "\n", encoding="utf-8")

    return item_text


@todo_app.command("move")
def move(
    item: Annotated[str, typer.Argument(help="Substring matching the checked todo item")],
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
) -> None:
    """Move a checked item from todo.md to completed.md."""
    root = (path or Path.cwd()).resolve()
    try:
        text = move_item(
            root / TODO_FILE,
            root / COMPLETED_FILE,
            item,
            today=date.today(),
            sha=get_commit_sha(root),
        )
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(code=1) from None
    print_success(f"Moved to completed: {text}")
