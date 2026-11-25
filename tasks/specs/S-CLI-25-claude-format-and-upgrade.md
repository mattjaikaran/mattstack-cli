# S-CLI-25: Delete the claude context format and claude_md key; retire CLAUDE.md in upgrade; changelog

| Field | Value |
|---|---|
| Spec ID | S-CLI-25 |
| Backlog item | GitHub issue #134; Agent layout contract (`docs/agent-layout.md`): retire `CLAUDE.md` and the Claude-specific surfaces |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-25 |
| Depends on | none |
| Conflicts with | S-CLI-05 (`src/mattstack/commands/context.py`, `tests/test_commands/test_context.py`); S-CLI-20, S-CLI-26, S-CLI-27, S-CLI-28 (`docs/commands.md`, file-level) |
| Files owned | `src/mattstack/commands/context_format.py`; `src/mattstack/commands/context.py`; `src/mattstack/commands/context_builders.py`; `src/mattstack/commands/upgrade.py`; `docs/commands.md` (the `rules` and `context` sections only); `CHANGELOG.md`; `tests/test_commands/test_context.py`; `tests/test_context_commands.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 8 |
| Max changed lines | 260 |
| Verification commands | `uv run python scripts/gauntlet.py --gate install`; `uv run ruff check src/ tests/`; `uv run ruff format --check src/ tests/`; `uv run mypy src/` |
| Acceptance criteria | A1 to A7 (table below) |

## Context and verified citations

Verified on `e89fac4`. The canonical contract is `docs/agent-layout.md` (present). Decisions (from the parent): the `claude` context format is deleted, with no alias (clean cutover, recorded in a CHANGELOG `Removed` entry); the context key `claude_md` becomes `agents_md`; upgrade drops `CLAUDE.md` from `SKIP_FILES` and does not recreate it, using a retired set (approved).

- `src/mattstack/commands/context_format.py`: the module docstring (line 1) says "markdown, JSON, and Claude XML". `FORMATS = ("markdown", "json", "claude")` is at line 10. `format_context_claude` is at lines 92-93. The dispatch is `if fmt == "claude":` at line 163, which calls it at line 164.
- `src/mattstack/commands/context.py:26`: the `context_app` help is "Dump project context for AI agents (Claude, Cursor, etc.)." `_FMT_HELP` at line 149 is "Output format: markdown (default), json, claude". S-CLI-05 owns this file.
- `src/mattstack/commands/context_builders.py:42`: `"claude_md": (root / "CLAUDE.md").exists(),`. No `src/` caller reads that key; `tests/test_commands/test_context.py:61` asserts it.
- `src/mattstack/commands/upgrade.py:43`: `SKIP_FILES` includes `"CLAUDE.md"`. Line 46 is `IGNORE_DIRS`, which has no `.claude`. Line 285 is `_comparable`: `if any(part in IGNORE_DIRS for part in rel.parts) or rel.name in SKIP_FILES:`. Upgrade does not call consolidate, so dropping `CLAUDE.md` from `SKIP_FILES` alone would let upstream `CLAUDE.md` be copied back. The retired set closes that path.
- `docs/commands.md`: the code block at lines 786-790 lists `mattstack rules  # AGENTS.md, .cursorrules` and `mattstack rules sync`. Lines 792-795 describe `.cursorrules` and `rules sync`. The `context` section (around line 803) says "Markdown, JSON, or Claude format" and has the example `mattstack context stack . --format claude`.
- `CHANGELOG.md`: `## [Unreleased]` exists at line 7 with a `### Added` section. This spec adds `### Removed` after it.
- `tests/test_context_commands.py`: line 20 imports `format_context_claude`; lines 280-323 hold three `format_context_claude` tests.
- `tests/test_commands/test_context.py`: line 20 imports `format_context_claude`; line 49 writes `CLAUDE.md` in a fixture; line 61 asserts `comps["claude_md"] is True`; lines 228-245 hold the XML test that calls `format_context_claude`.
- `tests/test_commands/test_upgrade.py:189-195` loops over `SKIP_FILES`, so it still passes after `CLAUDE.md` moves out of that set.
- Test edits: the deleted format and key are asserted by these tests, so the test changes are required by the decision. The same repository-rule caveat as in S-CLI-24 applies. If the parent has not confirmed the test-edit exception, stop.

## Goal and non-goals

Goal: the `claude` context format, the `claude_md` key, and the `rules sync` description are gone from code and docs. Upgrade never copies `CLAUDE.md` back, and it ignores `.claude/`. The CHANGELOG records the removals.

Non-goals: no change to `rules sync` code (deleted in S-CLI-24); no change to `README.md` (S-CLI-19 owns it, and the parent said no README edits in this pass; `README.md:241` still says "sync harness adapters" and must be fixed separately); no change to `cli.py` (S-CLI-24 owns line 58); no change to `docs/architecture.md` (S-CLI-24); no change to `scripts/` (S-CLI-23 and S-CLI-17); no commit beyond step 9.

## Implementation steps

1. `context_format.py`: delete `format_context_claude` (lines 92-93 and its body up to the next top-level definition), its dispatch at lines 163-164, and the `"claude"` entry in `FORMATS`. Change the module docstring to "markdown and JSON, plus token budgeting."
2. `context.py`: change the help at line 26 to "Dump project context for AI agents." Change `_FMT_HELP` at line 149 to "Output format: markdown (default), json". Change no other line.
3. `context_builders.py:42`: rename the key to `"agents_md": (root / "AGENTS.md").exists(),`.
4. `upgrade.py`:
   a. Remove `"CLAUDE.md"` from `SKIP_FILES` (line 43).
   b. Add `RETIRED_FILES: set[str] = {"CLAUDE.md"}` next to `SKIP_FILES`, with a comment that these are files mattstack no longer generates and that upgrade must not copy back.
   c. Add `".claude"` to `IGNORE_DIRS` (line 46).
   d. In `_comparable` (line 285), return False when `rel.name in RETIRED_FILES`. Keep the existing checks.
5. `docs/commands.md`, `rules` section (about lines 786-795): change the first code line to `mattstack rules             # AGENTS.md`; delete the `mattstack rules sync` line; delete the sentence about `.cursorrules`; delete the sentence about `rules sync` and its `--dry-run`. Keep `--gsd`, `--force`, and the `.mcp.json` text. In the `context` section (about lines 803-805), change "Markdown, JSON, or Claude format" to "Markdown or JSON", and change the example `--format claude` to `--format json`. Change nothing outside the `rules` and `context` sections.
6. `CHANGELOG.md`: under `## [Unreleased]`, after the `### Added` block, add `### Removed` with these bullets: `mattstack rules sync` and its per-harness adapters; `.cursorrules` and `CLAUDE.md` generation, with `.claude/` and `.cursor/` now gitignored whole; committed `.claude/skills/` moves to `.agents/skills/`; the `claude` value for `mattstack context --format`; the `claude_md` key in context output, renamed `agents_md`.
7. `tests/test_context_commands.py`: remove the `format_context_claude` import (line 20) and delete the three tests at lines 280-323.
8. `tests/test_commands/test_context.py`: remove the `format_context_claude` import (line 20). In the fixture at line 49, write `AGENTS.md` instead of `CLAUDE.md`. At line 61, assert `comps["agents_md"] is True`. Delete the XML test that uses `format_context_claude` (around lines 228-245).
9. Stage only the owned paths by name (no `git add -A`), then commit with subject `feat(context): Remove claude format and retire CLAUDE.md in upgrade`. Stop if the commit is blocked.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `grep -rn "format_context_claude\|claude_md\|\"claude\"" src tests; test $? -eq 1` | 0 | No matches |
| A2 | repo root | `uv run mattstack context stack . --format claude >/dev/null 2>&1; test $? -ne 0` | 0 | No output |
| A3 | repo root | `uv run python -c "from pathlib import Path; from mattstack.commands.upgrade import SKIP_FILES, RETIRED_FILES, IGNORE_DIRS, _comparable; assert 'CLAUDE.md' not in SKIP_FILES; assert 'CLAUDE.md' in RETIRED_FILES; assert '.claude' in IGNORE_DIRS; assert _comparable(Path('x/CLAUDE.md'), Path('CLAUDE.md')) is False; print('ok')"` | 0 | Prints `ok` |
| A4 | repo root | `uv run python scripts/gauntlet.py --gate install` | 0 | Gate `install` passes; no pytest run |
| A5 | repo root | `grep -n "rules sync" docs/commands.md; test $? -eq 1` | 0 | No matches |
| A6 | repo root | `grep -n "^### Removed" CHANGELOG.md` | 0 | Prints one line, after `## [Unreleased]` |
| A7 | repo root | `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/` | 0 | No errors |

## Stop conditions and PR evidence

Stop, and report without further edits, when: (1) `CHANGELOG.md` has no `## [Unreleased]` heading (the base has changed); (2) `upgrade.py` no longer has `SKIP_FILES` at line 43 and `_comparable` at line 285 (the base has changed); (3) a change needs a file outside Files owned; (4) the parent has not confirmed the test-edit exception. The report lists the base and head SHA, the changed-line count, and each criterion with its observed result. Also report `README.md:241` as a follow-up for S-CLI-19 or the parent.
