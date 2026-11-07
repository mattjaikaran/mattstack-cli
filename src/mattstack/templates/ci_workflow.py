"""Default GitHub Actions CI for generated projects.

`mattstack init` writes this workflow so a fresh checkout runs the same
checks as the root justfile's ``ci`` recipe on every pull request, manual
dispatch, and a weekly schedule. The jobs need no ``.env``, database, or
Docker: each step reads only the committed lockfiles.

Runner labels come from ``ProjectConfig.ci_runs_on``. A comma-separated
list renders as a YAML flow sequence, so a self-hosted runner can match
``self-hosted, Linux, X64``.
"""

from __future__ import annotations

from pathlib import Path

from mattstack.config import ProjectConfig
from mattstack.templates.ci_toolchain import (
    CHECKOUT,
    SETUP_UV,
    CiLayout,
    CiTools,
    JsCi,
    ci_tools,
    github_js_setup,
    js_ci,
    yaml_str,
)
from mattstack.templates.frontend_commands import frontend_commands
from mattstack.templates.stack_facts import BackendFacts, backend_facts

_CRON = "0 9 * * 0"


def generate_ci_workflow(config: ProjectConfig) -> str:
    """Generate the default ``.github/workflows/ci.yml`` content."""
    layout = CiLayout(config.path, config.backend_dir, config.frontend_dir)
    tools = ci_tools(config.path)
    runs_on = _runs_on(config.ci_runs_on)
    jobs: list[str] = []

    if config.has_backend:
        backend = backend_facts(config.backend_framework)
        directory = _rel(layout, layout.backend)
        if backend.is_python:
            jobs.append(_backend_lint_job(config, backend, directory, tools, runs_on))
            if config.is_ninja_backend:
                jobs.append(_django_check_job(config, backend, directory, tools, runs_on))
        else:
            jobs.append(
                _js_job(
                    "backend-lint",
                    "Backend lint",
                    backend.lint,
                    js_ci(layout.backend, layout.root),
                    directory,
                    runs_on,
                )
            )

    if config.has_frontend:
        cmds = frontend_commands(config)
        js = js_ci(layout.frontend, layout.root)
        directory = _rel(layout, layout.frontend)
        jobs.append(_js_job("frontend-lint", "Frontend lint", cmds.lint, js, directory, runs_on))
        if cmds.typecheck:
            jobs.append(
                _js_job(
                    "frontend-typecheck",
                    "Frontend typecheck",
                    cmds.typecheck,
                    js,
                    directory,
                    runs_on,
                )
            )
        jobs.append(
            _js_job(
                "frontend-build", "Frontend build", js.run("bun run build"), js, directory, runs_on
            )
        )

    jobs_block = "\n\n".join(jobs)
    return f"""name: CI

# Checks run on a fresh checkout: no .env, database, or Docker is required.
on:
  pull_request:
  workflow_dispatch:
  schedule:
    - cron: "{_CRON}"

concurrency:
  group: ci-${{{{ github.ref }}}}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
{jobs_block}
"""


def _rel(layout: CiLayout, component: Path) -> str:
    return layout.rel(component)


def _runs_on(labels: str) -> str:
    """Render ``runs-on`` from a comma-separated label list."""
    parts = [part.strip() for part in labels.split(",") if part.strip()]
    if not parts:
        return "ubuntu-latest"
    return parts[0] if len(parts) == 1 else f"[{', '.join(parts)}]"


def _python_setup(config: ProjectConfig, backend: BackendFacts, tools: CiTools) -> str:
    extra = backend.ci_sync_args
    if config.is_ninja_backend:
        extra += " --extra dev"
    return f"""      - uses: {CHECKOUT}
      - uses: {SETUP_UV}
        with:
          version: {yaml_str(tools.uv)}
          enable-cache: true
      - run: uv sync --frozen --python {tools.python}{extra}"""


def _backend_lint_job(
    config: ProjectConfig, backend: BackendFacts, directory: str, tools: CiTools, runs_on: str
) -> str:
    return f"""  backend-lint:
    name: Backend lint and format
    runs-on: {runs_on}
    defaults:
      run:
        working-directory: {yaml_str(directory)}
    steps:
{_python_setup(config, backend, tools)}
      - run: uv run ruff check .
      - run: uv run ruff format --check ."""


def _django_check_job(
    config: ProjectConfig, backend: BackendFacts, directory: str, tools: CiTools, runs_on: str
) -> str:
    settings = f"{config.django_package}.settings.test"
    return f"""  backend-django:
    name: Django system check and migration drift
    runs-on: {runs_on}
    defaults:
      run:
        working-directory: {yaml_str(directory)}
    env:
      DJANGO_SETTINGS_MODULE: {yaml_str(settings)}
    steps:
{_python_setup(config, backend, tools)}
      - run: uv run python manage.py check
      - run: uv run python manage.py makemigrations --check --dry-run"""


def _js_job(name: str, label: str, command: str, js: JsCi, directory: str, runs_on: str) -> str:
    return f"""  {name}:
    name: {label}
    runs-on: {runs_on}
    defaults:
      run:
        working-directory: {yaml_str(directory)}
    steps:
      - uses: {CHECKOUT}
{github_js_setup(js)}
      - run: {js.install}
      - run: {command}"""
