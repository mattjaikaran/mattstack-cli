# S-CLI-18: Make AGENTS.md the single agent instruction file and check its links

| Field | Value |
|---|---|
| Spec ID | S-CLI-18 |
| Backlog item | GitHub issue #95: move agent instructions to AGENTS.md (`CLAUDE.md` imports it) and harden agent context with a link check in a pre-commit hook |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e9b6016 |
| Branch | agent/S-CLI-18 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `AGENTS.md` (new), `CLAUDE.md`, `scripts/check_agent_docs.py` (new), `tests/test_agent_docs_script.py` (new), `.pre-commit-config.yaml` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 15 |
| Max changed lines | 800 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_agent_docs_script.py -q`; `uv run python scripts/check_agent_docs.py`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3; A4; A5 (table below) |

## Context and verified citations

Verified on `e9b6016` (2026-11-10).

- `git ls-files` lists no root `AGENTS.md`; `CLAUDE.md` (73 lines, 3213 bytes) holds all agent guidance: stack (`CLAUDE.md:5-7`), dev commands (`:9-14`), CLI commands (`:16-37`), presets (`:39-40`), frontend frameworks (`:42-43`), rules (`:45-49`), architecture pointer (`:51-52`) and the gauntlet gate table with `make` commands (`:54-73`).
- Generated projects already follow the target layout: `src/mattstack/templates/agent_files.py:21` sets `CLAUDE_POINTER = "@AGENTS.md\n"`, and `CHANGELOG.md:72` records that the generated `CLAUDE.md` imports `AGENTS.md`. This spec applies the same layout to this repository; it changes no template.
- `tasks/specs/README.md:37-38` tells executors to read `CLAUDE.md`; after this change that file imports `AGENTS.md`, so the instruction still reaches the same text. `tasks/specs/README.md:42-53` lists the gate commands and `:55-58` the `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0` prefix.
- `tasks/todo.md:5-7` states the testing rule ("Do not generate bulk tests") and `tasks/todo.md:51-54` states that a test is added only for a consumer-visible contract. `docs/release.md` and `docs/commands.md` exist. No `docs/adr/` directory exists.
- `.pre-commit-config.yaml:6-26` defines local hooks with `language: system` and `pass_filenames: false`; the new hook follows that shape. The file's header (`:1`) says every gate runs locally.
- `tests/test_gauntlet_script.py:14-28` shows how tests load a script with `importlib.util.spec_from_file_location`; follow it.

## Goal and non-goals

`AGENTS.md` at the repository root is the one source of agent instructions, `CLAUDE.md` only imports it, and a script catches a broken link or a copied rule before commit. Non-goals: no nested `AGENTS.md` (no package has its own commands or rules), no skills directory, no change to `tasks/specs/README.md`, no generated-template change, no addition to the gauntlet, no hosted CI.

## Implementation steps

1. Create `AGENTS.md` by moving the content of `CLAUDE.md` (do not leave a copy behind), with these `##` sections in this order and these exact headings: `Project overview` (what mattstack is; stack line from `CLAUDE.md:5-7`), `Commands` (install, test, lint, format and the CLI command list from `CLAUDE.md:9-37`, presets and frontend frameworks), `Code standards` (rules from `CLAUDE.md:45-49`; link `docs/architecture.md` for the file map, patterns and extension workflows; the 400-line file limit and the layer rule from `scripts/check_architecture.py`), `Testing policy` (tests only for a consumer-visible contract, no bulk tests, tests mirror `src/` under `tests/`; cite `tasks/todo.md`), `Git and commits` (Conventional Commits as `<type>(<scope>): <Capitalized imperative summary>`, subject at most 50 characters, body wrapped at 72, stage explicit paths, the `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0` prefix for tests and why), `Spec workflow` (agent-run claims READY specs from `tasks/specs/`; link `tasks/specs/README.md`; change only Files owned; branch `agent/<Spec ID>`; run the quick gauntlet gates; link `docs/release.md` for releases) and `Security` (no secrets or `.env` files committed, subprocess calls take an argv list, the bandit gate stays blocking, `uv` and `bun` only). The gauntlet gate table from `CLAUDE.md:54-73` moves under `Commands`.
2. Replace `CLAUDE.md` with exactly `@AGENTS.md` and a trailing newline. Add no prose pointer and no copied rule.
3. Create `scripts/check_agent_docs.py` with `check(root: Path) -> list[str]`, the one seam, returning one `<file>: <problem>` string per problem, and `main(argv: list[str] | None = None) -> int` that checks the repository root (the parent of `scripts/`), prints each problem to stderr and returns 1, or prints one confirmation line and returns 0. Rules: (a) `AGENTS.md` exists and has every heading named in step 1 as a `## ` line; (b) `CLAUDE.md` exists and its first non-blank line is exactly `@AGENTS.md`; (c) in `AGENTS.md`, `CLAUDE.md` and `CONTRIBUTING.md` (each only when it exists), every relative Markdown link target and every `@path` import line names an existing file or directory. Strip a `#fragment`; skip `http://`, `https://`, `mailto:` and fragment-only targets; ignore fenced code blocks.
4. Add a local hook `agent-docs` to `.pre-commit-config.yaml`: `entry: uv run python scripts/check_agent_docs.py`, `language: system`, `files: ^(AGENTS|CLAUDE|CONTRIBUTING)\.md$`, `pass_filenames: false`, default (pre-commit) stage.
5. Create `tests/test_agent_docs_script.py` that calls `check(tmp_path)` on small trees: a valid tree returns no problems; a missing required heading is named; a `CLAUDE.md` that starts with prose fails; a broken relative link is named; a link inside a fenced block and an `https://` link are ignored; `CONTRIBUTING.md` is skipped when absent and checked when present.

Stage only the Files owned, with explicit paths. Commit subject: `docs(agents): Make AGENTS.md the instruction source`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `cat CLAUDE.md` | 0 | Output is exactly `@AGENTS.md` |
| A2 | repo root | `uv run python scripts/check_agent_docs.py` | 0 | One confirmation line; no problems listed |
| A3 | repo root | `grep -c '^## ' AGENTS.md` | 0 | Prints a count of at least 7 (the seven required headings) |
| A4 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_agent_docs_script.py -q` | 0 | All tests pass |
| A5 | repo root | `grep -c 'agent-docs' .pre-commit-config.yaml` | 0 | Prints a count of at least 1 |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a new dependency, or a check that fails outside your change. If `CLAUDE.md` content that is not listed in step 1 needs a home, stop and report it instead of dropping it. Commit nothing and report the exact discrepancy. The PR body lists the spec ID, base and head SHA, owned files with changed-line counts, and each criterion with its observed result.
