"""Typer CLI app for mattstack."""

from __future__ import annotations

from typing import Annotated

import typer

from mattstack.cli_project import register_project_commands
from mattstack.cli_scaffold import register_scaffold_commands
from mattstack.commands.client import client_app
from mattstack.commands.context import context_app

app = typer.Typer(
    name="mattstack",
    help="Scaffold fullstack monorepos from battle-tested boilerplates.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

app.add_typer(client_app, name="client")
app.add_typer(context_app, name="context")


def _register_subgroups() -> None:
    """Register command subgroups."""
    from mattstack.commands.board import board_app
    from mattstack.commands.db import db_app
    from mattstack.commands.deps import deps_app
    from mattstack.commands.generate import generate_app
    from mattstack.commands.hooks import hooks_app
    from mattstack.commands.rules import rules_app
    from mattstack.commands.sync import sync_app
    from mattstack.commands.todo import todo_app

    app.add_typer(generate_app, name="generate")
    app.add_typer(db_app, name="db")
    app.add_typer(sync_app, name="sync")
    from mattstack.commands.openapi import sync_openapi

    sync_app.command("openapi")(sync_openapi)
    app.add_typer(deps_app, name="deps")
    app.add_typer(hooks_app, name="hooks")
    app.add_typer(board_app, name="board")
    app.add_typer(todo_app, name="todo")
    app.add_typer(rules_app, name="rules")


_register_subgroups()


@app.callback()
def main(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output"),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress non-essential output"),
    ] = False,
) -> None:
    """Scaffold fullstack monorepos from battle-tested boilerplates."""
    from mattstack.utils.console import set_quiet, set_verbose

    set_verbose(verbose)
    set_quiet(quiet)


register_scaffold_commands(app)
register_project_commands(app)


if __name__ == "__main__":
    app()
