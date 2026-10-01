"""Identify the database a Django project's effective settings point at."""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404 # Required CLI subprocess support.
from dataclasses import dataclass

from mattstack.project import ResolvedProject

_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1", "host.docker.internal"}
_KNOWN_ENGINES = {"postgresql", "postgis", "sqlite3", "spatialite", "mysql", "oracle"}
_TARGET_MARKER = "MATTSTACK_DB_TARGET="
# Runs inside `manage.py shell -c`, so it sees the effective settings module.
# It emits engine, host, port, and name only: never credentials.
TARGET_SCRIPT = (
    "import json\n"
    "from django.conf import settings\n"
    "d = settings.DATABASES.get('default', {})\n"
    f"print({_TARGET_MARKER!r} + json.dumps({{"
    "'engine': str(d.get('ENGINE') or ''), 'host': str(d.get('HOST') or ''), "
    "'port': str(d.get('PORT') or ''), 'name': str(d.get('NAME') or ''), "
    "'debug': bool(settings.DEBUG), 'settings': str(settings.SETTINGS_MODULE or '')}))\n"
)
_PROD_SETTINGS = re.compile(r"(^|[._])prod(uction)?($|[._])", re.IGNORECASE)


@dataclass(frozen=True)
class DbTarget:
    """Database that Django's effective settings point at (no credentials)."""

    engine: str
    host: str
    port: str
    name: str
    debug: bool
    settings: str

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.engine

    @property
    def label(self) -> str:
        engine = self.engine.rsplit(".", 1)[-1] or "database"
        if self.is_sqlite:
            return f"{engine} {self.name}"
        return f"{engine} {self.host or 'localhost'}:{self.port or 'default'}/{self.name}"

    @property
    def is_local(self) -> bool:
        host = self.host.strip().lower()
        return (
            self.is_sqlite
            or host in _LOCAL_HOSTS
            or host.startswith("/")
            or host.endswith((".localhost", ".orb.local"))
        )

    @property
    def is_production(self) -> bool:
        return not self.debug or bool(_PROD_SETTINGS.search(self.settings))


def inspect_target(project: ResolvedProject) -> DbTarget | None:
    """Read the default database from Django's effective settings, or None."""
    try:
        result = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
            ["uv", "run", "python", "manage.py", "shell", "-c", TARGET_SCRIPT],
            cwd=project.backend_dir,
            env=project.env,
            text=True,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in reversed(result.stdout.splitlines()):
        if line.startswith(_TARGET_MARKER):
            try:
                data = json.loads(line[len(_TARGET_MARKER) :])
                target = DbTarget(
                    engine=str(data["engine"]),
                    host=str(data["host"]),
                    port=str(data["port"]),
                    name=str(data["name"]),
                    debug=bool(data["debug"]),
                    settings=str(data["settings"]),
                )
            except (ValueError, KeyError, TypeError):
                return None
            # An unrecognised engine or a missing name is not a verified target.
            known = target.engine.rsplit(".", 1)[-1] in _KNOWN_ENGINES
            return target if known and target.name.strip() else None
    return None
