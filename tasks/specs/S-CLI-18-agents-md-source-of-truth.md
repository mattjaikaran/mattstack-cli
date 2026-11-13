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
| Verification commands | `uv run python scripts/check_agent_docs.py`; `uv run python scripts/gauntlet.py --gate agent-docs`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py` |
| Acceptance criteria | A1; A2; A3; A4; A5 (table below) |

## Context and verified citations

Verified on `eb306fa` (2026-11-13). This amends the merged S-CLI-18 (PR #113), whose Files owned was `tests/test_agent_docs_script.py`. The repository rule forbids a new unit-test file: `agent-run repos/mattstack-cli.yml:93` says "Do not add or change unit tests (tests/); when a change needs a test, extend the install smoke gate (scripts/gauntlet.py)", and the review hint at `repos/mattstack-cli.yml:101` says the same. The check therefore moves into the gauntlet.

- PR #102 (merged, branch `agent/issue-97`) already delivered steps 1-4 on `main`: `AGENTS.md` has the seven `##` headings, `CLAUDE.md` is exactly `@AGENTS.md`, `scripts/check_agent_docs.py` defines `check` (line 76) and `main` (lines 116-127), and `.pre-commit-config.yaml:20` defines the `agent-docs` hook. Do not redo these steps.
- `scripts/check_agent_docs.py:122-127` returns 1 when `check` reports problems and prints a confirmation line and returns 0 otherwise.
- `scripts/gauntlet.py:310-321` is the `GATES` registry. Each `Gate(name, description, quick, run)` entry adds one gate, and `--gate <name>` runs only that gate (lines 335-341).
- `scripts/gauntlet.py:252-253` shows `_gate_install`: its `uv` lookup is `bin_ = shutil.which("uv") or "uv"`. Follow the same lookup.
- `tasks/todo.md:5-7` states the testing rule ("Do not generate bulk tests").

## Goal and non-goals

The gauntlet fails when `AGENTS.md` or `CLAUDE.md` breaks the agent-docs rules: a missing required heading, a `CLAUDE.md` that does not import `AGENTS.md` first, or a broken relative link. The new `agent-docs` quick gate runs `scripts/check_agent_docs.py` so the check runs in `scripts/gauntlet.py --quick` as well as on its own.

Non-goals: no `tests/` file, no pytest, no change to `scripts/check_agent_docs.py`, no nested `AGENTS.md`, no skills directory, no change to `tasks/specs/README.md`, no generated-template change, no hosted CI.

## Implementation steps

1. In `scripts/gauntlet.py`, add `_gate_agent_docs() -> bool` above the `# gate registry` section (line 306). It runs `[bin_, "run", "python", "scripts/check_agent_docs.py"]` from the repository root, with `bin_` found as in `_gate_install` (line 253). It returns `True` only when the exit code is 0 and prints the script's output either way.
2. Add `Gate("agent-docs", "AGENTS.md and CLAUDE.md heading and link check", quick=True, run=_gate_agent_docs)` to `GATES` (lines 310-321), before the `install` entry.

Stage only `scripts/gauntlet.py`, with an explicit path. Commit subject: `chore(gauntlet): Add agent-docs gate`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `cat CLAUDE.md` | 0 | Output is exactly `@AGENTS.md` |
| A2 | repo root | `uv run python scripts/check_agent_docs.py` | 0 | One confirmation line; no problems listed |
| A3 | repo root | `uv run python scripts/gauntlet.py --gate agent-docs` | 0 | Output reports the `agent-docs` gate as passed |
| A4 | scratch copy | `rm -rf /tmp/s18-broken && cp -R . /tmp/s18-broken && cd /tmp/s18-broken && awk '!done && /^## / {done=1; next} 1' AGENTS.md > AGENTS.tmp && mv AGENTS.tmp AGENTS.md && uv run python scripts/gauntlet.py --gate agent-docs; echo "exit=$?"` | `exit=1` | Output names `AGENTS.md` and the removed heading. Do not commit the broken copy. Remove `/tmp/s18-broken` afterward. |
| A5 | repo root | `grep -c 'agent-docs' .pre-commit-config.yaml` | 0 | Prints a count of at least 1 |

A4 proves that the gate fails on a broken `AGENTS.md` without adding a test file.

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a new dependency, or a check that fails outside your change. Commit nothing and report the exact discrepancy. The PR body lists the spec ID, base and head SHA, owned files with changed-line counts, and each criterion with its observed result, including the A4 output from the broken copy.
