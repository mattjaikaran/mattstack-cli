"""Typer CLI app for mattstack.

Subcommand groups load on first use. The root help lists them from
``LAZY_GROUPS`` without importing their modules, so `mattstack --help` and
root commands skip the cost of every group's dependencies.
"""

from __future__ import annotations

import importlib
from difflib import get_close_matches
from typing import Annotated, Any, NamedTuple

import click
import typer
from typer.core import TyperGroup

from mattstack.cli_project import register_project_commands
from mattstack.cli_scaffold import register_scaffold_commands


class LazyGroupSpec(NamedTuple):
    """Where a subcommand group lives, and its one-line summary for the root help."""

    module: str
    attr: str
    short_help: str


LAZY_GROUPS: dict[str, LazyGroupSpec] = {
    "client": LazyGroupSpec(
        "mattstack.commands.client", "client_app", "Frontend package manager commands."
    ),
    "context": LazyGroupSpec(
        "mattstack.commands.context", "context_app", "Dump project context for AI agents."
    ),
    "generate": LazyGroupSpec(
        "mattstack.commands.generate",
        "generate_app",
        "Scaffold models, endpoints, components, pages, hooks, and schemas.",
    ),
    "db": LazyGroupSpec("mattstack.commands.db", "db_app", "Database management (Django)."),
    "sync": LazyGroupSpec(
        "mattstack.commands.sync",
        "sync_app",
        "Generate the frontend client from the backend OpenAPI contract.",
    ),
    "deps": LazyGroupSpec(
        "mattstack.commands.deps", "deps_app", "Check, update, and audit dependencies."
    ),
    "hooks": LazyGroupSpec(
        "mattstack.commands.hooks", "hooks_app", "Install, check, and run git hooks."
    ),
    "board": LazyGroupSpec("mattstack.commands.board", "board_app", "Pluggable kanban board."),
    "todo": LazyGroupSpec(
        "mattstack.commands.todo", "todo_app", "Task SSOT: archive checked items, sync to board."
    ),
    "rules": LazyGroupSpec(
        "mattstack.commands.rules", "rules_app", "Generate AI agent files and harness adapters."
    ),
}


class LazyTyperGroup(TyperGroup):
    """Root group that imports a subcommand group only when it runs or completes."""

    def __init__(self, **attrs: Any) -> None:
        super().__init__(**attrs)
        self._listing_help = False

    def list_commands(self, ctx: click.Context) -> list[str]:
        return [*super().list_commands(ctx), *(n for n in LAZY_GROUPS if n not in self.commands)]

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        spec = LAZY_GROUPS.get(cmd_name)
        if spec is None or cmd_name in self.commands:
            return super().get_command(ctx, cmd_name)
        if self._listing_help:
            return click.Group(name=cmd_name, short_help=spec.short_help)
        group = typer.main.get_group(getattr(importlib.import_module(spec.module), spec.attr))
        group.name, group.short_help = cmd_name, spec.short_help
        self.commands[cmd_name] = group
        return group

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as exc:
            # TyperGroup suggests only loaded commands; include the lazy groups.
            matches = get_close_matches(args[0], self.list_commands(ctx)) if args else []
            if not matches or "Did you mean" in exc.message:
                raise
            suggestions = ", ".join(repr(match) for match in matches)
            message = f"{exc.message.rstrip('.')}. Did you mean {suggestions}?"
            raise click.UsageError(message, ctx=exc.ctx) from None

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        self._listing_help = True
        try:
            super().format_help(ctx, formatter)
        finally:
            self._listing_help = False


app = typer.Typer(
    name="mattstack",
    cls=LazyTyperGroup,
    help="Scaffold fullstack monorepos from battle-tested boilerplates.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


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
