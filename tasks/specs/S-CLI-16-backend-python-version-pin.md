# S-CLI-16: Smoke the backend .python-version pin in the install gate

| Field | Value |
|---|---|
| Spec ID | S-CLI-16 |
| Backlog item | GitHub issue #43 (backend `.python-version` pin, shipped in `03b7cc1`) and spec-gap issue #74: the pin has no coverage; the executor may not add unit tests, so the install gate proves it |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | 440133b |
| Branch | agent/S-CLI-16 |
| Depends on | S-CLI-09, S-CLI-10 (both merged: `03caad9`, `6acde5c`) |
| Conflicts with | S-CLI-15 |
| Files owned | `scripts/gauntlet.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 1 |
| Max changed lines | 80 |
| Verification commands | `uv run python scripts/gauntlet.py --gate install`; `uv run ruff format --check src/ tests/ scripts/gauntlet.py`; `uv run ruff check src/ tests/ scripts/gauntlet.py`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py` |
| Acceptance criteria | A1; A2; A3 (table below) |

## Context and verified citations

Verified on `440133b` (2026-11-09).

- The source change for issue #43 is on `main` already (`03b7cc1`). `src/mattstack/post_processors/customizer.py:26` calls `_pin_python_version(config)` before `_refresh_uv_lock`; `customizer.py:30` defines it. It returns for a NestJS backend, a missing backend directory, or an existing `.python-version`, and otherwise writes `python_minor(config)` plus a newline. `src/mattstack/templates/dockerfiles.py:212` defines the public `python_minor`.
- Nothing tests it. `grep -n "python-version" tests/test_post_processors.py` finds no match.
- The first attempt at this spec (agent/S-CLI-16, `9476a4b`) stopped on the gate line `scripts/gauntlet.py is not in the spec's Files owned`: the executor rules say to extend the install smoke gate rather than add unit tests, so the only file it could change was `scripts/gauntlet.py`. This revision owns that file and nothing else.
- `scripts/gauntlet.py:193` (`_gate_install`) builds the sdist, builds the wheel from it, installs the wheel into a fresh venv, then runs `--version` (line 230), `--help`, `sync --help` and the mistyped group `sync2` (line 240) through `_run` (line 54). It ends with `return True` at line 244. The gate registry entry is at line 261, and the gate list in the module docstring is at line 14.
- `tests/test_gauntlet_script.py` records every `_run` call of `_gate_install` and is stale at this commit: 12 tests fail when run here (`uv run --extra dev pytest tests/test_gauntlet_script.py -q`; the module loader raises `AttributeError` and the recorded call list lacks the `--version` call from `3a39e1a`). Do not edit it and do not run it as a gate.

## Goal and non-goals

The install gate proves that the wheel it just built writes the backend pin. After the existing checks, it runs one Python program with the venv's interpreter, which calls the installed `customize_backend` on three temporary projects: a Django Ninja backend whose `pyproject.toml` has `requires-python = ">=3.13"` and no pin must end with `backend/.python-version` reading `3.13` and a newline; a FastAPI backend with an existing `.python-version` of `3.12` and a newline must keep it; a NestJS backend must get no `.python-version`. The gate fails, with the program's output printed, when any assertion fails. Non-goals: no change under `src/` or `tests/`, no change to the other gate steps, no new dependency, no network access.

## Implementation steps

1. In `scripts/gauntlet.py`, add a module-level program string and a helper `_smoke_python_pin(venv_python: Path, work: Path, timeout: int) -> bool`. The helper creates a `pin-smoke` directory inside `work`, runs `[str(venv_python), "-c", <program>, <directory>]` through `_run`, prints the output on a non-zero exit, and returns whether the exit code was 0. The program builds each project with `ProjectConfig(name=..., path=..., backend_framework=...)` from `mattstack.config`, writes the `pyproject.toml` (and the existing pin for the second case) into `<path>/backend`, calls `mattstack.post_processors.customizer.customize_backend`, and asserts the file content.
2. Replace `return True` at the end of `_gate_install` (line 244) with `return _smoke_python_pin(venv / "bin" / "python", work, timeout)`.
3. Update the gate description at line 261 to `wheel build + installed smoke test`, and extend the item 10 text in the module docstring (line 14) to mention the backend Python pin.
4. Prove the smoke is not vacuous, then discard the experiment: temporarily comment out `_pin_python_version(config)` in a scratch copy of `src/` (never in the owned file), build and run the gate against it or run the program by hand, and confirm the first assertion fails. Record the observed failure in the PR body. The scratch copy is not part of the diff.

Stage only the Files owned, with explicit paths. Commit subject (at most 50 characters): `test(gauntlet): Smoke the Python pin in the wheel`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `uv run python scripts/gauntlet.py --gate install` | 0 | Output contains `[PASS] install: wheel build + installed smoke test` and `1 passed, 0 failed` |
| A2 | repo root | `uv run ruff format --check src/ tests/ scripts/gauntlet.py && uv run ruff check src/ tests/ scripts/gauntlet.py` | 0 | `already formatted` and `All checks passed!` |
| A3 | repo root | `git diff --stat origin/main...HEAD` | 0 | Lists exactly one file, `scripts/gauntlet.py`, with at most 80 changed lines |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result, including the failure observed in step 4.
