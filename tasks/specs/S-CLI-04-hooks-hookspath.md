# S-CLI-04: Handle core.hooksPath in hooks install and status

| Field | Value |
|---|---|
| Spec ID | S-CLI-04 |
| Backlog item | hooks install/status: respect core.hooksPath |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | 9bf4cfe |
| Branch | agent/S-CLI-04 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `src/mattstack/commands/hooks.py`, `tests/test_commands/test_hooks.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 2 |
| Max changed lines | 150 |
| Verification commands | `uv run pytest tests/test_commands/test_hooks.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3 (table below) |

## Context and verified citations

Verified on `9bf4cfe` (2026-10-26).

- `src/mattstack/commands/hooks.py:152-161` runs `pre-commit install --hook-type ...` without checking `core.hooksPath`; pre-commit refuses to install when it is set.
- `status` hardcodes `hooks_dir = project / ".git" / "hooks"` (`hooks.py:203`) and keeps its own hook list (`hooks.py:209-217`).
- `git_hooks_dir()` (`hooks.py:99-108`) already resolves the hooks directory through git, including `core.hooksPath` and worktrees.

## Goal and non-goals

`hooks install` exits 1 with an error that names the `core.hooksPath` value and the fix (`git config --unset core.hooksPath`) when it is set, and never runs pre-commit or changes git config. `hooks status` reads the directory from `git_hooks_dir()` and the hook names from `_GIT_HOOK_TYPES`. Decision taken: refuse; do not unset the user's config.

## Implementation steps

1. Before install, read `git config --get core.hooksPath`; if set, print the error and exit 1.
2. In `status`, use `git_hooks_dir()` and `_GIT_HOOK_TYPES`.
3. Update the status tests that build `.git/hooks` without a repository (`tests/test_commands/test_hooks.py:141-188`) to use `git init`; add the new tests.

Stage only the Files owned, with explicit paths. Commit subject: `fix(hooks): Respect core.hooksPath`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | see Verification commands | 0 | With `core.hooksPath .githooks`: `install` exits 1, output contains `core.hooksPath`, the fake pre-commit binary never runs |
| A2 | repo root | see Verification commands | 0 | With `.githooks/pre-commit` containing `pre-commit`: `status` reports it installed |
| A3 | repo root | see Verification commands | 0 | Without `core.hooksPath`: existing install/status behavior and tests pass |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
