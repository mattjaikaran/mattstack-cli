# S-CLI-09: Make gauntlet INSTALL a wheel smoke test

| Field | Value |
|---|---|
| Spec ID | S-CLI-09 |
| Backlog item | Gate 10 passed while a dependency was missing: build and install the wheel |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | 9bf4cfe |
| Branch | agent/S-CLI-09 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `scripts/gauntlet.py`, `CLAUDE.md`, `tests/test_gauntlet_script.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 3 |
| Max changed lines | 200 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_gauntlet_script.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2 (table below) |

## Context and verified citations

Verified on `9bf4cfe` (2026-10-26).

- `scripts/gauntlet.py:192-198` (`_gate_install`) only runs `uv pip install -e .`, which passes even when a runtime dependency is missing from `pyproject.toml`.
- CLAUDE.md gate table row 10 describes it as `pip install -e .`.
- No test covers `scripts/`.

## Goal and non-goals

Gate 10 builds an sdist, builds a wheel from that sdist, creates a temporary `uv venv`, installs the wheel into it, and runs `mattstack --help` and `mattstack sync --help` from that venv; any non-zero exit fails the gate. Agent runs have no network, so A1 and A2 (mocked `_run`) are the proof; do not run the real install gate. Non-goals: no CI workflow change, no other gate changes.

## Implementation steps

1. Rewrite `_gate_install` with a temporary directory: `uv build --sdist -o D`, `uv build --wheel -o D <sdist>`, `uv venv D/venv`, `uv pip install --python D/venv <wheel>`, then the two help runs. Give it a timeout above the default 120 s.
2. Update CLAUDE.md row 10.
3. Create `tests/test_gauntlet_script.py`: load the script with `importlib.util.spec_from_file_location`, monkeypatch `_run` to record argv and return canned results.

Stage only the Files owned, with explicit paths. Commit subject: `fix(gauntlet): Smoke-test the built wheel`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | see Verification commands | 0 | Recorded argv order: sdist build, wheel build, venv, install, `--help`, `sync --help` |
| A2 | repo root | see Verification commands | 0 | `_gate_install()` returns False when any step exits non-zero |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
