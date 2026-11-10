# S-CLI-19: Document the contribution workflow and add a pull request template

| Field | Value |
|---|---|
| Spec ID | S-CLI-19 |
| Backlog item | GitHub issue #53: adopt the planning and delivery workflow from sports-platform; this spec covers the in-repo documents only (`CONTRIBUTING.md`, PR template) |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e9b6016 |
| Branch | agent/S-CLI-19 |
| Depends on | S-CLI-18 |
| Conflicts with | none |
| Files owned | `CONTRIBUTING.md` (new), `.github/pull_request_template.md` (new), `README.md` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | S |
| Max files | 8 |
| Max changed lines | 300 |
| Verification commands | `uv run python scripts/check_agent_docs.py`; `test -f CONTRIBUTING.md`; `test -f .github/pull_request_template.md`; `grep -n 'CONTRIBUTING.md' README.md`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run python scripts/check_file_length.py` |
| Acceptance criteria | A1; A2; A3; A4 (table below) |

## Context and verified citations

Verified on `e9b6016` (2026-11-10).

- The repository has no `CONTRIBUTING.md` and no `.github/` directory (`ls -a` shows neither). `README.md:343-358` (`## Development`) holds the only contributor instructions: `uv sync --extra dev`, the test and lint commands, `make gauntlet-quick`, the statement `This repository has no hosted CI` (`README.md:353`), and the hooks install line. `README.md:413-419` is the `## Docs` link list.
- Issue #53 asks for: modular boundaries documented in an architecture doc (already present: `docs/architecture.md`), issues sized S, M or L with a frontier model splitting L work into S and M specs for small models, batch PRs of up to 2,000 lines that close every component issue, a PR template and review process (`matt-reviewer`, then the owner), and agent-run specs in `tasks/specs/S-*.md`.
- The reference is `~/dev/sports-platform/CONTRIBUTING.md` (108 lines: Work flow, Batch PRs, Sizes, Overnight agents, Review process, Tests) and `~/dev/sports-platform/.github/pull_request_template.md`. Adapt it; do not copy its hosted-CI, wave, journey, Playwright or `just claimed` content, which this repository does not have. If the reference is not readable on the executor host, step 1 and step 2 below list every section needed.
- Facts to state: gates run locally (`README.md:353-354`, `.pre-commit-config.yaml:1`); `make gauntlet-quick` is the pre-push gate; commit subjects follow `<type>(<scope>): <Capitalized imperative summary>`; agent-run claims READY specs and opens one PR per spec on `agent/<Spec ID>` (`tasks/specs/README.md:67-70`); `agent-run merge` merges only PRs that `mattjaikaran` and `matt-reviewer` both approved on the current head (`~/dev/sports-platform/CONTRIBUTING.md:52-57`, the reference this issue names).
- `scripts/check_agent_docs.py` (S-CLI-18) checks relative links and `@` imports in `CONTRIBUTING.md` when it exists.

## Goal and non-goals

A contributor or agent can read one file to learn how work flows from an issue to a merged PR here, and every PR opens with a template that asks for the issue, the spec and the commands run. Non-goals: no hosted CI workflow (issue #52), no GitHub labels, milestones or waves (they are GitHub state, not repository files), no Playwright or journey docs, no change to `AGENTS.md`, `tasks/specs/README.md` or any spec, no branch protection.

## Implementation steps

1. Create `CONTRIBUTING.md` with these `##` sections: `Set up` (`uv sync --extra dev`, `uv run mattstack hooks install`, the `git config --get core.hooksPath` caveat from `README.md:357`), `Work flow` (two tracks: owner sessions for larger or supervised work, and overnight agent-run specs; start from an issue or a READY spec; commit format with a 50-character subject and a body wrapped at 72; every commit body names its issue with `Closes #N` or `Refs #N`), `Batch PRs` (group similar issues in one area into one PR of at most 2,000 changed lines, one commit per issue, the PR closes every issue in the batch), `Sizes` (table: S at most 8 files and 300 inserted lines, an overnight small-model agent; M at most 15 files and 800; L at most 30 files and 2,000, split by a frontier-model session into S and M specs; tests count, lockfiles, generated files and deletions do not; each spec records its size in the `Size` header field), `Overnight agents` (link `tasks/specs/README.md`; claim rules in one paragraph; one PR per spec on `agent/<Spec ID>`), `Review process` (local gates first: `make gauntlet-quick` must pass; `matt-reviewer` reviews every PR; `mattstack-cli` owner `mattjaikaran` approves; a PR merges only with both approvals on its current head; no hosted CI exists, so evidence is the Verification section of the PR) and `Tests` (the policy in `AGENTS.md` under `Testing policy`: link it, do not restate the rules).
2. Create `.github/pull_request_template.md` with sections `Summary`, `Issues` (a `Closes #` line), `Spec` (spec ID and size, or `none`), `Verification` (commands run and what you saw) and a `Review checklist`: size within the spec's limits, no secrets or `.env` files, `make gauntlet-quick` passes, docs and `CHANGELOG.md` updated when behavior changed.
3. In `README.md`, add `- [Contributing](CONTRIBUTING.md)` to the `## Docs` list (`README.md:415-419`). Change nothing else in the file.
4. Run `uv run python scripts/check_agent_docs.py` and fix any broken link it reports in the new file.

Stage only the Files owned, with explicit paths. Commit subject: `docs(contributing): Document the contribution workflow`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `uv run python scripts/check_agent_docs.py` | 0 | No problems; `CONTRIBUTING.md` links resolve |
| A2 | repo root | `grep -c '^## ' CONTRIBUTING.md` | 0 | Prints a count of at least 7 |
| A3 | repo root | `grep -c 'Closes #' .github/pull_request_template.md` | 0 | Prints a count of at least 1 |
| A4 | repo root | `grep -n 'CONTRIBUTING.md' README.md` | 0 | One match inside the `## Docs` list |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file (including `scripts/check_agent_docs.py` when S-CLI-18 is not merged), a needed file outside Files owned, or a check that fails outside your change. Do not invent a merge method, branch-protection rule or runner. Commit nothing and report the exact discrepancy. The PR body lists the spec ID, base and head SHA, owned files with changed-line counts, and each criterion with its observed result.
