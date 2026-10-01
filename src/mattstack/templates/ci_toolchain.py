"""Shared pieces of generated CI: JavaScript toolchain, quoting, backend env.

`mattstack workflow` reads the committed lockfile, so CI uses the package
manager the project already chose. A project without a lockfile keeps the
scaffold default, Bun. Component directories come from mattstack.yml, so
every path is quoted for both the shell and YAML.
"""

from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from mattstack.templates.stack_facts import BackendFacts
from mattstack.utils.package_manager import LOCKFILE_MAP, PackageManager


def yaml_str(value: str) -> str:
    """Return ``value`` as a YAML double-quoted scalar (JSON strings are valid YAML)."""
    return json.dumps(value)


def in_dir(directory: str, command: str) -> str:
    """Return a shell command that runs ``command`` inside ``directory``."""
    return f"cd {shlex.quote(directory)} && {command}"


def backend_test_env(backend: BackendFacts, db_host: str, redis_host: str) -> dict[str, str]:
    """Return the environment a Python backend's test job needs.

    Django settings read the ``DB_*`` parts; FastAPI reads ``DATABASE_URL``.
    """
    env = {
        "DATABASE_URL": f"{backend.database_scheme}://postgres:postgres@{db_host}:5432/test_db",
        "REDIS_URL": f"redis://{redis_host}:6379/0",
    }
    if backend.db_env_parts:
        env.update(
            {
                "DB_NAME": "test_db",
                "DB_USER": "postgres",
                "DB_PASSWORD": "postgres",
                "DB_HOST": db_host,
                "DB_PORT": "5432",
            }
        )
    return env


def yaml_mapping(values: dict[str, str], indent: int) -> str:
    """Render ``values`` as YAML mapping lines with every value quoted."""
    pad = " " * indent
    return "\n".join(f"{pad}{key}: {yaml_str(value)}" for key, value in values.items())


@dataclass(frozen=True)
class JsCi:
    """How CI installs and runs one JavaScript component."""

    pm: PackageManager
    install: str

    def run(self, command: str) -> str:
        """Translate a Bun command from frontend_commands to this package manager."""
        if self.pm == PackageManager.BUN:
            return command
        if command.startswith("bun run "):
            return f"{self.pm.value} run {command.removeprefix('bun run ')}"
        if command.startswith("bunx "):
            local_bin = {
                PackageManager.NPM: "npx",
                PackageManager.PNPM: "pnpm exec",
                PackageManager.YARN: "yarn",
            }[self.pm]
            return f"{local_bin} {command.removeprefix('bunx ')}"
        return command


@dataclass(frozen=True)
class CiLayout:
    """Where the project keeps its components, as root-relative CI paths."""

    root: Path
    backend: Path
    frontend: Path

    def rel(self, component_dir: Path) -> str:
        """Return ``component_dir`` relative to the root ('.' for the root itself)."""
        return component_dir.relative_to(self.root).as_posix()


def _lockfile(component_dir: Path, root: Path) -> tuple[PackageManager, Path] | None:
    """Return the lockfile in ``component_dir`` or, for a workspace, at ``root``."""
    for directory in dict.fromkeys((component_dir, root)):
        for name, pm in LOCKFILE_MAP.items():
            if (directory / name).is_file():
                return pm, directory / name
    return None


def js_ci(component_dir: Path, root: Path) -> JsCi:
    """Resolve CI install for ``component_dir`` from its committed lockfile.

    A user default package manager does not apply: CI can only use what the
    repository records. Without a lockfile, keep Bun.
    """
    found = _lockfile(component_dir, root)
    if found is None or found[0] == PackageManager.BUN:
        return JsCi(PackageManager.BUN, "bun install --frozen-lockfile")
    pm, lockfile = found
    if pm == PackageManager.NPM:
        install = "npm ci"
    elif pm == PackageManager.PNPM:
        install = "pnpm install --frozen-lockfile"
    elif (lockfile.parent / ".yarnrc.yml").exists():
        install = "yarn install --immutable"
    else:
        install = "yarn install --frozen-lockfile"
    if lockfile.parent == component_dir:
        return JsCi(pm, install)
    # A workspace lockfile lives at the repository root. The subshell keeps
    # the job's working directory on the component for the commands after it.
    up = os.path.relpath(lockfile.parent, component_dir)
    return JsCi(pm, f"({in_dir(up, install)})")


def github_js_setup(js: JsCi) -> str:
    """Return the GitHub Actions steps that provide ``js.pm``."""
    if js.pm == PackageManager.BUN:
        return """      - uses: oven-sh/setup-bun@v2
        with:
          bun-version: latest"""
    setup = """      - uses: actions/setup-node@v4
        with:
          node-version: 22"""
    if js.pm in (PackageManager.PNPM, PackageManager.YARN):
        setup += "\n      - run: corepack enable"
    return setup
