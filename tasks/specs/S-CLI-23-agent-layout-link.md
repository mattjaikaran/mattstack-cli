# S-CLI-23: Retire the root CLAUDE.md and link the agent layout doc

| Field | Value |
|---|---|
| Spec ID | S-CLI-23 |
| Backlog item | GitHub issue #132; Agent layout contract (`docs/agent-layout.md`): AGENTS.md is the only agent instruction file |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-23 |
| Depends on | none |
| Conflicts with | S-CLI-18 (shared file `scripts/gauntlet.py`); S-CLI-26, S-CLI-27, S-CLI-28, S-CLI-40, S-CLI-41 (shared file `scripts/gauntlet.py`) |
| Files owned | `CLAUDE.md` (delete); `AGENTS.md`; `scripts/check_agent_docs.py`; `scripts/gauntlet.py`; `.gitignore` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | S |
| Max files | 6 |
| Max changed lines | 120 |
| Verification commands | `uv run python scripts/check_agent_docs.py`; `uv run python scripts/gauntlet.py --gate install`; `uv run ruff format --check scripts/check_agent_docs.py scripts/gauntlet.py`; `uv run ruff check scripts/check_agent_docs.py scripts/gauntlet.py` |
| Acceptance criteria | A1 to A7 (table below) |

## Context and verified citations

Verified on `e89fac4`.

- `CLAUDE.md` is tracked at the repo root as the one-line `@AGENTS.md` pointer. The decided contract, from `docs/agent-layout.md` (exists now), is that `CLAUDE.md` never exists: `AGENTS.md` is the only agent instruction file. The rule covers this repo too, so the root pointer is deleted.
- `scripts/check_agent_docs.py` still requires it: `AGENT_DOCS` at line 30 lists `"CLAUDE.md"`, `POINTER = "@AGENTS.md"` at line 31, the rule-2 docstring at lines 9-10, and the `claude = root / "CLAUDE.md"` block at lines 93-102 (reports `CLAUDE.md: file is missing` and the pointer mismatch). The pass message at line 127 says "CLAUDE.md imports it".
- `scripts/gauntlet.py:272` is `for name in ("AGENTS.md", "CLAUDE.md"):` inside `_check_agent_docs`. It copies `CLAUDE.md` into the broken copy, so the gate fails once the file is deleted. This is the reason S-CLI-23 owns `scripts/gauntlet.py`.
- `.pre-commit-config.yaml:24` is `files: ^(AGENTS|CLAUDE|CONTRIBUTING)\.md$`.
- `.gitignore:33-34` is `.claude/settings.local.json` and `.claude/worktrees/`. Nothing under `.claude/` or `.cursor/` is tracked (`git ls-files .claude .cursor` is empty).
- `AGENTS.md` contains no `CLAUDE` text. Its only change is the link to `docs/agent-layout.md`.
- `S-CLI-18` also owns `scripts/gauntlet.py`. Its rewrite depends on this spec and declares the shared file as a conflict.
- PR #102 (`6a44a8e`) is an ancestor of the base `e89fac4`, so the S-CLI-18 agent-docs steps are on main and are not redone here.

## Goal and non-goals

Goal: the root `CLAUDE.md` is gone. `scripts/check_agent_docs.py` fails when `CLAUDE.md` exists at the root. The install gate's broken copy no longer includes `CLAUDE.md`. `AGENTS.md` links to `docs/agent-layout.md`, and the root ignore rules cover `.claude/` and `.cursor/` as whole directories.

Non-goals: no change to the seven `REQUIRED_HEADINGS`; no new gate and no change to `GATES`; no `tests/` file; no change to `docs/agent-layout.md`; no change to any generated-project template (that is S-CLI-24 and S-CLI-25); no change to `README.md` or `tasks/specs/README.md`; no commit beyond step 8.

## Implementation steps

1. Confirm `docs/agent-layout.md` exists. If not, stop (see stop conditions).
2. Delete the root `CLAUDE.md`. Do not replace it with another file.
3. `scripts/check_agent_docs.py`:
   a. In the docstring, replace rule 2 with: `CLAUDE.md does not exist; AGENTS.md is the only agent instruction file.` In rule 3, remove `CLAUDE.md` from the list of files.
   b. Remove `"CLAUDE.md"` from `AGENT_DOCS` (line 30). Remove `POINTER` (line 31) if nothing else uses it.
   c. Replace the `claude = root / "CLAUDE.md"` block (lines 93-102) with: if `(root / "CLAUDE.md").exists() or (root / "CLAUDE.md").is_symlink()`, append the problem `CLAUDE.md: must not exist; AGENTS.md is the only agent instruction file`.
   d. Change the pass message on line 127 to `Agent docs check passed: AGENTS.md is the only agent instruction file.`
4. `scripts/gauntlet.py:272`: change the tuple to `("AGENTS.md",)`. Change nothing else in `_check_agent_docs`.
5. `.pre-commit-config.yaml`: no change. Its `files:` pattern already includes `CLAUDE`, so the agent-docs hook runs on a commit that only adds `CLAUDE.md` and the must-not-exist check fires.
6. `.gitignore`: replace lines 33-34 with `.claude/` and `.cursor/`. Keep any other `.cursor` entry already present.
7. `AGENTS.md`: add one bullet that links `[docs/agent-layout.md](docs/agent-layout.md)`. Put it in the existing reference list, or directly after the first paragraph under the title. Change no other line.
8. Stage only the owned paths by name: `git add CLAUDE.md AGENTS.md scripts/check_agent_docs.py scripts/gauntlet.py .gitignore`. Commit with subject `chore(agents): Retire root CLAUDE.md`. Stop if the commit is blocked.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `test ! -e CLAUDE.md` | 0 | No output |
| A2 | repo root | `uv run python scripts/check_agent_docs.py` | 0 | Output includes `Agent docs check passed` |
| A3 | repo root | `d=$(mktemp -d); cp AGENTS.md "$d"/; mkdir "$d"/docs; cp docs/agent-layout.md "$d"/docs/; printf '@AGENTS.md\n' > "$d"/CLAUDE.md; uv run python scripts/check_agent_docs.py "$d" 2>&1; test $? -eq 1` | 0 (the inner check exits 1) | Output includes `CLAUDE.md: must not exist` |
| A4 | repo root | `uv run python scripts/gauntlet.py --gate install` | 0 | Output includes `agent-docs: repo passes; broken copy rejected` |
| A5 | repo root | `grep -n 'CLAUDE' scripts/gauntlet.py; test $? -eq 1` | 0 | No matches in `scripts/gauntlet.py` |
| A6 | repo root | `git check-ignore -q .claude/x && git check-ignore -q .cursor/x` | 0 | Both paths are ignored |
| A7 | repo root | `test -f docs/agent-layout.md && grep -c 'docs/agent-layout.md' AGENTS.md` | 0 | Prints `1` or more |

## Stop conditions and PR evidence

Stop, and report the discrepancy without further edits, when `docs/agent-layout.md` is missing, when `check_agent_docs` fails before your edit, when `scripts/gauntlet.py` no longer contains the `CLAUDE.md` tuple at line 272 (the base has changed), or when a change needs a file outside Files owned. The report lists the base and head SHA, the changed-line count, and each criterion with its observed result.
