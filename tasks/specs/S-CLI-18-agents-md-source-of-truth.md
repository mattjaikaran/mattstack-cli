# S-CLI-18: Make AGENTS.md the single agent instruction file and check its links

| Field | Value |
|---|---|
| Spec ID | S-CLI-18 |
| Backlog item | GitHub issue #95: move agent instructions to AGENTS.md (`CLAUDE.md` imports it) and harden agent context with a link check in a pre-commit hook |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | 4215076 |
| Branch | agent/S-CLI-18 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `tests/test_agent_docs_script.py` (new) |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | S |
| Max files | 1 |
| Max changed lines | 150 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_agent_docs_script.py -q`; `uv run python scripts/check_agent_docs.py`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3; A4; A5 (table below) |

## Context and verified citations

Verified on `4215076` (2026-11-12).

- PR #102 (merged, branch `agent/issue-97`) already delivered steps 1-4 on `main`: `AGENTS.md` has the seven `##` headings, `CLAUDE.md` is exactly `@AGENTS.md`, `scripts/check_agent_docs.py` defines `check` and `main`, and `.pre-commit-config.yaml:20` defines the `agent-docs` hook. Do not redo these steps.
- `tasks/todo.md:5-7` states the testing rule ("Do not generate bulk tests") and `tasks/todo.md:51-54` states that a test is added only for a consumer-visible contract.
- `tests/test_gauntlet_script.py:14-28` shows how tests load a script with `importlib.util.spec_from_file_location`; follow it.

## Goal and non-goals

`AGENTS.md` at the repository root is the one source of agent instructions, `CLAUDE.md` only imports it, and a script catches a broken link or a missing required heading before commit. Non-goals: no nested `AGENTS.md` (no package has its own commands or rules), no skills directory, no change to `tasks/specs/README.md`, no generated-template change, no addition to the gauntlet, no hosted CI.

## Implementation steps

1. Create `tests/test_agent_docs_script.py` that loads `scripts/check_agent_docs.py` as `tests/test_gauntlet_script.py` does and calls `check(tmp_path)`. The signature is `check(root: Path) -> list[str]`: it reads only `root` and returns one `<file>: <problem>` string per problem. Build each tree with the seven headings in `REQUIRED_HEADINGS` as `## ` lines. Cover: a valid tree returns `[]`; a tree missing one required heading names `AGENTS.md` and that heading; a `CLAUDE.md` whose first non-blank line is prose fails; a relative link to a missing file is named; a link inside a fenced block and an `https://` link are ignored; `CONTRIBUTING.md` is skipped when absent and checked when present.

Stage only the Files owned, with explicit paths. Commit subject: `test(agents): Cover the agent docs check`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `cat CLAUDE.md` | 0 | Output is exactly `@AGENTS.md` |
| A2 | repo root | `uv run python scripts/check_agent_docs.py` | 0 | One confirmation line; no problems listed |
| A3 | repo root | `grep -c '^## ' AGENTS.md` | 0 | Prints a count of at least 7 (the seven required headings) |
| A4 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_agent_docs_script.py -q` | 0 | All tests pass |
| A5 | repo root | `grep -c 'agent-docs' .pre-commit-config.yaml` | 0 | Prints a count of at least 1 |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a new dependency, or a check that fails outside your change. Commit nothing and report the exact discrepancy. The PR body lists the spec ID, base and head SHA, owned files with changed-line counts, and each criterion with its observed result.
