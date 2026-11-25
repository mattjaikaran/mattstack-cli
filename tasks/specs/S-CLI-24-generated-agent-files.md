# S-CLI-24: Stop generating CLAUDE.md, .cursorrules and .claude/; delete rules sync

| Field | Value |
|---|---|
| Spec ID | S-CLI-24 |
| Backlog item | Agent layout contract (`docs/agent-layout.md`): AGENTS.md is the only agent instruction file in generated projects |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-24 |
| Depends on | none |
| Conflicts with | S-CLI-15 (`tests/test_post_processors.py`); S-CLI-11, S-CLI-13, S-CLI-26, S-CLI-43 (`src/mattstack/cli.py`); S-CLI-20, S-CLI-26, S-CLI-27, S-CLI-28 (`docs/commands.md`, file-level) |
| Files owned | `src/mattstack/post_processors/consolidate.py`; `src/mattstack/templates/agent_files.py`; `src/mattstack/templates/root_gitignore.py`; `src/mattstack/commands/rules.py`; `src/mattstack/cli.py` (line 58 help text only); `docs/architecture.md` (lines 397-409 only); `tests/test_commands/test_rules.py`; `tests/test_post_processors.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 8 |
| Max changed lines | 320 |
| Verification commands | `uv run python scripts/gauntlet.py --gate install`; `uv run ruff check src/ tests/`; `uv run ruff format --check src/ tests/`; `uv run mypy src/`; `uv run python scripts/check_file_length.py` |
| Acceptance criteria | A1 to A7 (table below) |

## Context and verified citations

Verified on `e89fac4`. Decisions (from the parent): `CLAUDE.md` never exists; `.cursorrules` is no longer written; committed `.claude/skills/<name>` moves to `.agents/skills/<name>` unless a duplicate already exists; `.claude/` and `.cursor/` are gitignored whole; `rules sync` is deleted (clean cutover). `docs/agent-layout.md` is the canonical contract.

- `src/mattstack/post_processors/consolidate.py`: the docstring at lines 14-23 describes keeping `.claude/skills` and removing `CLAUDE.md` and `.cursorrules` only when an `AGENTS.md` exists. `_BACKEND_AGENT_PATHS` is at line 99 (includes `"CLAUDE.md"`). `_drop_agent_duplicates` is at lines 198-217; `_skill_is_duplicate` is at lines 220-224; `_remove` is at lines 231-235. `shutil` is already imported.
- `src/mattstack/templates/agent_files.py`: `CURSOR_ADAPTER` is at lines 19-23. The `agent_files` dict (lines 60-63) includes `".cursorrules": CURSOR_ADAPTER` at line 62.
- `src/mattstack/templates/root_gitignore.py:35` is `.claude/settings.local.json`.
- `src/mattstack/commands/rules.py`: `HARNESS_ADAPTERS` at lines 108-114; `CANONICAL_DIRS` at line 116; `_GENERATED_HEADER` at lines 119-122; `collect_canonical` at line 125; `render_adapter` at line 137; `sync_harness_rules` at line 142; the `sync` command at lines 206-217. The `rules_app` help at line 182 says "...and sync per-harness adapters." `run_rules` (lines 21-105) does not call the sync code.
- `src/mattstack/cli.py:58`: the lazy group help is "Generate AI agent files and harness adapters."
- `docs/architecture.md:397-409` describes the generated consolidation rules.
- `tests/test_commands/test_rules.py`: imports at lines 11 and 15 (`HARNESS_ADAPTERS`, `sync_harness_rules`, and others); lines 93-97 (the CLAUDE.md preservation test and the `[create] .cursorrules` assertion); lines 118-150 (sync and adapter tests).
- `tests/test_post_processors.py`: lines 417-418 (`CLAUDE.md`, `.cursorrules`), 433-447 (`.claude` skill fixtures), 468, 475-480, 506-507, 513-517, and 567-571 (the test that says `CLAUDE.md` is kept without an `AGENTS.md`).
- `scripts/smoke_scaffold.py:36` is a `BACKEND_LEFTOVERS` entry that asserts `CLAUDE.md` is absent. It is consistent with the decision and is not changed here. That file belongs to S-CLI-17.
- Test edits: the behavior these tests assert is being deleted, so the test changes are required by the decision. The repository rule quoted in S-CLI-18 (`repos/mattstack-cli.yml:93`) says not to change `tests/`. That file is not in this checkout and could not be read. Stop condition 4 applies if the parent does not confirm this exception.

## Goal and non-goals

Goal: generated projects receive no `CLAUDE.md`, no `.cursorrules`, and no `.claude/`. Committed skills are moved to `.agents/skills/`. The `rules sync` subcommand and its adapter code are deleted.

Non-goals: no change to `scripts/smoke_scaffold.py` (S-CLI-17); no change to `README.md` (S-CLI-19); no change to `docs/commands.md` (that is S-CLI-25); no change to `CHANGELOG.md` (that is S-CLI-25); no change to `context`, `upgrade`, or the `claude` format (S-CLI-25); no change to `scripts/check_agent_docs.py` or `scripts/gauntlet.py` (S-CLI-23); no commit beyond step 9.

## Implementation steps

1. `consolidate.py`:
   a. Replace the docstring paragraph at lines 14-23 with: committed `.claude/skills/<name>/` move to `.agents/skills/<name>/` unless `.agents/skills/` or `.omp/skills/` already holds that skill, in which case the copy is dropped. Everything else in `.claude/` is dropped, and `.claude/` itself is removed. `CLAUDE.md` and `.cursorrules` are removed unconditionally as legacy files that are never generated.
   b. Rewrite `_drop_agent_duplicates` (lines 198-217) to: remove `CLAUDE.md` and `.cursorrules`; if `.claude` is a symlink or not a directory, remove it and return; for each entry of `.claude/skills` that is a directory and not a symlink, remove it when `_skill_is_duplicate(root, name)` is true, otherwise create `.agents/skills/` with `mkdir(parents=True, exist_ok=True)` and move the entry with `shutil.move`; remove every other entry; finally remove `.claude`.
   c. Keep `_skill_is_duplicate` (lines 220-224) and `_remove` unchanged.
   d. Leave `_BACKEND_AGENT_PATHS` (line 99) unchanged; it removes legacy files.
2. `agent_files.py`: delete the `CURSOR_ADAPTER` constant (lines 19-23) and the `".cursorrules"` entry (line 62). Update the module docstring (line 3) so it no longer names `.cursorrules`.
3. `root_gitignore.py:35`: replace `.claude/settings.local.json` with two lines, `.claude/` and `.cursor/`.
4. `rules.py`: delete `HARNESS_ADAPTERS`, `CANONICAL_DIRS`, `_GENERATED_HEADER`, `collect_canonical`, `render_adapter`, `sync_harness_rules`, and the `sync` command. Change the `rules_app` help at line 182 to "Generate AI agent config files." Remove imports that become unused. Do not change `run_rules`, `_status`, or the gsd path.
5. `cli.py:58`: change the lazy group help to "Generate AI agent files." Change no other line in `cli.py`.
6. `docs/architecture.md` lines 397-409: rewrite the bullets so they state the rules in step 1 (`.claude/skills` moves to `.agents/skills`; `.claude/`, `CLAUDE.md`, and `.cursorrules` are removed; `.cursor/` and the other harness adapters are removed). Change nothing outside that range.
7. `tests/test_commands/test_rules.py`:
   a. Remove the `HARNESS_ADAPTERS` and `sync_harness_rules` imports and any other import used only by deleted tests.
   b. In the dry-run test (lines 93-97), change the `.cursorrules` assertion to `assert "[create] .cursorrules" not in out` and keep the CLAUDE.md preservation assertion.
   c. Delete the tests at lines 118-150 that cover `collect_canonical` and `render_adapter` and `sync_harness_rules`. Keep any `run_rules` tests.
8. `tests/test_post_processors.py`: update the fixtures and assertions at lines 417-418, 433-447, 468, 475-480, 506-507, 513-517, and 567-571. Specifically, `CLAUDE.md` and `.cursorrules` are removed even when no `AGENTS.md` exists; `.claude/skills` that is not a duplicate is moved to `.agents/skills/`; and `.claude/` no longer exists afterwards.
9. Stage only the owned paths by name (no `git add -A`), then commit with subject `feat(generate): Stop generating CLAUDE.md, .cursorrules and .claude`. Stop if the commit is blocked.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `grep -rln "sync_harness_rules\|HARNESS_ADAPTERS\|CURSOR_ADAPTER\|render_adapter\|collect_canonical" src tests; test $? -eq 1` | 0 | No matches |
| A2 | repo root | `uv run mattstack rules sync >/dev/null 2>&1; test $? -ne 0` | 0 | No output |
| A3 | repo root | `uv run python -c "import tempfile,pathlib; from mattstack.post_processors.consolidate import _drop_agent_duplicates as d; r=pathlib.Path(tempfile.mkdtemp()); (r/'.claude/skills/foo').mkdir(parents=True); (r/'.claude/skills/foo/SKILL.md').write_text('x'); (r/'.claude/settings.local.json').write_text('{}'); d(r); assert (r/'.agents/skills/foo/SKILL.md').exists(); assert not (r/'.claude').exists(); print('ok')"` | 0 | Prints `ok` |
| A4 | repo root | `uv run python scripts/gauntlet.py --gate install` | 0 | Gate `install` passes; no pytest run |
| A5 | repo root | `grep -n "cursorrules" src/mattstack/templates/agent_files.py src/mattstack/commands/rules.py; test $? -eq 1` | 0 | No matches |
| A6 | repo root | `grep -n '^\.claude/$\|^\.cursor/$' src/mattstack/templates/root_gitignore.py \| wc -l` | 0 | Prints `2` |
| A7 | repo root | `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/` | 0 | No errors |
| A8 | repo root | `T=$(mktemp -d) && uv run mattstack init demo --preset starter-fullstack -o "$T/out" >/dev/null 2>&1 && test -z "$(find "$T" \( -name CLAUDE.md -o -name .cursorrules -o -name .claude \) -print)" && test -n "$(find "$T" -name .gitignore -exec grep -l "^\.claude/$" {} +)" && echo ok` | 0 | Prints `ok`; no `CLAUDE.md`, `.cursorrules` or `.claude` in generated output; a generated `.gitignore` contains `.claude/` |

## Stop conditions and PR evidence

Stop, and report without further edits, when: (1) `consolidate.py` no longer contains the `_drop_agent_duplicates` body at lines 198-217 (the base has changed); (2) `rules.py` contains a caller of `sync_harness_rules` outside the sync command; (3) a change needs a file outside Files owned; (4) the parent has not confirmed the test-edit exception described in the context section. The report lists the base and head SHA, the changed-line count, and each criterion with its observed result.
