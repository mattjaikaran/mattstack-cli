# S-CLI-01: Use the pgvector image in generated CI for AI projects

| Field | Value |
|---|---|
| Spec ID | S-CLI-01 |
| Backlog item | Generated CI must use the same database image as Compose (pgvector when AI is on) |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | 9bf4cfe |
| Branch | agent/S-CLI-01 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `src/mattstack/templates/ci_toolchain.py`, `src/mattstack/commands/workflow.py`, `tests/test_commands/test_workflow.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 3 |
| Max changed lines | 120 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_commands/test_workflow.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3; A4 (table below) |

## Context and verified citations

Verified on `9bf4cfe` (2026-10-26).

- `src/mattstack/commands/workflow.py:153` (GitHub `backend-test` service) emits `image: postgres:{tools.postgres}`.
- `src/mattstack/commands/workflow.py:274` (GitLab `services`) emits `- postgres:{tools.postgres}`.
- Compose and `.env` already select pgvector through `pgvector_image(config)` (`src/mattstack/templates/compose_env.py:56-58`, `src/mattstack/templates/root_env.py:202`).
- `workflow.py` is 392 lines; the file-length gate allows 400. Put the new logic in `src/mattstack/templates/ci_toolchain.py` (181 lines).

## Goal and non-goals

When `config.use_ai` is true, the generated GitHub and GitLab workflows run the backend test service on `pgvector/pgvector:pg{postgres}`; otherwise they keep `postgres:{postgres}`. Non-goals: no change to Compose, `.env`, Redis/Valkey services or other jobs.

## Implementation steps

1. In `ci_toolchain.py`, add a method `CiTools.postgres_image(self, ai: bool) -> str` that returns `f"pgvector/pgvector:pg{self.postgres}"` when `ai` else `f"postgres:{self.postgres}"`.
2. In `workflow.py`, pass `config.use_ai` to `_backend_test_job` and `_gitlab_python_jobs` and use `tools.postgres_image(...)` for the image.
3. GitLab: render the AI service as `- name: pgvector/pgvector:pg<N>` with `alias: postgres`, so `DB_HOST=postgres` still resolves. Keep the plain `- postgres:<N>` form for non-AI.
4. Add tests to `tests/test_commands/test_workflow.py` (load output with `yaml.safe_load`).

Stage only the Files owned, with explicit paths. Commit subject: `fix(workflow): Use pgvector image in AI project CI`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | see Verification commands | 0 | AI config: GitHub `jobs.backend-test.services.postgres.image` starts with `pgvector/pgvector:pg` |
| A2 | repo root | see Verification commands | 0 | AI config: GitLab `backend-test.services[0]` equals `{name: pgvector/pgvector:pg<N>, alias: postgres}` |
| A3 | repo root | see Verification commands | 0 | Non-AI config: both workflows still use `postgres:<N>` |
| A4 | repo root | see Verification commands | 0 | `uv run python scripts/check_file_length.py` passes (workflow.py <= 400 lines) |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
