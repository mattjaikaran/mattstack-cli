# S-CLI-07: Add generate crud output contract tests

| Field | Value |
|---|---|
| Spec ID | S-CLI-07 |
| Backlog item | Phase 21: integration test for generate crud output |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | 9bf4cfe |
| Branch | agent/S-CLI-07 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `tests/test_commands/test_generate_crud_contract.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 1 |
| Max changed lines | 200 |
| Verification commands | `uv run pytest tests/test_commands/test_generate_crud_contract.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3; A4 (table below) |

## Context and verified citations

Verified on `9bf4cfe` (2026-10-26).

- No test asserts the `@http_*` controller decorators, the all-optional `UpdateSchema`, or `id`/`created_at`/`updated_at` on `ResponseSchema` (`src/mattstack/commands/codegen/django_models.py:172-189`).
- No test asserts the hooks, list component and `--with-tests` outputs (`src/mattstack/commands/codegen/crud_frontend.py:113-169`, `src/mattstack/commands/codegen/crud_backend.py:95-100`).
- No test compiles the generated Python.
- Helper `crud(...)`: `tests/test_commands/test_generate.py:22-27` (copy it; do not import from or edit that file).

## Goal and non-goals

A new test module proves the `generate crud` output contract. Test-only: if a test exposes a bug, stop and report it.

## Implementation steps

1. Create `tests/test_commands/test_generate_crud_contract.py`; run `crud(root, "-f", "title:str price:decimal", "--with-tests")`.

Stage only the Files owned, with explicit paths. Commit subject: `test(generate): Cover generate crud output contract`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | see Verification commands | 0 | Controller matches `@http_(get|post|put|delete)` |
| A2 | repo root | see Verification commands | 0 | Every `ProductUpdateSchema` field ends in `None = None`; `ProductResponseSchema` has `id`, `created_at`, `updated_at` |
| A3 | repo root | see Verification commands | 0 | Frontend hooks file, `ProductList` component, `ProductList.test.tsx` and `core/tests/test_product_api.py` exist |
| A4 | repo root | see Verification commands | 0 | `compile(text, path, "exec")` succeeds for every new `.py` under `backend/` |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
