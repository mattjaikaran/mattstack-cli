"""Board command: pluggable kanban board (design doc §2)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from mattstack.boards import get_board_backend
from mattstack.boards.base import BoardBackend
from mattstack.commands.todo import read_open_tasks
from mattstack.config_file import MattstackConfig, load_config
from mattstack.utils.console import console, print_info, print_success

board_app = typer.Typer(
    name="board",
    help="Pluggable kanban board (create, list, claim, transition, link-pr, sync).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _load_backend(path: Path) -> tuple[MattstackConfig, BoardBackend]:
    config = load_config(path / "mattstack.yml")
    return config, get_board_backend(config.board)


def sync_open_tasks(backend: BoardBackend, path: Path, project: str) -> int:
    """Push open tasks from tasks/todo.md into ``backend``. Returns the count."""
    tasks = read_open_tasks(path)
    for title in tasks:
        backend.create_task(title, project=project)
    return len(tasks)


@board_app.command("create")
def create(
    title: Annotated[str, typer.Argument(help="Task title")],
    project: Annotated[str | None, typer.Option("--project", "-p", help="Board project")] = None,
    path: Annotated[Path | None, typer.Option("--path", help="Project path")] = None,
) -> None:
    """Create a task on the configured board."""
    config, backend = _load_backend(path or Path.cwd())
    result = backend.create_task(title, project=project or config.board.project_slug)
    print_success("Task created")
    console.print_json(data=result)


@board_app.command("list")
def list_tasks_cmd(
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Filter by project")
    ] = None,
    status: Annotated[str | None, typer.Option("--status", "-s", help="Filter by status")] = None,
    path: Annotated[Path | None, typer.Option("--path", help="Project path")] = None,
) -> None:
    """List tasks from the configured board."""
    _config, backend = _load_backend(path or Path.cwd())
    filters: dict[str, Any] = {}
    if project:
        filters["project"] = project
    if status:
        filters["status"] = status
    console.print_json(data=backend.list_tasks(**filters))


@board_app.command("claim")
def claim(
    task_id: Annotated[str, typer.Argument(help="Task id to claim")],
    agent: Annotated[str, typer.Option("--agent", "-a", help="Agent name")] = "mattstack",
    path: Annotated[Path | None, typer.Option("--path", help="Project path")] = None,
) -> None:
    """Claim a task for an agent."""
    _config, backend = _load_backend(path or Path.cwd())
    result = backend.claim_task(task_id, agent)
    print_success(f"Claimed task {task_id}")
    console.print_json(data=result)


@board_app.command("transition")
def transition(
    task_id: Annotated[str, typer.Argument(help="Task id to transition")],
    status: Annotated[str, typer.Option("--status", "-s", help="Target status")],
    comment: Annotated[str, typer.Option("--comment", "-c", help="Transition comment")] = "",
    path: Annotated[Path | None, typer.Option("--path", help="Project path")] = None,
) -> None:
    """Transition a task to a new status."""
    _config, backend = _load_backend(path or Path.cwd())
    result = backend.transition_task(task_id, status, comment=comment)
    print_success(f"Transitioned task {task_id} to {status}")
    console.print_json(data=result)


@board_app.command("link-pr")
def link_pr(
    task_id: Annotated[str, typer.Argument(help="Task id to link")],
    pr_url: Annotated[str, typer.Argument(help="Pull-request URL")],
    pr_number: Annotated[
        int | None, typer.Option("--pr-number", help="Pull-request number")
    ] = None,
    path: Annotated[Path | None, typer.Option("--path", help="Project path")] = None,
) -> None:
    """Link a pull request to a task."""
    _config, backend = _load_backend(path or Path.cwd())
    result = backend.link_pr(task_id, pr_url, pr_number=pr_number)
    print_success(f"Linked PR to task {task_id}")
    console.print_json(data=result)


@board_app.command("sync")
def sync(
    project: Annotated[str | None, typer.Option("--project", "-p", help="Board project")] = None,
    path: Annotated[Path | None, typer.Option("--path", help="Project path")] = None,
) -> None:
    """Push open tasks from tasks/todo.md into the configured board."""
    root = (path or Path.cwd()).resolve()
    config, backend = _load_backend(root)
    count = sync_open_tasks(backend, root, project or config.board.project_slug)
    if count == 0:
        print_info("No open tasks in tasks/todo.md")
    else:
        print_success(f"Synced {count} task(s) to the board")
