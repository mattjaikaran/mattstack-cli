# S-CLI-08: Correct backend env vars in generated AGENTS.md

| Field | Value |
|---|---|
| Spec ID | S-CLI-08 |
| Backlog item | Generated AGENTS.md lists DATABASE_URL, which Django settings ignore |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | 9bf4cfe |
| Branch | agent/S-CLI-08 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `src/mattstack/templates/stack_facts.py`, `tests/test_templates/test_templates.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 2 |
| Max changed lines | 80 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_templates/test_templates.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2 (table below) |

## Context and verified citations

Verified on `9bf4cfe` (2026-10-26).

- `src/mattstack/templates/stack_facts.py:74` sets `_DJANGO_ENV` to `DATABASE_URL`, `SECRET_KEY`, `REDIS_URL` (if Redis); it is used for Django (`stack_facts.py:106`) and FastAPI (`stack_facts.py:150`).
- Django settings read `DB_*` and ignore `DATABASE_URL` (`stack_facts.py:69-70`, `src/mattstack/templates/root_env.py:99-100`, `src/mattstack/templates/deploy_runtime.py:41`).
- FastAPI requires `JWT_SECRET_KEY` (`src/mattstack/templates/deploy_runtime.py:310-314`, `src/mattstack/templates/root_env.py:119`).
- Rendered at `src/mattstack/templates/root_agents_md.py:211`.

## Goal and non-goals

Generated AGENTS.md lists the variables each backend actually reads: Django `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `SECRET_KEY`, `REDIS_URL` (if Redis); FastAPI its own set including `JWT_SECRET_KEY`. Take each name from `root_env.py`; add none that it does not write.

## Implementation steps

1. Split `_DJANGO_ENV` into Django and FastAPI strings, each verified against `root_env.py`.
2. Add tests to `tests/test_templates/test_templates.py`.

Stage only the Files owned, with explicit paths. Commit subject: `fix(templates): List real backend env vars in AGENTS.md`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | see Verification commands | 0 | django-ninja config: the env section of `generate_agents_md(config)` contains `DB_NAME` and `DB_HOST`, not `DATABASE_URL` |
| A2 | repo root | see Verification commands | 0 | FastAPI config: it contains `JWT_SECRET_KEY` |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
