"""Generate per-environment secrets for a project's gitignored env files.

The django-ninja backend owns its secret list in ``scripts/env_secrets.py``,
so ``mattstack init`` runs the cloned backend's script for ``.env`` and,
separately, ``.env.production``; mattstack keeps no second copy of that list.
For backends without the script (FastAPI, NestJS, django-matt), mattstack
generates the few values those backends read. The committed ``.env.example``
files keep every name with an empty value. No function prints a value.
"""

from __future__ import annotations

import os
import secrets
import string
import subprocess  # nosec B404 # Runs the cloned backend's own stdlib script.
import sys
from pathlib import Path

from mattstack.config import ProjectConfig

_KEY = "key"
_PASSWORD = "password"  # nosec B105 # Secret kind label, not a credential.
# Letters and digits only, as the backend's docs/ENV_SECRETS.md requires: no
# character needs quoting in .env, a redis:// URL, or a shell argument.
_ALPHABET = string.ascii_letters + string.digits
BACKEND_SCRIPT = Path("scripts") / "env_secrets.py"


class SecretsScriptError(OSError):
    """The backend's secret script is missing or failed; init must stop."""


def delegates_secrets(config: ProjectConfig) -> bool:
    """Return whether the backend's own script generates the secrets."""
    return config.has_backend and config.is_ninja_backend


def secret_names(config: ProjectConfig) -> dict[str, str]:
    """Return ``{name: kind}`` that mattstack generates itself (non-Ninja backends)."""
    if not config.has_backend or delegates_secrets(config):
        return {}
    names = {"DB_PASSWORD": _PASSWORD}
    if config.use_redis:
        names["REDIS_PASSWORD"] = _PASSWORD
    if config.is_nestjs_backend:
        names.update({"JWT_SECRET": _KEY, "JWT_REFRESH_SECRET": _KEY})
        return names
    names["SECRET_KEY"] = _KEY
    if config.is_fastapi_backend:
        names["JWT_SECRET_KEY"] = _KEY
    return names


def run_backend_script(backend_dir: Path, env_file: Path, template: Path) -> str:
    """Create ``env_file`` (mode 0600) with the backend script; return its summary.

    Raise ``SecretsScriptError`` with the exit code when the script is missing
    or fails. The script prints names only.
    """
    script = backend_dir / BACKEND_SCRIPT
    if not script.is_file():
        raise SecretsScriptError(
            f"{script} is missing; this django-ninja backend cannot generate its "
            "secrets. Update django-ninja-boilerplate (docs/ENV_SECRETS.md)."
        )
    command = [sys.executable, str(script), "create", "--root", str(backend_dir)]
    command += ["--env-file", str(env_file), "--template", str(template)]
    result = subprocess.run(  # nosec B603 # Argv; the cloned backend's own script.
        command, cwd=backend_dir, capture_output=True, text=True, check=False
    )
    if result.returncode != 0 or not env_file.is_file():
        detail = (result.stderr or result.stdout).strip()
        raise SecretsScriptError(
            f"{BACKEND_SCRIPT} create --env-file {env_file.name} exited "
            f"{result.returncode}: {detail}"
        )
    env_file.chmod(0o600)
    return result.stdout.strip()


def generate_secrets(config: ProjectConfig) -> dict[str, str]:
    """Return a fresh, distinct value for every name in ``secret_names``."""
    return {name: _new(kind) for name, kind in secret_names(config).items()}


def fill_secrets(example: str) -> tuple[str, list[str]]:
    """Fill every empty known secret in an env example; return the text and the names."""
    filled: list[str] = []
    lines = []
    for line in example.splitlines():
        name, sep, value = line.partition("=")
        if sep and not value.strip() and name.strip() in _ALL_KINDS:
            filled.append(name.strip())
            line = f"{name}={_new(_ALL_KINDS[name.strip()])}"
        lines.append(line)
    return "\n".join(lines) + "\n", filled


def _new(kind: str) -> str:
    length = 64 if kind == _KEY else 32
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


# Secrets of the backends that ship no script of their own.
_ALL_KINDS = {
    "DB_PASSWORD": _PASSWORD,
    "REDIS_PASSWORD": _PASSWORD,
    "SECRET_KEY": _KEY,
    "JWT_SECRET": _KEY,
    "JWT_REFRESH_SECRET": _KEY,
    "JWT_SECRET_KEY": _KEY,
}


def write_private_file(path: Path, content: str) -> bool:
    """Create ``path`` with mode 0600; return False and keep it if it exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
    os.chmod(path, 0o600)  # The umask cannot widen it, but make the mode explicit.
    return True
