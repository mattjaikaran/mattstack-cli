# S-CLI-15: Document the pinned openapi-ts in frontend/DEPENDENCIES.md

| Field | Value |
|---|---|
| Spec ID | S-CLI-15 |
| Backlog item | GitHub issue #47: init pins `@hey-api/openapi-ts` into `frontend/package.json` without a `frontend/DEPENDENCIES.md` entry, so `bun run check-dependencies` fails with `MISSING_DEPENDENCY_ENTRY` on a fresh scaffold |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | 599d338 |
| Branch | agent/S-CLI-15 |
| Depends on | none |
| Conflicts with | S-CLI-16 |
| Files owned | `src/mattstack/post_processors/frontend_config.py`, `src/mattstack/post_processors/frontend_openapi_pin.py` (new), `tests/test_post_processors.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 3 |
| Max changed lines | 160 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_post_processors.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3; A4 (table below) |

## Context and verified citations

Verified on `599d338` (2026-11-08).

- `src/mattstack/post_processors/frontend_config.py:114-133` (`_pin_openapi_generator`) writes `@hey-api/openapi-ts` into `frontend/package.json` (`HEY_API_VERSION` is `0.99.0`, `src/mattstack/parsers/openapi_spec.py:28`) and never touches `frontend/DEPENDENCIES.md`. It returns early at line 129-130 when the frontend already has an exact pin.
- It is called from `setup_frontend_monorepo` at `frontend_config.py:44-45` (`if config.has_backend:` then `_pin_openapi_generator(config)`).
- `frontend_config.py` is 399 lines; `scripts/check_file_length.py` fails above 400 (`MAX_LINES = 400`). The new logic therefore lives in a new module, and `_pin_openapi_generator` moves there.
- The boilerplates' gate (`frontend/scripts/check_dependencies.ts`, seen in a scaffold at `/private/tmp/pr104-verify/frontend/`) reads every `| name |` table row of `DEPENDENCIES.md` and requires one for each `package.json` dependency and devDependency. The file is a Markdown table with the header `| Package | Version |`, a `| --- | --- |` separator, and rows sorted by package name (for example `| @tanstack/react-query | 5.100.9 |`).
- `tests/test_post_processors.py:78` (`_frontend(config, files)`) writes files into the frontend directory. `tests/test_post_processors.py:225` (`test_openapi_generator_is_pinned_exactly`) covers the three pin cases through `setup_frontend_monorepo` and must keep passing unchanged.

## Goal and non-goals

After `setup_frontend_monorepo`, when `frontend/DEPENDENCIES.md` exists, it has exactly one row for `@hey-api/openapi-ts` whose version is the exact version now in `frontend/package.json`, in sorted position. A missing `DEPENDENCIES.md` is left missing (the boilerplate does not use the gate). Non-goals: no change to which version is pinned, no removal of the injection (issue #54 covers that), no `bun.lock` change.

## Implementation steps

1. Create `src/mattstack/post_processors/frontend_openapi_pin.py`. Move `_pin_openapi_generator` into it as `pin_openapi_generator(config)`, unchanged in behaviour, then add `_document_dependency(config, version)`. It runs after the pin (also when the early return keeps an existing exact pin), reads the pinned version from `package.json`, and edits `DEPENDENCIES.md`: replace the version cell of an existing `@hey-api/openapi-ts` row, otherwise insert a row after the last table row whose name sorts before it (before the first row that sorts after it). Keep the file's trailing newline and every other line byte-identical.
2. In `frontend_config.py`, import `pin_openapi_generator`, call it at the existing call site, delete the old function, and drop imports that become unused (`EXACT_VERSION`, `HEY_API_NAME`, `HEY_API_VERSION`, `write_package_json`, if nothing else uses them).
3. Add tests in `tests/test_post_processors.py`: a `DEPENDENCIES.md` without the package gets a sorted row; a stale row is updated to the pinned version; a second `setup_frontend_monorepo` run adds no duplicate row; no `DEPENDENCIES.md` means none is created.

Stage only the Files owned, with explicit paths. Commit subject: `fix(frontend): Document the pinned openapi-ts in DEPENDENCIES.md`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_post_processors.py -q` | 0 | `DEPENDENCIES.md` containing rows `@a/x` and `zod` gets one `@hey-api/openapi-ts` row with version `0.99.0` between them |
| A2 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_post_processors.py -q` | 0 | A frontend that pins `0.98.0` exactly gets a `0.98.0` row; an existing `0.1.0` row becomes `0.99.0` for a missing pin |
| A3 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_post_processors.py -q` | 0 | Running `setup_frontend_monorepo` twice leaves one row; with no `DEPENDENCIES.md` none is created; `test_openapi_generator_is_pinned_exactly` still passes |
| A4 | repo root | `uv run python scripts/check_file_length.py` | 0 | `File length check passed` |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
