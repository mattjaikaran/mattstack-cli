"""Root pre-commit configuration for generated projects.

Consolidation removes each component's own ``.pre-commit-config.yaml``, because
git runs hooks from one config at the repository root. The root config replaces
them: every hook that runs a component tool changes into that component first,
so the tool reads the component's own configuration and locked version.

Which component tools survive:

- Django Ninja: the backend's locked ruff (lint with fixes, then format) on
  commit, and ``just gauntlet-quick`` on push. The quick gauntlet runs the
  backend's mypy, bandit, convention, dependency, architecture, file-length,
  and pytest checks. The root config does not carry over the backend's djhtml,
  hadolint, shellcheck, YAML/JSON prettier, commit-message, or pip-audit hooks;
  run ``cd backend && just gauntlet`` for pip-audit.
- Other Python backends: ``uv run ruff`` inside ``backend/``, so the hook uses
  the version the backend's lockfile resolves instead of a pinned mirror.
- NestJS: the backend's own ``lint`` script (Biome).
- React frontends: locked Oxlint and Oxfmt scripts; Next.js: its own lint script.
"""

from __future__ import annotations

import json

from mattstack.config import BackendFramework, ProjectConfig

# Tools that generated local hooks run, with the command that installs each.
# `mattstack hooks install` checks these before it installs any hook.
HOOK_PREREQUISITES: dict[str, str] = {
    "uv": "curl -LsSf https://astral.sh/uv/install.sh | sh",
    "just": "uv tool install rust-just",
    "bun": "curl -fsSL https://bun.sh/install | bash",
}

# `--extra dev` installs the locked ruff; plain `uv run ruff` in a fresh clone
# falls back to whatever ruff is on PATH.
_NINJA_RUFF = (
    "cd backend && uv run --extra dev ruff check --fix --exit-non-zero-on-fix . "
    "&& uv run --extra dev ruff format ."
)
_NINJA_GAUNTLET = (
    "command -v just >/dev/null || "
    '{ echo "backend-gauntlet-quick needs just: uv tool install rust-just" >&2; exit 1; }; '
    "command -v uv >/dev/null || "
    '{ echo "backend-gauntlet-quick needs uv: '
    'curl -LsSf https://astral.sh/uv/install.sh | sh" >&2; exit 1; }; '
    "cd backend && uv run --extra dev just gauntlet-quick"
)
# Other Python backends: the ruff their lockfile resolves, never a mirror pin.
_PROJECT_RUFF = (
    "cd backend && uv run ruff check --fix --exit-non-zero-on-fix . && uv run ruff format ."
)


def _entry(script: str) -> str:
    """Return a ``bash -c`` entry as a quoted scalar; JSON strings are valid YAML."""
    return json.dumps(f"bash -c '{script}'")


def _backend_hooks(config: ProjectConfig) -> str:
    if config.backend_framework == BackendFramework.DJANGO_NINJA:
        return f"""\
  - repo: local
    hooks:
      - id: backend-ruff
        name: backend ruff (locked version)
        entry: {_entry(_NINJA_RUFF)}
        language: system
        files: ^backend/.*\\.pyi?$
        pass_filenames: false
      - id: backend-gauntlet-quick
        name: backend gauntlet-quick
        entry: {_entry(_NINJA_GAUNTLET)}
        language: system
        files: ^backend/
        pass_filenames: false
        stages: [pre-push]"""
    if config.backend_framework == BackendFramework.NESTJS:
        return """\
  - repo: local
    hooks:
      - id: backend-lint
        name: backend lint (Biome)
        entry: bash -c 'cd backend && bun run lint'
        language: system
        files: ^backend/
        types_or: [javascript, jsx, ts, tsx, json]
        pass_filenames: false"""
    return f"""\
  - repo: local
    hooks:
      - id: backend-ruff
        name: backend ruff (project version)
        entry: {_entry(_PROJECT_RUFF)}
        language: system
        files: ^backend/.*\\.pyi?$
        pass_filenames: false"""


def generate_pre_commit_config(config: ProjectConfig) -> str:
    """Generate .pre-commit-config.yaml content."""
    repos: list[str] = []

    # Common hooks
    repos.append("""\
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files""")

    if config.has_backend:
        repos.append(_backend_hooks(config))

    if config.has_frontend:
        format_hook = (
            ""
            if config.is_nextjs
            else """
      - id: frontend-format
        name: frontend format (Oxfmt)
        entry: bash -c 'cd frontend && bun run format:check'
        language: system
        files: ^frontend/
        pass_filenames: false"""
        )
        repos.append(f"""\
  - repo: local
    hooks:
      - id: frontend-lint
        name: frontend lint
        entry: bash -c 'cd frontend && bun run lint'
        language: system
        files: ^frontend/
        types_or: [javascript, jsx, ts, tsx]
        pass_filenames: false{format_hook}""")

    repos_block = "\n".join(repos)
    header = ""
    if config.has_backend and config.backend_framework == BackendFramework.DJANGO_NINJA:
        # A plain `pre-commit install` then also installs the push-stage
        # gauntlet. Hooks without `stages` stay on commit, so fixers never
        # rewrite files during `git push`.
        header = (
            "default_install_hook_types: [pre-commit, pre-push]\ndefault_stages: [pre-commit]\n"
        )
    return f"{header}repos:\n{repos_block}\n"
