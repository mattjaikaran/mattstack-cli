"""Workflow command: CI/CD workflow generation for fullstack monorepos.

Job names are part of the contract. `mattstack protect` requires the
`gauntlet` status check by default, so this generator emits a job with that
exact name for every project type.
"""

from __future__ import annotations

import time
from pathlib import Path

import typer

from mattstack.config import (
    BackendFramework,
    FrontendFramework,
    ProjectConfig,
    ProjectType,
)
from mattstack.templates.frontend_commands import frontend_commands
from mattstack.utils.console import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
)


def _detect_project_type(path: Path) -> str:
    """Detect if project is fullstack, backend-only, or frontend-only."""
    has_be = (path / "backend" / "pyproject.toml").exists()
    has_fe = (path / "frontend" / "package.json").exists()
    if has_be and has_fe:
        return "fullstack"
    if has_be:
        return "backend-only"
    if has_fe:
        return "frontend-only"
    return "unknown"


def _detect_frontend_framework(path: Path) -> FrontendFramework:
    """Resolve the frontend framework from the generated package.json.

    The scaffolding process renames the package, so the manifest does not
    name the framework. Two markers are reliable, in order:

    1. The dev script: `next` or `rsbuild` identify those boilerplates.
    2. The type-check script name. `react-vite-boilerplate` and
       `react-vite-starter` both run `vite` for dev, so the dev script
       cannot tell them apart, but only the boilerplate defines
       `type-check`; the starter defines `typecheck`.

    Getting this wrong emits a CI job that fails on its first run, so this
    must agree with `mattstack.templates.frontend_commands`.
    """
    import json

    package_json = path / "frontend" / "package.json"
    try:
        pkg = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return FrontendFramework.REACT_VITE

    scripts = pkg.get("scripts", {})
    if not isinstance(scripts, dict):
        return FrontendFramework.REACT_VITE
    dev = str(scripts.get("dev", ""))
    if "next" in dev:
        return FrontendFramework.NEXTJS
    if "rsbuild" in dev:
        return FrontendFramework.REACT_RSBUILD
    if "type-check" in scripts:
        return FrontendFramework.REACT_VITE
    return FrontendFramework.REACT_VITE_STARTER


def _config_for_ci(path: Path, project_type: str) -> ProjectConfig:
    """Build the minimal config needed to resolve frontend commands."""
    has_backend = (path / "backend" / "pyproject.toml").exists()
    if project_type == "frontend-only":
        ptype = ProjectType.FRONTEND_ONLY
    elif project_type == "backend-only":
        ptype = ProjectType.BACKEND_ONLY
    else:
        ptype = ProjectType.FULLSTACK
    return ProjectConfig(
        name=path.name or "project",
        path=path,
        project_type=ptype,
        frontend_framework=_detect_frontend_framework(path),
        backend_framework=BackendFramework.DJANGO_NINJA,
        use_celery=False,
        use_redis=has_backend,
        init_git=False,
    )


def _gauntlet_job() -> str:
    """Build the Gauntlet verification job.

    The job name is the status check that `mattstack protect` requires, so
    do not rename it. It calls mattstack rather than the gauntlet binary,
    because `mattstack gauntlet` exits 1 when the binary is missing.

    mattstack is not on PyPI yet, so install it from git. Pass
    `--fail-if-absent`, because this job is a required status check: without
    it, a skipped audit exits 0 and the check passes while verifying nothing.
    """
    return """  gauntlet:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - name: Install mattstack
        run: uv tool install git+https://github.com/mattjaikaran/mattstack-cli
      - name: Run the Gauntlet gate
        run: mattstack audit --no-todo --fail-if-absent"""


def _generate_github_actions(path: Path, project_type: str, *, with_gauntlet: bool) -> str:
    """Generate GitHub Actions CI workflow YAML."""
    jobs: list[str] = []

    if with_gauntlet:
        jobs.append(_gauntlet_job())

    if project_type in ("fullstack", "backend-only"):
        jobs.append(_backend_lint_job())
        jobs.append(_backend_test_job())

    if project_type in ("fullstack", "frontend-only"):
        config = _config_for_ci(path, project_type)
        cmds = frontend_commands(config)
        jobs.append(_bun_job("frontend-lint", cmds.lint))
        if cmds.test:
            jobs.append(_bun_job("frontend-test", cmds.test))
        if cmds.typecheck:
            jobs.append(_bun_job("frontend-typecheck", cmds.typecheck))

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


def _backend_lint_job() -> str:
    return """  backend-lint:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check ."""


def _backend_test_job() -> str:
    return """  backend-test:
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
        working-directory: backend
    env:
      DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test_db
      REDIS_URL: redis://localhost:6379/0
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: uv sync --frozen
      - run: uv run pytest -x -q"""


def _bun_job(name: str, command: str) -> str:
    """Build one CI job that runs a bun command in frontend/."""
    return f"""  {name}:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v2
        with:
          bun-version: latest
      - run: bun install --frozen-lockfile
      - run: {command}"""


def _generate_gitlab_ci(path: Path, project_type: str, *, with_gauntlet: bool) -> str:
    """Generate GitLab CI configuration."""
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
    - mattstack audit --no-todo --fail-if-absent""")

    if project_type in ("fullstack", "backend-only"):
        stages.extend(["lint", "test"])
        jobs.append("""
backend-lint:
  stage: lint
  image: python:3.13-slim
  before_script:
    - pip install uv
    - cd backend && uv sync --frozen
  script:
    - uv run ruff check .
    - uv run ruff format --check .""")

        jobs.append("""
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
    DATABASE_URL: postgresql://postgres:postgres@postgres:5432/test_db
    REDIS_URL: redis://redis:6379/0
  before_script:
    - pip install uv
    - cd backend && uv sync --frozen
  script:
    - uv run pytest -x -q""")

    if project_type in ("fullstack", "frontend-only"):
        config = _config_for_ci(path, project_type)
        cmds = frontend_commands(config)
        if "lint" not in stages:
            stages.append("lint")
        if "test" not in stages:
            stages.append("test")

        jobs.append(_gitlab_frontend_job("frontend-lint", "lint", cmds.lint))
        if cmds.test:
            jobs.append(_gitlab_frontend_job("frontend-test", "test", cmds.test))
        if cmds.typecheck:
            jobs.append(_gitlab_frontend_job("frontend-typecheck", "test", cmds.typecheck))

    stages_str = "\n".join(f"  - {s}" for s in stages)
    jobs_str = "\n".join(jobs)

    return f"""stages:
{stages_str}
{jobs_str}
"""


def _gitlab_frontend_job(name: str, stage: str, command: str) -> str:
    """Build one GitLab job that runs a bun command in frontend/."""
    return f"""
{name}:
  stage: {stage}
  image: oven/bun:latest
  before_script:
    - cd frontend && bun install --frozen-lockfile
  script:
    - {command}"""


def run_generate_workflow(
    path: Path,
    platform: str = "github-actions",
    dry_run: bool = False,
) -> None:
    """Generate CI/CD workflow configuration."""
    path = path.resolve()
    if not path.is_dir():
        print_error(f"Directory not found: {path}")
        raise typer.Exit(code=1)

    start = time.perf_counter()

    console.print()
    console.print("[bold cyan]mattstack workflow[/bold cyan]")
    console.print()

    project_type = _detect_project_type(path)
    if project_type == "unknown":
        print_error("Could not detect project type (no backend/ or frontend/ found)")
        raise typer.Exit(code=1)

    print_info(f"Detected project type: {project_type}")
    print_info(f"Platform: {platform}")

    if platform == "github-actions":
        content = _generate_github_actions(path, project_type, with_gauntlet=True)
        output_path = path / ".github" / "workflows" / "ci.yml"
    elif platform == "gitlab-ci":
        content = _generate_gitlab_ci(path, project_type, with_gauntlet=True)
        output_path = path / ".gitlab-ci.yml"
    else:
        print_error(f"Unknown platform: {platform}. Use: github-actions, gitlab-ci")
        raise typer.Exit(code=1)

    if dry_run:
        console.print()
        console.print(f"[bold]Would create:[/bold] {output_path}")
        console.print()
        console.print(content)
        elapsed = time.perf_counter() - start
        console.print(f"[dim]({elapsed:.1f}s)[/dim]")
        return

    # Write file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        print_warning(f"Overwriting existing {output_path.name}")
    output_path.write_text(content, encoding="utf-8")

    elapsed = time.perf_counter() - start
    print_success(f"Created {output_path}")
    console.print(f"[dim]({elapsed:.1f}s)[/dim]")
