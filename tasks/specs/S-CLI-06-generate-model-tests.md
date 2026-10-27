# S-CLI-06: Add generate model contract tests

| Field | Value |
|---|---|
| Spec ID | S-CLI-06 |
| Backlog item | Phase 16E / 21: tests for generate model (fields guard, admin files, base class) |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | 9bf4cfe |
| Branch | agent/S-CLI-06 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `tests/test_commands/test_generate_model.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 1 |
| Max changed lines | 200 |
| Verification commands | `uv run pytest tests/test_commands/test_generate_model.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3 (table below) |

## Context and verified citations

Verified on `9bf4cfe` (2026-10-26).

- The behavior exists but `generate model` has no test; `tests/test_commands/test_generate.py:22-27` only wraps `crud(...)` and `page(...)`.
- Fields guard: `src/mattstack/commands/generate_crud.py:140-142` raises the "No --fields given" error.
- Admin package and `__init__` exports: `src/mattstack/commands/codegen/crud_backend.py:74-85`.
- Base class and timestamps: `src/mattstack/commands/codegen/django_models.py:46-88`.
- Fixture: `make_project` in `tests/test_commands/conftest.py`; base-model pattern at `tests/test_commands/test_generate.py:104`.

## Goal and non-goals

A new test module proves the `generate model` contract. Test-only: if a test exposes a bug, stop and report it; do not change `src/`.

## Implementation steps

1. Create `tests/test_commands/test_generate_model.py`; invoke `generate_app` with `["model", "Product", "--path", root, ...]`.

Stage only the Files owned, with explicit paths. Commit subject: `test(generate): Cover generate model contract`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | see Verification commands | 0 | No `--fields`/`--empty`: exit 1, output contains `No --fields given`, no files written |
| A2 | repo root | see Verification commands | 0 | `-f "title:str"`: `backend/core/admin/product_admin.py` exists; `core/models/__init__.py` exports `Product`; `core/admin/__init__.py` exports `ProductAdmin` |
| A3 | repo root | see Verification commands | 0 | With `core/models/base.py` defining `AbstractBaseModel`: model inherits `(AbstractBaseModel)` and has no `created_at =`/`updated_at =` |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
