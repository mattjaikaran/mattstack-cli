# S-CLI-03: Detect @jwt_required on django-matt endpoints

| Field | Value |
|---|---|
| Spec ID | S-CLI-03 |
| Backlog item | Audit false positive: 'No auth on write endpoint' for generated django-matt routes |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | 9bf4cfe |
| Branch | agent/S-CLI-03 |
| Depends on | S-CLI-02 |
| Conflicts with | S-CLI-02 |
| Files owned | `src/mattstack/parsers/django_routes.py`, `tests/test_parsers/test_django_matt_routes.py`, `tests/test_auditors/test_endpoints.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 3 |
| Max changed lines | 120 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_parsers/test_django_matt_routes.py tests/test_auditors/test_endpoints.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3 (table below) |

## Context and verified citations

Verified on `9bf4cfe` (2026-10-26).

- `src/mattstack/parsers/django_routes.py:276-280` (`MATT_METHOD_RE`) reads `auth=` only inside `@get(...)`/`@post(...)`. These line numbers are as of 9bf4cfe; after S-CLI-02 merges they shift by its added lines, so locate `MATT_METHOD_RE` by name (a shift alone is not a wrong citation).
- The django-matt generator guards routes with a separate decorator: `@post("/")` then `@jwt_required` (`src/mattstack/commands/codegen/django_matt_api.py:86`).
- `src/mattstack/auditors/endpoints.py:92-99` then warns "No auth on write endpoint" for generated write routes.
- `django_routes.py` is 367 lines before S-CLI-02, which may grow it to 383; the file-length gate allows 400. Budget: this spec grows `django_routes.py` by at most 16 lines (`wc -l` at most 400 after S-CLI-02). It depends on S-CLI-02 so the two never run at once.

## Goal and non-goals

A django-matt endpoint whose decorator block (between the method decorator and its `def`) contains `@jwt_required` parses with `auth=True`, and the endpoint auditor no longer reports it. Non-goals: no ninja-extra changes, no new auth decorator names beyond `@jwt_required`.

## Implementation steps

1. After each `MATT_METHOD_RE` match, scan the decorator lines up to the next `def`/`async def`; set auth when one is `@jwt_required`.
2. Add parser tests and an auditor regression test.

Stage only the Files owned, with explicit paths. Commit subject: `fix(parsers): Treat @jwt_required as endpoint auth`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | see Verification commands | 0 | `@post("/")` + `@jwt_required` + `async def create_x`: endpoint `.auth is True` |
| A2 | repo root | see Verification commands | 0 | `@get("/")` alone: `.auth is False` |
| A3 | repo root | see Verification commands | 0 | Endpoint auditor on a django-matt project whose write routes use `@jwt_required`: no finding contains `No auth on write endpoint` |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
