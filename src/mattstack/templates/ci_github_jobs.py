"""GitHub Actions pieces of the workflow generator: triggers, jobs, and runner label.

Every job pins ``runs-on: ubuntu-latest``; ``with_runner`` rewrites that label
for self-hosted runners. The GitLab generator and shared helpers stay in
``ci_toolchain``.
"""

from __future__ import annotations

from mattstack.templates.ci_toolchain import CHECKOUT, SETUP_UV, CiTools, in_dir, yaml_str
from mattstack.templates.stack_facts import BackendFacts

DEFAULT_RUNNER = "ubuntu-latest"


def github_triggers() -> str:
    """Return the ``on:`` block: main pushes and pull requests, a manual run, and a weekly run."""
    return "\n".join(
        (
            "on:",
            "  push:",
            "    branches: [main]",
            "  pull_request:",
            "    branches: [main]",
            "  workflow_dispatch:",
            "  schedule:",
            '    - cron: "0 6 * * 1"',
        )
    )


def gauntlet_job(tools: CiTools) -> str:
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


def _run(command: str, directory: str | None) -> str:
    """Return a `run:` step; with ``directory``, the command changes into it first."""
    if directory is None:
        return f"      - run: {command}"
    return f"      - run: {yaml_str(in_dir(directory, command))}"


def python_steps(backend: BackendFacts, tools: CiTools, directory: str | None = None) -> str:
    sync = f"uv sync --frozen --python {tools.python}{backend.ci_sync_args}"
    return f"""      - uses: {CHECKOUT}
      - uses: {SETUP_UV}
        with:
          version: {yaml_str(tools.uv)}
          enable-cache: true
{_run(sync, directory)}"""


def backend_check_job(steps: str, django_package: str, directory: str) -> str:
    """Build the Django job that runs the system and migration checks from `just ci`.

    ``steps`` come from ``python_steps(backend, tools, directory)``. The check
    commands also change into ``directory``, so the job sets no working-directory default.
    """
    settings = f"{django_package}.settings.test"
    check = "uv run python manage.py check"
    migrations = "uv run python manage.py makemigrations --check --dry-run"
    return f"""  backend-check:
    runs-on: ubuntu-latest
    env:
      DJANGO_SETTINGS_MODULE: {yaml_str(settings)}
    steps:
{steps}
{_run(check, directory)}
{_run(migrations, directory)}"""


def with_runner(workflow: str, label: str) -> str:
    """Return ``workflow`` with every default GitHub-hosted runner replaced by ``label``."""
    if label == DEFAULT_RUNNER:
        return workflow
    return workflow.replace(f"runs-on: {DEFAULT_RUNNER}", f"runs-on: {yaml_str(label)}")
