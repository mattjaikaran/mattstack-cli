"""Workflow command: opt-in hosted CI generation for fullstack monorepos.

Generated projects run every gate locally (``make gauntlet`` and the pre-push
hook). Hosted runners cost build minutes, so this command writes a workflow
only for an explicit ``--ci github`` or ``--ci gitlab``.

Job names are part of the contract. `mattstack protect` requires the
`gauntlet` status check by default, so this generator emits a job with that
exact name for every project type. Backend and frontend jobs follow the
resolved frameworks, and every action, image, and tool version is pinned.
"""

from __future__ import annotations

import time
from pathlib import Path

import typer
from rich.markup import escape

from mattstack.config import ProjectConfig
from mattstack.stack import load_stack, unknown_framework_message
from mattstack.templates.ci_toolchain import (
    CHECKOUT,
    NODE_VERSION,
    SETUP_UV,
    CiLayout,
    CiTools,
    JsCi,
    backend_test_env,
    ci_tools,
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
    print_warning,
)
from mattstack.utils.package_manager import PackageManager


def _gauntlet_job(tools: CiTools) -> str:
    """Build the Gauntlet job; its name is the status check `mattstack protect` requires.

    It installs mattstack from git and runs the built-in auditors, which exit 1
    on any error-severity finding. `--no-todo` keeps CI from writing tasks/todo.md.
    """
    return f"""  gauntlet:
    runs-on: ubuntu-latest
    steps:
      - uses: {CHECKOUT}
      - uses: {SETUP_UV}
        with:
          version: {yaml_str(tools.uv)}
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
    tools = ci_tools(layout.root)
    jobs: list[str] = []

    if with_gauntlet:
        jobs.append(_gauntlet_job(tools))

    if config.has_backend:
        backend = backend_facts(config.backend_framework)
        if backend.is_python:
            jobs.append(_backend_lint_job(backend, backend_dir, tools))
            jobs.append(_backend_test_job(backend, backend_dir, tools))
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


def _python_steps(backend: BackendFacts, tools: CiTools) -> str:
    return f"""      - uses: {CHECKOUT}
      - uses: {SETUP_UV}
        with:
          version: {yaml_str(tools.uv)}
          enable-cache: true
      - run: uv sync --frozen --python {tools.python}{backend.ci_sync_args}"""


def _backend_lint_job(backend: BackendFacts, directory: str, tools: CiTools) -> str:
    return f"""  backend-lint:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: {yaml_str(directory)}
    steps:
{_python_steps(backend, tools)}
      - run: uv run ruff check .
      - run: uv run ruff format --check ."""


def _backend_test_job(backend: BackendFacts, directory: str, tools: CiTools) -> str:
    return f"""  backend-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:{tools.postgres}
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
        image: valkey/valkey:{tools.valkey}
        ports:
          - 6379:6379
        options: >-
          --health-cmd "valkey-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    defaults:
      run:
        working-directory: {yaml_str(directory)}
    env:
{yaml_mapping(backend_test_env(backend, "localhost", "localhost"), 6)}
    steps:
{_python_steps(backend, tools)}
      - run: uv run pytest -x -q"""


def _js_job(name: str, command: str, js: JsCi, directory: str) -> str:
    """Build one CI job that installs and runs ``command`` in ``directory``."""
    return f"""  {name}:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: {yaml_str(directory)}
    steps:
      - uses: {CHECKOUT}
{github_js_setup(js)}
      - run: {js.install}
      - run: {command}"""


def _generate_gitlab_ci(
    config: ProjectConfig, *, with_gauntlet: bool, layout: CiLayout | None = None
) -> str:
    """Generate GitLab CI configuration. See _generate_github_actions for ``layout``."""
    layout = layout or _default_layout(config)
    backend_dir, frontend_dir = layout.rel(layout.backend), layout.rel(layout.frontend)
    tools = ci_tools(layout.root)
    stages: list[str] = []
    jobs: list[str] = []

    if with_gauntlet:
        stages.append("verify")
        jobs.append(f"""
gauntlet:
  stage: verify
  image: {tools.uv_image}
  before_script:
    - uv tool install git+https://github.com/mattjaikaran/mattstack-cli
  script:
    - mattstack audit --no-todo""")

    if config.has_backend:
        stages.extend(["lint", "test"])
        backend = backend_facts(config.backend_framework)
        if backend.is_python:
            jobs.extend(_gitlab_python_jobs(backend, backend_dir, tools))
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


def _gitlab_python_jobs(backend: BackendFacts, directory: str, tools: CiTools) -> list[str]:
    sync = f"uv sync --frozen --python {tools.python}{backend.ci_sync_args}"
    head = f"""
  image: {tools.uv_image}
  before_script:
    - {yaml_str(in_dir(directory, sync))}"""
    lint = f"""
backend-lint:
  stage: lint{head}
  script:
    - uv run ruff check .
    - uv run ruff format --check ."""
    test = f"""
backend-test:
  stage: test{head}
  services:
    - postgres:{tools.postgres}
    - name: valkey/valkey:{tools.valkey}
      alias: redis
  variables:
    POSTGRES_DB: test_db
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: postgres
{yaml_mapping(backend_test_env(backend, "postgres", "redis"), 4)}
  script:
    - uv run pytest -x -q"""
    return [lint, test]


def _gitlab_js_job(name: str, stage: str, command: str, js: JsCi, directory: str) -> str:
    """Build one GitLab job that installs and runs ``command`` in ``directory``."""
    image = f"oven/bun:{js.bun}" if js.pm == PackageManager.BUN else f"node:{NODE_VERSION}"
    corepack = "corepack enable && " if js.pm in (PackageManager.PNPM, PackageManager.YARN) else ""
    return f"""
{name}:
  stage: {stage}
  image: {image}
  before_script:
    - {yaml_str(in_dir(directory, corepack + js.install))}
  script:
    - {command}"""


_CI_TARGETS = {
    "github": (_generate_github_actions, Path(".github") / "workflows" / "ci.yml"),
    "gitlab": (_generate_gitlab_ci, Path(".gitlab-ci.yml")),
}


def run_generate_workflow(
    path: Path,
    ci: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Generate an opt-in hosted CI workflow; without ``ci``, explain the local gates.

    An existing workflow file is a user file: it is replaced only with
    ``force``. Without it, a differing file stops the command with exit 1.
    """
    target = _CI_TARGETS.get(ci or "")
    if target is None:
        print_error(
            "Hosted CI is opt-in. Gates run locally: `make gauntlet` and the "
            "pre-push hook (`mattstack hooks install`)."
        )
        print_info("To generate a workflow anyway, pass --ci github or --ci gitlab.")
        raise typer.Exit(code=2)
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
    print_warning(f"--ci {ci}: every push and pull request will spend hosted CI minutes.")
    generate, relative = target
    content = generate(config, with_gauntlet=True, layout=layout)
    output_path = stack.root / relative

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
