"""Gauntlet pass-through: run the verification engine directly.

This group lets you run Gauntlet without knowing the binary path. It reads
`binary_path` from the project's `gauntlet.toml` and forwards the exit code
unchanged, so a CI job still sees code 2 for a blocking failure.

Unknown options pass through to Gauntlet, so `mattstack gauntlet check
--offline` and `mattstack gauntlet run vault show X` both work.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Annotated

import typer

from mattstack.gauntlet.client import DEFAULT_TIER, load_config, resolve_binary
from mattstack.gauntlet.report import install_instructions
from mattstack.utils.console import print_error, print_verbose

# Let every option that mattstack does not declare reach Gauntlet.
PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}

gauntlet_app = typer.Typer(
    name="gauntlet",
    help="Run Gauntlet, the verification engine, against this project.",
    no_args_is_help=True,
    add_completion=False,
)


@gauntlet_app.command("check", context_settings=PASSTHROUGH)
def check_cmd(
    ctx: typer.Context,
    path: Annotated[
        Path,
        typer.Option("--path", "-C", help="Project directory (default: current)"),
    ] = Path(),
    tier: Annotated[
        str,
        typer.Option("--tier", help="Tier to run: fast, standard, full, release"),
    ] = DEFAULT_TIER,
) -> None:
    """Run `gauntlet check` with this project's configuration."""
    _exec(path, ["check", f"--tier={tier}", *ctx.args])


@gauntlet_app.command("run", context_settings=PASSTHROUGH)
def run_cmd(
    ctx: typer.Context,
    path: Annotated[
        Path,
        typer.Option("--path", "-C", help="Project directory (default: current)"),
    ] = Path(),
) -> None:
    """Run any Gauntlet subcommand, for example `mattstack gauntlet run vault show X`."""
    args = list(ctx.args)
    if not args:
        print_error("Pass a Gauntlet subcommand, for example: mattstack gauntlet run vault show")
        raise typer.Exit(code=1)
    _exec(path, args)


def _exec(path: Path, argv: list[str]) -> None:
    """Run Gauntlet in ``path`` and exit with its status code."""
    project_path = path.resolve()
    if not project_path.is_dir():
        print_error(f"Not a directory: {project_path}")
        raise typer.Exit(code=1)

    settings = load_config(project_path)
    binary = resolve_binary(settings, project_path)
    if binary is None:
        print_error(install_instructions(settings.binary_path))
        raise typer.Exit(code=1)

    command = [binary, *argv]
    print_verbose(f"Running: {' '.join(command)}")
    try:
        completed = subprocess.run(command, cwd=project_path, check=False)  # noqa: S603
    except OSError as exc:
        print_error(f"Could not run Gauntlet: {exc}")
        raise typer.Exit(code=1) from exc

    raise typer.Exit(code=completed.returncode)
