# S-CLI-16: Write backend/.python-version matching the backend image

| Field | Value |
|---|---|
| Spec ID | S-CLI-16 |
| Backlog item | GitHub issue #43: `backend/pyproject.toml` has `requires-python = ">=3.13"` and no `.python-version`, so a host with a newer Python makes uv pick it and fail to build wheels; write `backend/.python-version` with the image's Python version |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | 599d338 |
| Branch | agent/S-CLI-16 |
| Depends on | none |
| Conflicts with | S-CLI-15 |
| Files owned | `src/mattstack/post_processors/customizer.py`, `src/mattstack/templates/dockerfiles.py`, `tests/test_post_processors.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 3 |
| Max changed lines | 100 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_post_processors.py tests/test_templates/test_dockerfiles.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3; A4 (table below) |

## Context and verified citations

Verified on `599d338` (2026-11-08).

- `src/mattstack/templates/dockerfiles.py:212-215` (`_python_minor`) returns the backend's `major.minor` Python from the `python` pin (`.python-version`, else the `requires-python` floor, e.g. `>=3.13` gives `3.13`), else `_PYTHON_FALLBACK = "3.13"` (line 33). `_python_base` (line 239) uses it for `FROM python:<minor>-slim` and `ENV UV_PYTHON`. The generated image is therefore pinned; the scaffold's own `backend/` is not, so uv on the host chooses the newest interpreter.
- `src/mattstack/utils/versions.py:119-121` (`_python_sources`) reads `component / ".python-version"`, so a written file is picked up by `mattstack audit --versions` and agrees with the Dockerfile by construction.
- `src/mattstack/templates/dockerfiles.py` is exactly 400 lines (the `scripts/check_file_length.py` limit). Renaming `_python_minor` to the public `python_minor` (its two uses are lines 212 and 239) adds no line.
- `src/mattstack/post_processors/customizer.py:17-25` (`customize_backend`) is called by both `FullstackGenerator` (`generators/fullstack.py:131`) and `BackendOnlyGenerator` (`generators/backend_only.py:95`) after `config.source_pins` is set, and it already skips work in dry-run because the generators skip the step. It ends with `_refresh_uv_lock(config.backend_dir)`.
- `tests/test_post_processors.py:326` (`test_customize_backend_updates_pyproject_name`) is the pattern: a `_make_config(tmp_path)`, `config.backend_dir.mkdir(parents=True)`, a written `pyproject.toml`, then `customize_backend(config)`.

## Goal and non-goals

For a Python backend (Django Ninja, django-matt, FastAPI), `customize_backend` writes `backend/.python-version` containing `python_minor(config)` and a newline, unless the file already exists. A NestJS backend gets none. Non-goals: no change to the Dockerfile content, no `requires-python` edit, no write for NestJS, no overwrite of an existing pin.

## Implementation steps

1. In `src/mattstack/templates/dockerfiles.py`, rename `_python_minor` to `python_minor` at its definition and its one call; no other edit.
2. In `src/mattstack/post_processors/customizer.py`, add `_pin_python_version(config)` that returns when the backend is NestJS or `backend_dir/.python-version` exists, and otherwise writes `python_minor(config) + "\n"`. Call it in `customize_backend` before `_refresh_uv_lock`, for the Python branches only.
3. Add tests in `tests/test_post_processors.py`: a Django Ninja backend whose `pyproject.toml` has `requires-python = ">=3.13"` and no pin gets `3.13`; an existing `.python-version` containing `3.12` is kept; a NestJS backend gets none.

Stage only the Files owned, with explicit paths. Commit subject: `fix(backend): Pin the backend Python to the image version`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_post_processors.py -q` | 0 | After `customize_backend`, `backend/.python-version` reads `3.13` followed by a newline for a `>=3.13` backend |
| A2 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_post_processors.py -q` | 0 | An existing `.python-version` with `3.12` is unchanged; a NestJS backend has no `.python-version` |
| A3 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_templates/test_dockerfiles.py -q` | 0 | Existing Dockerfile tests pass unchanged (the rename changes no output) |
| A4 | repo root | `uv run python scripts/check_file_length.py` | 0 | `File length check passed` |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
