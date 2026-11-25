<!-- EDIT ISSUE #1 -->
Umbrella: mattjaikaran/agent-run, "Track AGENTS.md migration across repos". Size: M.
Contract: https://github.com/mattjaikaran/mattstack-cli/blob/main/docs/agent-layout.md

## Contract (summary)
- Root `AGENTS.md` is the only agent instruction file. Max 200 lines, all links resolve.
- Skills: `.agents/skills/<name>/SKILL.md`, frontmatter `name` (equals dir) and `description`.
- `SKILLS.md` at root indexes every skill and is linked from `AGENTS.md`. Required only when `.agents/skills/` exists.
- Never tracked: `CLAUDE.md` (any depth), `.claude/**`, `.cursor/**`, `.cursorrules`, `.windsurf/**`, `GEMINI.md`, `.github/copilot-instructions.md`.
- `.claude/` and `.cursor/` are gitignored.

## Current state (origin/main)
- No `AGENTS.md`, no `CLAUDE.md`, no skills, no `SKILLS.md`.
- No `justfile`. A `Makefile` has a `deps-check` target.
- `package.json` scripts: `build`, `check`, `typecheck`, `test`, `test:cov`, `test:e2e`, `db:migrate`, `db:seed`, `openapi:codegen`.
- `tasks/todo.md` is tracked. `docs/` is referenced by the issue and does not exist on origin/main.
- `.gitignore` has no `.claude/` or `.cursor/` rule.

## Work
- [ ] Create root `AGENTS.md` (under 200 lines). Link the existing `docs/` directory for reference material.
- [ ] Add a `justfile` whose recipes delegate to the `package.json` scripts with `bun run` (for example `just test` runs `bun run test`). The repo uses `bun.lock`; never use npm. Keep `make deps-check` in the Makefile.
- [ ] Keep `tasks/todo.md` and link it from `AGENTS.md`.
- [ ] `.gitignore`: add `.claude/` and `.cursor/`.
- [ ] Add a step to `.github/workflows/ci.yml` that fails when `git ls-files CLAUDE.md '*/CLAUDE.md' .claude .cursor .cursorrules` prints anything.

## Acceptance
- [ ] `just --list` shows a recipe for each delegated script.
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.
- [ ] Every link in `AGENTS.md` resolves.

## Content references (origin/main)
- [ ] `git grep -nE 'CLAUDE\.md|\.claude/'` on `origin/main` returns no hits. Nothing to rewrite; keep the contract checks.
