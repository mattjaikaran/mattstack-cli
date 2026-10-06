"""`mattstack sync`: the frontend API client comes from the backend OpenAPI contract."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from mattstack.commands.openapi import sync_check, sync_openapi
from mattstack.utils.console import print_warning

sync_app = typer.Typer(
    name="sync",
    help="Generate the frontend client (types, SDK, Zod, TanStack Query) from the backend "
    "OpenAPI contract. Without a subcommand, run `sync openapi`.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)


@sync_app.callback()
def sync_default(ctx: typer.Context) -> None:
    """Run `sync openapi` in the current directory when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        sync_openapi()


sync_app.command("openapi")(sync_openapi)
sync_app.command("check")(sync_check)


def _deprecated_alias(name: str) -> Callable[[Path | None], None]:
    def alias(
        path: Annotated[Path | None, typer.Option("--path", "-p", help="Project root")] = None,
    ) -> None:
        print_warning(f"`mattstack sync {name}` is deprecated; running `mattstack sync openapi`")
        sync_openapi(path=path)

    alias.__doc__ = "Deprecated: runs `mattstack sync openapi`."
    return alias


for _name in ("types", "zod", "api-client", "all"):
    sync_app.command(_name, deprecated=True)(_deprecated_alias(_name))
