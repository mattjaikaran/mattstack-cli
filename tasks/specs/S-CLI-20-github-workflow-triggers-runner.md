# S-CLI-20: Generate a GitHub workflow with dispatch, weekly schedule, runner label and the `just ci` checks

| Field | Value |
|---|---|
| Spec ID | S-CLI-20 |
| Backlog item | GitHub issue #42 (generated CI that needs no `.env`: `workflow_dispatch`, weekly `schedule`, a `runs-on` label for self-hosted runners, and the `ci` recipe's checks as parallel jobs), opt-in `--ci github` part only |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | f4c5525 |
| Branch | agent/S-CLI-20 |
| Depends on | none |
| Conflicts with | S-CLI-01 |
| Files owned | `src/mattstack/commands/workflow.py`, `src/mattstack/cli_project.py`, `src/mattstack/templates/ci_github_jobs.py` (new), `tests/test_commands/test_workflow_triggers.py` (new) |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 15 |
| Max changed lines | 800 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_commands/test_workflow_triggers.py tests/test_commands/test_workflow.py tests/test_commands/test_workflow_jobs.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3; A4; A5 (table below) |

## Context and verified citations

Verified on `f4c5525` (2026-11-11).

- Issue #42 asks for a generated `ci` recipe and a `ci.yml` whose jobs run the same checks, with the triggers `pull_request`, `workflow_dispatch` and a weekly `schedule`, and a `runs-on` label for self-hosted runners. The `ci` recipe already exists: `src/mattstack/templates/root_justfile.py:178-212` (`_ci_recipe`) runs ruff, the format check, and for Ninja `manage.py check` and `makemigrations --check --dry-run` with `DJANGO_SETTINGS_MODULE={django_package}.settings.test` (lines 198-203), then frontend install, lint, typecheck and `bun run build` (lines 205-211). Generated `test` and `backend-test` recipes do not read `.env`, and `set dotenv-load` (`root_justfile.py:62`) tolerates a missing file (comment at lines 57-58). So only the workflow generator is left.
- `src/mattstack/commands/workflow.py:73` (`_generate_github_actions`) builds the workflow. Its `on:` block (lines 112-116) has only `push` and `pull_request` on `main`. Four job templates hard-code `runs-on: ubuntu-latest` (lines 57, 138, 150, 187), and no other file under `src/` contains `ubuntu`. The jobs are `gauntlet`, `backend-lint`, `backend-test`, `frontend-lint`, `frontend-test`, `frontend-typecheck` (lines 77-106); there is no Django check job and no frontend build job.
- `workflow.py` is 397 lines and the file-length gate allows 400. New logic goes in `src/mattstack/templates/ci_github_jobs.py`; `_python_steps` (line 127) moves there, and if `workflow.py` still exceeds 400 lines move `_gauntlet_job` (line 50) too. Other workflow code stays put.
- `src/mattstack/cli_project.py:225-250` defines `workflow` and calls `run_generate_workflow(path=..., ci=ci, dry_run=..., force=...)`; `workflow.py:312` is `run_generate_workflow`; `_CI_TARGETS` (line 306) maps `github` and `gitlab` to their generators.
- `src/mattstack/commands/protect.py:27` requires only the `gauntlet` job name (`DEFAULT_STATUS_CHECKS`); `tests/test_commands/test_workflow_jobs.py:132` pins it. New jobs must not rename existing ones.
- `src/mattstack/templates/ci_toolchain.py:65` `yaml_str` quotes a value as a YAML string; `ci_toolchain.py:111` `JsCi.run` translates a Bun command for the project's package manager.
- Measured: on a fresh `starter-fullstack` scaffold, `uv run mattstack workflow --ci github --dry-run --path <project>` prints a workflow whose `on:` has `push` and `pull_request` only, and `load_stack(<project>).config().django_package` is `api`.

## Goal and non-goals

`mattstack workflow --ci github` writes a workflow that can also be started by hand and runs weekly, accepts `--runs-on LABEL` for every job, and has one parallel job per remaining `just ci` check (Django system and migration check for Ninja backends, frontend build). Non-goals: no default CI at `init` (hosted CI stays opt-in, `tasks/todo.md` rules); no GitLab change; no fork-PR guard or runner provisioning; no change to existing job names or to `push`/`pull_request` triggers.

## Implementation steps

1. Create `src/mattstack/templates/ci_github_jobs.py` with: `github_triggers() -> str` (the full `on:` block: `push` and `pull_request` on `main` as today, `workflow_dispatch:`, and `schedule` with one cron entry, weekly on Monday); `python_steps(backend, tools)` moved from `workflow.py:127` unchanged; `backend_check_job(steps: str, django_package: str, directory: str) -> str` (job `backend-check`: the python steps, then `uv run python manage.py check` and `uv run python manage.py makemigrations --check --dry-run`, with `DJANGO_SETTINGS_MODULE: <django_package>.settings.test` in the job `env`, working directory `directory` quoted with `yaml_str`); `with_runner(workflow: str, label: str) -> str` (replaces every `runs-on: ubuntu-latest` line with `runs-on: <yaml_str(label)>`; the default label returns the text unchanged).
2. In `workflow.py`, use `github_triggers()` for the `on:` block, import `python_steps`, add `backend-check` after `backend-lint` only when `config.is_ninja_backend`, and add a `frontend-build` job built with the existing `_js_job("frontend-build", js.run("bun run build"), js, frontend_dir)` after `frontend-typecheck`.
3. Add `runs_on: str | None = None` to `run_generate_workflow`. After the existing `ci` validation: when `runs_on` is set and `ci != "github"`, print an error that says GitLab selects runners with tags and `--runs-on` applies to `--ci github`, and raise `typer.Exit(code=2)`. When it is set for GitHub, pass the generated text through `with_runner` before the up-to-date and dry-run comparisons.
4. In `cli_project.py`, add `--runs-on` (`str | None`, help: runner label for every job of the GitHub workflow, for example a self-hosted runner label; default ubuntu-latest) to `workflow` and pass it through.
5. Create `tests/test_commands/test_workflow_triggers.py`. Build configs the way `tests/test_commands/test_workflow.py:30-42` does; parse output with `yaml.safe_load` (note: PyYAML reads the key `on` as boolean `True`; look the triggers up with that in mind). Cover: triggers include `push`, `pull_request`, `workflow_dispatch` and a `schedule` entry whose cron has five fields; `--runs-on` replaces `runs-on` in every job and leaves no `ubuntu-latest`; a Ninja fullstack config has `backend-check` whose steps include `manage.py check` and `makemigrations --check --dry-run` and whose env module is `<package>.settings.test`; a FastAPI or NestJS backend has no `backend-check`; `frontend-build` exists for a project with a frontend and uses the project's package manager (`js.run`); `run_generate_workflow(..., ci="gitlab", runs_on="x")` raises `typer.Exit` with code 2 and writes nothing; the `gauntlet` job is still present.

Stage only the Files owned, with explicit paths. Commit subject: `feat(workflow): Add dispatch, schedule and runner label`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_commands/test_workflow_triggers.py tests/test_commands/test_workflow.py tests/test_commands/test_workflow_jobs.py -q` | 0 | All tests pass; the existing workflow tests are unchanged |
| A2 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run mattstack init wf-smoke -p starter-fullstack -o /tmp/s-cli-20` | 0 | Creates `/tmp/s-cli-20/wf-smoke` |
| A3 | repo root | `uv run mattstack workflow --ci github --dry-run --runs-on ci-runner-mattstack --path /tmp/s-cli-20/wf-smoke` | 0 | Output contains `workflow_dispatch:`, `schedule:`, `backend-check:`, `frontend-build:` and `runs-on: "ci-runner-mattstack"`; it does not contain `ubuntu-latest` |
| A4 | repo root | `uv run mattstack workflow --ci gitlab --runs-on x --dry-run --path /tmp/s-cli-20/wf-smoke` | 2 | stderr mentions `--ci github`; no `.gitlab-ci.yml` is written |
| A5 | repo root | `uv run python scripts/check_file_length.py` | 0 | `workflow.py` is at most 400 lines |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a new dependency, or a check that fails outside your change. If `S-CLI-01` is still open and has changed `workflow.py` or `ci_toolchain.py` since the base commit, report the overlap instead of resolving it. If `django_package` is not `api` for the scaffold in A2, report the value and stop. The PR body lists the spec ID, base and head SHA, owned files with changed-line counts, and each criterion with its observed result.
