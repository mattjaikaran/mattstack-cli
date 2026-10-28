# S-CLI-10: Gate 10 checks the mistyped-group suggestion

| Field | Value |
|---|---|
| Spec ID | S-CLI-10 |
| Backlog item | `tasks/todo.md:11-15` (release process): the INSTALL gate must also run a mistyped group that prints "Did you mean" |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | 9337e65 |
| Branch | agent/S-CLI-10 |
| Depends on | S-CLI-09 |
| Conflicts with | S-CLI-09 |
| Files owned | `scripts/gauntlet.py`, `tests/test_gauntlet_script.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 2 |
| Max changed lines | 100 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_gauntlet_script.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3 (table below) |

## Context and verified citations

Verified on `9337e65` (2026-10-28).

- `tasks/todo.md:11-15` asks gate 10 to run `mattstack --help`, `mattstack sync --help` and a mistyped group that must print "Did you mean". S-CLI-09 adds the first two runs; it does not add the third.
- `scripts/gauntlet.py:192-198` (`_gate_install`) is rewritten by S-CLI-09. Read the post-S-CLI-09 version, with its venv install and its `_run` calls.
- `_run(cmd, cwd, timeout)` returns `(exit_code, combined_output)` (`scripts/gauntlet.py:53`).
- `mattstack sync2` exits non-zero and prints `No such command 'sync2'. Did you mean 'sync'?` (observed with `uv run mattstack sync2` on `9337e65`). `sync` is a lazy group (`src/mattstack/cli.py:43-47`), so the suggestion proves lazy groups are listed in the installed wheel.
- `tests/test_gauntlet_script.py` is created by S-CLI-09 (its loader and recorded-argv fake `_run`). Extend it; do not duplicate the loader.

## Goal and non-goals

After the two help runs, gate 10 runs the installed `mattstack` with `sync2` and passes only when the exit code is non-zero and the output contains `Did you mean`. A zero exit, or a non-zero exit without the suggestion, fails the gate and prints the output. Non-goals: no other gate, no CLAUDE.md change, no real network install (agent runs have no network; the mocked `_run` is the proof).

## Implementation steps

1. In `_gate_install`, after the `sync --help` run, call `_run` with the venv's `mattstack` and `sync2`; require `code != 0` and `"Did you mean" in out`; print `out` on failure.
2. Extend the fake `_run` in `tests/test_gauntlet_script.py` to return canned output per argv; add three tests (suggestion present, suggestion missing, exit zero).

Stage only the Files owned, with explicit paths. Commit subject: `fix(gauntlet): Check the mistyped-group suggestion in gate 10`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | see Verification commands | 0 | Recorded argv: the last call is the venv `mattstack` with `sync2`, after `sync --help` |
| A2 | repo root | see Verification commands | 0 | `_gate_install()` returns True when that call exits 2 with output containing `Did you mean 'sync'` |
| A3 | repo root | see Verification commands | 0 | `_gate_install()` returns False when that call exits 0, or exits 2 without `Did you mean` |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
