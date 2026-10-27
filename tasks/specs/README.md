# Coding specs

This directory holds one file per coding task for the unattended executor
(agent-run). Each spec is one vertical slice that one overnight run can
finish and that a reviewer can merge alone.

## File format

Name each spec `S-<AREA>-<NN>-<slug>.md`. Start it with this header table:

| Field | Value |
|---|---|
| Spec ID | `S-CLI-<NN>` |
| Backlog item | The entry in `tasks/todo.md` or the GitHub issue |
| Role | `coding` |
| Status | `READY`, `DRAFT` (needs a decision) or `DONE` |
| Assigned executor | `agent-run`, or a person |
| Base commit | The commit the citations were checked on |
| Branch | `agent/<Spec ID>` |
| Depends on | Spec IDs that must be `DONE` or merged first, or `none` |
| Conflicts with | Spec IDs that must not run at the same time, or `none` |
| Files owned | Every path the change may touch, comma-separated |
| Migrations | `none` |
| Runtime locks | `none` |
| Human needed | `none`, or the open decision |
| Max files | At most 6 |
| Max changed lines | At most 300, insertions plus deletions |
| Verification commands | Commands from `Makefile` and the quick gates of `scripts/gauntlet.py` |
| Acceptance criteria | Criterion IDs, detailed in the acceptance table |

Then add these sections: context and verified citations, goal and
non-goals, implementation steps, machine-checkable acceptance, and stop
conditions.

## Executor rules

- Read `CLAUDE.md`, `docs/architecture.md` and the spec before you edit.
- Change only the spec's Files owned. Do not edit `tasks/todo.md`,
  `tasks/completed.md` or `tasks/specs/`.
- Use `uv` only. Add no dependency.
- Run the spec's Verification commands. The repository has no hosted CI;
  these are the quick gauntlet gates (`make gauntlet-quick`), one by one:

  ```bash
  uv sync --locked --extra dev
  uv run ruff format --check src/ tests/
  uv run ruff check src/ tests/
  uv run mypy src/
  uv run bandit -q -r src/ -c pyproject.toml
  uv run python scripts/check_architecture.py
  uv run python scripts/check_file_length.py
  GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short
  ```

  The prefix drops the `core.hooksPath` that the agent's environment sets
  in its global Git config and in `GIT_CONFIG_KEY_0`. Those hooks make
  `git init` fail, which breaks the tests that build temporary
  repositories.

- Commit with explicit paths and a Conventional Commit subject.
- Open a pull request from the spec's Branch. Do not push to `main`.
- Stop and report when a citation is wrong, a needed file is not owned, or
  the spec needs a new decision.

## Claiming

agent-run claims the first `READY` spec, in ID order, whose Assigned
executor names `agent-run`, whose dependencies are done, that has no open or
merged pull request, and that shares no owned file or declared conflict with
a claimed spec. The claim is the push that creates `agent/<Spec ID>`.

## Queue

| Spec | Status | Depends on | Conflicts with |
|---|---|---|---|
| [S-CLI-01](S-CLI-01-ci-pgvector-image.md) pgvector image in generated CI | READY | none | none |
| [S-CLI-02](S-CLI-02-controller-class-auth.md) class-level controller auth | READY | none | S-CLI-03 |
| [S-CLI-03](S-CLI-03-matt-jwt-required-auth.md) `@jwt_required` endpoint auth | READY | S-CLI-02 | S-CLI-02 |
| [S-CLI-04](S-CLI-04-hooks-hookspath.md) `core.hooksPath` in hooks | READY | none | none |
| [S-CLI-05](S-CLI-05-context-watch-clear.md) clear screen in context watch | READY | none | none |
| [S-CLI-06](S-CLI-06-generate-model-tests.md) generate model tests | READY | none | none |
| [S-CLI-07](S-CLI-07-generate-crud-contract-tests.md) generate crud tests | READY | none | none |
| [S-CLI-08](S-CLI-08-agents-md-env-vars.md) AGENTS.md env vars | READY | none | none |
| [S-CLI-09](S-CLI-09-gauntlet-install-wheel.md) wheel smoke test gate | READY | none | none |
