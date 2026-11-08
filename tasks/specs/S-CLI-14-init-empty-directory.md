# S-CLI-14: Let init scaffold into an existing empty directory

| Field | Value |
|---|---|
| Spec ID | S-CLI-14 |
| Backlog item | GitHub issue #48: `mattstack init NAME -o DIR` refuses when `DIR/NAME` exists, even when it is empty; accept an empty directory and keep refusing a non-empty one |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | 599d338 |
| Branch | agent/S-CLI-14 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `src/mattstack/commands/init.py`, `src/mattstack/generators/base.py`, `tests/test_commands/test_init.py`, `tests/test_generators/test_base.py`, `tests/test_generators/test_fullstack.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 5 |
| Max changed lines | 120 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_commands/test_init.py tests/test_commands/test_init_safety.py tests/test_generators/test_base.py tests/test_generators/test_fullstack.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3; A4 (table below) |

## Context and verified citations

Verified on `599d338` (2026-11-08).

- `src/mattstack/commands/init.py:342` (`_generate`) rejects any existing path: `if config.path.exists() and not config.dry_run:` then `print_error(f"Directory already exists: ...")` and `typer.Exit(code=1)`. `init.py` is exactly 400 lines, the limit enforced by `scripts/check_file_length.py` (`MAX_LINES = 400`). The change there must not add a line.
- `src/mattstack/generators/base.py:45-57` (`create_root_directory`) calls `mkdir(parents=True, exist_ok=False)`, sets `_owns_root = True`, and returns False on `FileExistsError`.
- `src/mattstack/generators/base.py:222-226` (`cleanup`) removes the whole project directory only when `_owns_root` is set. A directory the user created must survive a failed run; `tests/test_generators/test_base.py:124` (`test_cleanup_preserves_existing_directory`) pins that for a non-empty directory.
- Three tests pin the refusal of an existing empty directory and must change: `tests/test_commands/test_init.py:74` (`test_generate_existing_dir_exits`), `tests/test_generators/test_base.py:150` (`test_create_root_directory_exists`) and `tests/test_generators/test_fullstack.py:179` (`test_fullstack_existing_dir_fails`). `tests/test_commands/test_init_safety.py:51` (`test_failed_generator_preserves_existing_directory`) uses a non-empty directory and stays valid.

## Goal and non-goals

`init` accepts a project path that is an empty directory (no entries at all, hidden files included) and scaffolds into it. A non-empty directory, or a path that is a file, is still refused with `Directory already exists`. If a run into a pre-existing empty directory fails, cleanup removes what the run wrote but keeps the directory itself. Non-goals: no merge into a non-empty directory, no `--force`, no change to dry-run behaviour.

## Implementation steps

1. In `src/mattstack/generators/base.py`, add a module-level `project_dir_is_free(path: Path) -> bool`: True when the path does not exist, or is a directory with no entries.
2. In `create_root_directory`, use it: refuse (print the same error, return False) when it is False; otherwise `mkdir(parents=True, exist_ok=True)`. Record whether the directory existed before. Set `_owns_root` only when the run created it. In `cleanup`, when the run did not create the root but it was empty at the start, delete the entries the run created (children of the root) and keep the root.
3. In `src/mattstack/commands/init.py:342`, replace the condition with `not project_dir_is_free(config.path) and not config.dry_run`, imported from `mattstack.generators.base` (add it to the `mattstack.generators` import block, alphabetically before `mattstack.generators.backend_only`). That import adds one line, so delete the blank line before `generator: FullstackGenerator | BackendOnlyGenerator | FrontendOnlyGenerator` in `_generate` (`init.py:349`, `init.py:350` once the import exists); a single blank line removed inside a function survives `ruff format --check`. `init.py` must stay at 400 lines; A4 fails if you add the import without the deletion.
4. Update the three tests listed above to use a non-empty directory (write a sentinel file) so they keep pinning the refusal. Add tests: `_generate` and `create_root_directory` accept an empty directory; a failed run into an empty directory leaves the directory and removes the run's files.

Stage only the Files owned, with explicit paths. Commit subject: `feat(init): Accept an existing empty project directory`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_generators/test_base.py -q` | 0 | `create_root_directory()` returns True for an existing empty directory and False for a directory holding one file |
| A2 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_commands/test_init.py -q` | 0 | `_generate` raises `Exit` for a non-empty existing directory and does not for an empty one (generator patched) |
| A3 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_generators/test_base.py tests/test_commands/test_init_safety.py -q` | 0 | After a failed run into a pre-existing empty directory, the directory exists and is empty; a non-empty directory's files are untouched |
| A4 | repo root | `uv run python scripts/check_file_length.py` | 0 | `File length check passed` (`init.py` still at most 400 lines) |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
