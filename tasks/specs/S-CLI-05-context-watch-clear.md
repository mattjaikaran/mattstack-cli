# S-CLI-05: Clear the terminal between context --watch emissions

| Field | Value |
|---|---|
| Spec ID | S-CLI-05 |
| Backlog item | Phase 18E: Clear terminal between emissions, show timestamp |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | 9bf4cfe |
| Branch | agent/S-CLI-05 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `src/mattstack/commands/context.py`, `tests/test_commands/test_context.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 2 |
| Max changed lines | 100 |
| Verification commands | `uv run pytest tests/test_commands/test_context.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3 (table below) |

## Context and verified citations

Verified on `9bf4cfe` (2026-10-26).

- `src/mattstack/commands/context.py:81-107` (`_watch_loop`) re-emits after each change with only a stderr separator (`context.py:91-94`); it never clears the screen.
- No test covers `--watch`.

## Goal and non-goals

In watch mode, before each re-emission, clear the screen only when output goes to stdout (`output is None`) and stdout is a TTY. Never clear when writing to `-o` or a pipe. Keep the existing separator/timestamp. Non-goals: no new dependency (no watchfiles), no change to the polling interval.

## Implementation steps

1. Add the clear in `_watch_loop` using the existing console helper or the ANSI sequence `\033[2J\033[H` on stdout.
2. Add tests: monkeypatch `_watch_snapshot` to return two different snapshots and `time.sleep` to raise `KeyboardInterrupt` on its second call.

Stage only the Files owned, with explicit paths. Commit subject: `feat(context): Clear screen between watch emissions`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | see Verification commands | 0 | TTY stdout, no `-o`: the clear runs once before the re-emission |
| A2 | repo root | see Verification commands | 0 | `isatty()` false: no clear |
| A3 | repo root | see Verification commands | 0 | `-o FILE` set: no clear |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
