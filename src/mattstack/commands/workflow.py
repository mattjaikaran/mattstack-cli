"""Workflow command: CI/CD workflow generation for fullstack monorepos.

Job names are part of the contract. `mattstack protect` requires the
`gauntlet` status check by default, so this generator emits a job with that
exact name for every project type.

Backend and frontend jobs follow the project's resolved frameworks: Python
backends run uv, ruff, and pytest; a NestJS backend runs its package scripts.
JavaScript jobs use the package manager that the committed lockfile names;
a project without a lockfile keeps the scaffold default, Bun.
"""

from __future__ import annotations

import time
from pathlib import Path

import typer
from rich.markup import escape

from mattstack.config import ProjectConfig
from mattstack.stack import load_stack, unknown_framework_message
from mattstack.templates.ci_toolchain import (
    CiLayout,
    JsCi,
    backend_test_env,
    github_js_setup,
    in_dir,
    js_ci,
    yaml_mapping,
    yaml_str,
)
from mattstack.templates.frontend_commands import frontend_commands
from mattstack.templates.stack_facts import BackendFacts, backend_facts
from mattstack.utils.console import (
    console,
    print_error,
    print_info,
    print_success,
)
from mattstack.utils.package_manager import PackageManager


def _gauntlet_job() -> str:
    """Build the Gauntlet verification job.

    The job name is the status check that `mattstack protect` requires, so
    do not rename it. mattstack is not on PyPI yet, so the job installs it
    from git. It runs `mattstack audit --no-todo`: the built-in auditors
    (no external binary), which exit 1 when any error-severity finding
    exists. `--no-todo` keeps CI from writing tasks/todo.md.
    """
    return """  gauntlet:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Install mattstack
        run: uv tool install git+https://github.com/mattjaikaran/mattstack-cli
      - name: Run the Gauntlet gate
        run: mattstack audit --no-todo"""


def _default_layout(config: ProjectConfig) -> CiLayout:
    return CiLayout(config.path, config.backend_dir, config.frontend_dir)


def _generate_github_actions(
    config: ProjectConfig, *, with_gauntlet: bool, layout: CiLayout | None = None
) -> str:
    """Generate GitHub Actions CI workflow YAML.

    ``layout`` holds the resolved component directories; the default is the
    scaffold layout (`backend/` and `frontend/`).
    """
    layout = layout or _default_layout(config)
    backend_dir, frontend_dir = layout.rel(layout.backend), layout.rel(layout.frontend)
    jobs: list[str] = []

    if with_gauntlet:
        jobs.append(_gauntlet_job())

    if config.has_backend:
        backend = backend_facts(config.backend_framework)
        if backend.is_python:
            jobs.append(_backend_lint_job(backend, backend_dir))
            jobs.append(_backend_test_job(backend, backend_dir))
        else:
            js = js_ci(layout.backend, layout.root)
            jobs.append(_js_job("backend-lint", js.run(backend.lint), js, backend_dir))
            jobs.append(_js_job("backend-test", js.run(backend.test), js, backend_dir))

    if config.has_frontend:
        cmds = frontend_commands(config)
        js = js_ci(layout.frontend, layout.root)
        jobs.append(_js_job("frontend-lint", js.run(cmds.lint), js, frontend_dir))
        if cmds.test:
            jobs.append(_js_job("frontend-test", js.run(cmds.test), js, frontend_dir))
        if cmds.typecheck:
            jobs.append(_js_job("frontend-typecheck", js.run(cmds.typecheck), js, frontend_dir))

    jobs_block = "\n\n".join(jobs)

    return f"""name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ${{{{ github.workflow }}}}-${{{{ github.ref }}}}
  cancel-in-progress: true

jobs:
{jobs_block}
"""


def _backend_lint_job(backend: BackendFacts, directory: str) -> str:
    return f"""  backend-lint:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
    defaults:
      run:
        working-directory: {yaml_str(directory)}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
      - uses: actions/setup-python@v5
        with:
          python-version: ${{{{ matrix.python-version }}}}
      - run: uv sync --frozen{backend.ci_sync_args}
      - run: uv run ruff check .
      - run: uv run ruff format --check ."""


def _backend_test_job(backend: BackendFacts, directory: str) -> str:
    return f"""  backend-test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    defaults:
      run:
        working-directory: {yaml_str(directory)}
    env:
{yaml_mapping(backend_test_env(backend, "localhost", "localhost"), 6)}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
      - uses: actions/setup-python@v5
        with:
          python-version: ${{{{ matrix.python-version }}}}
      - run: uv sync --frozen{backend.ci_sync_args}
      - run: uv run pytest -x -q"""


def _js_job(name: str, command: str, js: JsCi, directory: str) -> str:
    """Build one CI job that installs and runs ``command`` in ``directory``."""
    return f"""  {name}:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: {yaml_str(directory)}
    steps:
      - uses: actions/checkout@v4
{github_js_setup(js)}
      - run: {js.install}
      - run: {command}"""


def _generate_gitlab_ci(
    config: ProjectConfig, *, with_gauntlet: bool, layout: CiLayout | None = None
) -> str:
    """Generate GitLab CI configuration. See _generate_github_actions for ``layout``."""
    layout = layout or _default_layout(config)
    backend_dir, frontend_dir = layout.rel(layout.backend), layout.rel(layout.frontend)
    stages: list[str] = []
    jobs: list[str] = []

    if with_gauntlet:
        stages.append("verify")
        jobs.append("""
gauntlet:
  stage: verify
  image: python:3.13-slim
  before_script:
    - pip install uv && uv tool install git+https://github.com/mattjaikaran/mattstack-cli
  script:
    - mattstack audit --no-todo""")

    if config.has_backend:
        stages.extend(["lint", "test"])
        backend = backend_facts(config.backend_framework)
        if backend.is_python:
            jobs.extend(_gitlab_python_jobs(backend, backend_dir))
        else:
            js = js_ci(layout.backend, layout.root)
            for name, stage, command in (
                ("backend-lint", "lint", backend.lint),
                ("backend-test", "test", backend.test),
            ):
                jobs.append(_gitlab_js_job(name, stage, js.run(command), js, backend_dir))

    if config.has_frontend:
        cmds = frontend_commands(config)
        if "lint" not in stages:
            stages.append("lint")
        if "test" not in stages:
            stages.append("test")

        js = js_ci(layout.frontend, layout.root)
        frontend_jobs = (
            ("frontend-lint", "lint", cmds.lint),
            ("frontend-test", "test", cmds.test),
            ("frontend-typecheck", "test", cmds.typecheck),
        )
        for name, stage, frontend_command in frontend_jobs:
            if frontend_command:
                jobs.append(_gitlab_js_job(name, stage, js.run(frontend_command), js, frontend_dir))

    stages_str = "\n".join(f"  - {s}" for s in stages)
    jobs_str = "\n".join(jobs)

    return f"""stages:
{stages_str}
{jobs_str}
"""


def _gitlab_python_jobs(backend: BackendFacts, directory: str) -> list[str]:
    install = yaml_str(in_dir(directory, f"uv sync --frozen{backend.ci_sync_args}"))
    lint = f"""
backend-lint:
  stage: lint
  image: python:3.13-slim
  before_script:
    - pip install uv
    - {install}
  script:
    - uv run ruff check .
    - uv run ruff format --check ."""
    test = f"""
backend-test:
  stage: test
  image: python:3.13-slim
  services:
    - postgres:17
    - redis:7
  variables:
    POSTGRES_DB: test_db
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: postgres
{yaml_mapping(backend_test_env(backend, "postgres", "redis"), 4)}
  before_script:
    - pip install uv
    - {install}
  script:
    - uv run pytest -x -q"""
    return [lint, test]


def _gitlab_js_job(name: str, stage: str, command: str, js: JsCi, directory: str) -> str:
    """Build one GitLab job that installs and runs ``command`` in ``directory``."""
    image = "oven/bun:latest" if js.pm == PackageManager.BUN else "node:22"
    corepack = "corepack enable && " if js.pm in (PackageManager.PNPM, PackageManager.YARN) else ""
    return f"""
{name}:
  stage: {stage}
  image: {image}
  before_script:
    - {yaml_str(in_dir(directory, corepack + js.install))}
  script:
    - {command}"""


def run_generate_workflow(
    path: Path,
    platform: str = "github-actions",
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Generate CI/CD workflow configuration.

    An existing workflow file is a user file: it is replaced only with
    ``force``. Without it, a differing file stops the command with exit 1.
    """
    path = path.resolve()
    if not path.is_dir():
        print_error(f"Directory not found: {path}")
        raise typer.Exit(code=1)

    start = time.perf_counter()

    console.print()
    console.print("[bold cyan]mattstack workflow[/bold cyan]")
    console.print()

    stack = load_stack(path)
    if not stack.has_backend and not stack.has_frontend:
        print_error("Could not detect project type (no backend/ or frontend/ found)")
        raise typer.Exit(code=1)
    unknown = stack.unknown_components()
    if unknown:
        print_error(unknown_framework_message(unknown))
        raise typer.Exit(code=1)

    config = stack.config()
    layout = CiLayout(stack.root, stack.project.backend_dir, stack.project.frontend_dir)
    stack_desc = [config.project_type.value]
    if config.has_backend:
        stack_desc.append(f"backend {config.backend_framework.value}")
    if config.has_frontend:
        stack_desc.append(f"frontend {config.frontend_framework.value}")
    print_info(f"Detected stack: {', '.join(stack_desc)}")
    print_info(f"Platform: {platform}")

    if platform == "github-actions":
        content = _generate_github_actions(config, with_gauntlet=True, layout=layout)
        output_path = stack.root / ".github" / "workflows" / "ci.yml"
    elif platform == "gitlab-ci":
        content = _generate_gitlab_ci(config, with_gauntlet=True, layout=layout)
        output_path = stack.root / ".gitlab-ci.yml"
    else:
        print_error(f"Unknown platform: {platform}. Use: github-actions, gitlab-ci")
        raise typer.Exit(code=1)

    exists = output_path.exists()
    if exists and output_path.read_text(encoding="utf-8", errors="replace") == content:
        print_success(f"{output_path} is already up to date")
        return
    blocked = exists and not force

    if dry_run:
        if not exists:
            action = "Would create:"
        elif blocked:
            action = "Would overwrite (requires --force):"
        else:
            action = "Would overwrite:"
        console.print()
        console.print(f"[bold]{action}[/bold] {escape(str(output_path))}")
        console.print()
        console.print(content, markup=False, highlight=False)
        elapsed = time.perf_counter() - start
        console.print(f"[dim]({elapsed:.1f}s)[/dim]")
        return

    if blocked:
        print_error(
            f"{output_path} already exists and differs. "
            "Re-run with --force to replace it, or --dry-run to review the new version."
        )
        raise typer.Exit(code=1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    elapsed = time.perf_counter() - start
    print_success(f"{'Replaced' if exists else 'Created'} {output_path}")
    console.print(f"[dim]({elapsed:.1f}s)[/dim]")
