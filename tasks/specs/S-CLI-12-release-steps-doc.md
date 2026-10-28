# S-CLI-12: Document the manual release steps

| Field | Value |
|---|---|
| Spec ID | S-CLI-12 |
| Backlog item | `tasks/todo.md:21-24` (release process): write the manual release steps in `docs/` |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | 9337e65 |
| Branch | agent/S-CLI-12 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `docs/release.md` (new) |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 1 |
| Max changed lines | 120 |
| Verification commands | `test -f docs/release.md`; `grep -c 'gh release create' docs/release.md`; `make -n gauntlet`; `uv run python scripts/check_file_length.py`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/` |
| Acceptance criteria | A1; A2; A3 (table below) |

## Context and verified citations

Verified on `9337e65` (2026-10-28).

- `tasks/todo.md:21-24` says no workflow publishes releases, so 0.9.0 was tagged without one. Tags `v0.8.0`, `v0.9.0` and `v0.9.1` exist (`git tag`); `pyproject.toml:7` has `version = "0.9.1"`.
- The build backend is hatchling (`CLAUDE.md`). Gates: `make gauntlet` runs `uv run python scripts/gauntlet.py` (`Makefile:27-28`); `make gauntlet-quick` skips mutation and audit.
- No file in `docs/` describes a release (`docs/` holds architecture, commands, deployment-guide, ecosystem, plugin-guide and plans).
- Gate 10 becomes a built-wheel smoke test in S-CLI-09; the document must name the gate, not copy its commands.

## Goal and non-goals

`docs/release.md` lists, in order, the steps a maintainer runs by hand to cut a release: (1) bump `version` in `pyproject.toml` and commit; (2) run `make gauntlet` on a clean tree and require every gate to pass; (3) tag `vX.Y.Z` and push the tag; (4) from the tag, build the sdist with `uv build --sdist`, then the wheel from the sdist with `uv build --wheel` (output in `dist/`); (5) install the wheel into a fresh `uv venv` outside the repo and run `mattstack --help` and `mattstack sync --help`; (6) `gh release create vX.Y.Z dist/*.tar.gz dist/*.whl` with generated notes. State that no workflow publishes releases. Non-goals: no Makefile target, no workflow, no code change, no PyPI upload step, no change to other docs.

## Implementation steps

1. Create `docs/release.md` with a short intro and the six numbered steps, each with its command in a fenced block.
2. Run the verification commands.

Stage only the Files owned, with explicit paths. Commit subject: `docs(release): Document the manual release steps`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `test -f docs/release.md` | 0 | File exists |
| A2 | repo root | `grep -c 'gh release create' docs/release.md` | 0 | Prints a count of at least 1 |
| A3 | repo root | `make -n gauntlet` | 0 | Prints `uv run python scripts/gauntlet.py`, the command the document names for step 2 |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
