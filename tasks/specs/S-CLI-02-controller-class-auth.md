# S-CLI-02: Read class-level auth on @api_controller

| Field | Value |
|---|---|
| Spec ID | S-CLI-02 |
| Backlog item | Phase 18D: Extract controller prefix, tags, auth at class level |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | 9bf4cfe |
| Branch | agent/S-CLI-02 |
| Depends on | none |
| Conflicts with | S-CLI-03 |
| Files owned | `src/mattstack/parsers/django_routes.py`, `tests/test_parsers/test_django_routes.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 2 |
| Max changed lines | 120 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_parsers/test_django_routes.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3 (table below) |

## Context and verified citations

Verified on `9bf4cfe` (2026-10-26).

- `src/mattstack/parsers/django_routes.py:150-154` (`API_CONTROLLER_RE`) captures only the prefix and tags.
- Endpoint auth comes only from the `@http_*` arguments (`django_routes.py:197-198`).
- The generator puts auth on the class for owned resources: `src/mattstack/commands/codegen/django_api.py:100-101,122` (`class_auth = ["auth=JWTAuth()"] if owned`).
- So `context routes` reports `auth: False` for generated owned endpoints (`src/mattstack/commands/context_builders.py:266`).
- `django_routes.py` is 367 lines; the file-length gate allows 400, and S-CLI-03 also adds code to it. Budget: this spec grows `django_routes.py` by at most 16 lines (`wc -l` at most 383).

## Goal and non-goals

An endpoint inside an `@api_controller(..., auth=X)` class parses with `auth=True` unless its own `@http_*` decorator sets `auth=None`. Non-goals: no change to django-matt parsing (S-CLI-03), output formats or auditors.

## Implementation steps

1. Capture the full `@api_controller(...)` argument text and detect `auth=` with a value other than `None`.
2. Record class-level auth on the controller; set each endpoint's auth to its own `auth=` when given (`auth=None` means False), else the class value.
3. Add tests to `tests/test_parsers/test_django_routes.py`.

Stage only the Files owned, with explicit paths. Commit subject: `fix(parsers): Read class-level controller auth`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | see Verification commands | 0 | `@api_controller("/p", tags=["P"], auth=JWTAuth())` with plain `@http_get("/")`: endpoint `.auth is True` |
| A2 | repo root | see Verification commands | 0 | Same class, `@http_get("/open", auth=None)`: endpoint `.auth is False` |
| A3 | repo root | see Verification commands | 0 | The tag `P` and prefix `/p` still parse; existing tests pass |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
