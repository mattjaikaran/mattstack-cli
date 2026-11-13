# S-CLI-18: Make AGENTS.md the single agent instruction file and check its links

| Field | Value |
|---|---|
| Spec ID | S-CLI-18 |
| Backlog item | GitHub issue #95: move agent instructions to AGENTS.md (`CLAUDE.md` imports it) and harden agent context with a link check in a pre-commit hook |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | eb306fa |
| Branch | agent/S-CLI-18 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `scripts/gauntlet.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | S |
| Max files | 1 |
| Max changed lines | 150 |
| Verification commands | `uv run python scripts/check_agent_docs.py`; `uv run python scripts/gauntlet.py --gate install`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py` |
| Acceptance criteria | A1; A2; A3; A4; A5 (table below) |

## Context and verified citations

Verified on `eb306fa` (2026-11-12). This amends the merged S-CLI-18 (PR #113), whose Files owned was `tests/test_agent_docs_script.py`. The repository rule forbids a new unit-test file: `agent-run repos/mattstack-cli.yml:93` says "Do not add or change unit tests (tests/); when a change needs a test, extend the install smoke gate (scripts/gauntlet.py)", and the review hint at `repos/mattstack-cli.yml:101` says the same. The check therefore moves into the install smoke gate.

- PR #102 (merged, branch `agent/issue-97`) already delivered the agent-docs steps on `main`: `AGENTS.md` has the seven `##` headings, `CLAUDE.md` is exactly `@AGENTS.md`, `scripts/check_agent_docs.py` defines `REQUIRED_HEADINGS` (line 21), `check` (line 76) and `main` (lines 116-127), and `.pre-commit-config.yaml:20` defines the `agent-docs` hook. Do not redo these steps.
- `scripts/check_agent_docs.py:122-127` returns 1 when `check` reports problems, and returns 0 with a confirmation line otherwise.
- `scripts/gauntlet.py:252-253` is `_gate_install`; its `uv` lookup is `bin_ = shutil.which("uv") or "uv"`.
- `scripts/gauntlet.py:310-321` is the `GATES` registry. The `install` entry is at line 320. The adapter runs `--gate install` at `repos/mattstack-cli.yml:159`.

## Goal and non-goals

The install smoke gate fails when `AGENTS.md` or `CLAUDE.md` breaks the agent-docs rules. The gate checks the real repository, then runs a negative control on a copy with one required heading removed. The gate fails if the real repository fails the check, or if the broken copy passes it.

Non-goals: no new gate and no change to `GATES`, no `tests/` file, no pytest, no change to `scripts/check_agent_docs.py`, no nested `AGENTS.md`, no skills directory, no change to `tasks/specs/README.md`, no generated-template change, no hosted CI.

## Implementation steps

1. In `scripts/gauntlet.py`, add `_check_agent_docs() -> bool` directly above `_gate_install` (line 252). It:
   a. Loads `scripts/check_agent_docs.py` under the module name `check_agent_docs` with `importlib.util.spec_from_file_location`, the same loader pattern as `tests/test_gauntlet_script.py:14-28`. It reads `REQUIRED_HEADINGS` and `check` from the loaded module.
   b. Sets `root = Path(__file__).resolve().parent.parent` and requires `check(root) == []`. On a non-empty result, it prints the problems and returns `False`.
   c. Creates a `tempfile.TemporaryDirectory()`, copies `AGENTS.md` and `CLAUDE.md` from `root` into it, and removes from the copied `AGENTS.md` every line that contains `REQUIRED_HEADINGS[0]`. It requires `check(tmp)` to be non-empty, with at least one problem that contains `REQUIRED_HEADINGS[0]`. Otherwise it prints a message and returns `False`.
   d. Prints `agent-docs: repo passes; broken copy rejected` and returns `True`.
2. In `_gate_install`, call `_check_agent_docs()` first and return `False` when it returns `False`. Keep the rest of `_gate_install` unchanged.

Stage only `scripts/gauntlet.py`, with an explicit path. Commit subject: `chore(gauntlet): Check agent docs in install`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `cat CLAUDE.md` | 0 | Output is exactly `@AGENTS.md` |
| A2 | repo root | `uv run python scripts/check_agent_docs.py` | 0 | One confirmation line; no problems listed |
| A3 | repo root | `uv run python scripts/gauntlet.py --gate install` | 0 | Output includes `agent-docs: repo passes; broken copy rejected` and the install smoke test passes |
| A4 | repo root | `grep -c '_check_agent_docs' scripts/gauntlet.py` | 0 | Prints a count of at least 2 (the definition and the call) |
| A5 | repo root | `grep -c 'agent-docs' .pre-commit-config.yaml` | 0 | Prints a count of at least 1 |

A3 proves both directions in one run: the real repository passes, and the in-gate negative control rejects a broken copy. Do not edit `AGENTS.md` or `CLAUDE.md` to test the negative case.

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a new dependency, or a check that fails outside your change. Commit nothing and report the exact discrepancy. The PR body lists the spec ID, base and head SHA, owned files with changed-line counts, and each criterion with its observed result, including the A3 output lines.
