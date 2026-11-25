Umbrella: mattjaikaran/agent-run, "Track AGENTS.md migration across repos". Size: M.
Contract: https://github.com/mattjaikaran/mattstack-cli/blob/main/docs/agent-layout.md

## Contract (summary)
- Root `AGENTS.md` is the only agent instruction file. Max 200 lines, all links resolve.
- Skills: `.agents/skills/<name>/SKILL.md`, frontmatter `name` (equals dir) and `description`.
- `SKILLS.md` at root indexes every skill and is linked from `AGENTS.md`. Required only when `.agents/skills/` exists.
- Never tracked: `CLAUDE.md` (any depth), `.claude/**`, `.cursor/**`, `.cursorrules`, `.windsurf/**`, `GEMINI.md`, `.github/copilot-instructions.md`.
- `.claude/` and `.cursor/` are gitignored and dockerignored.

## Current state (origin/main)
- No `CLAUDE.md`. `AGENTS.md` is the instruction file.
- Vendored, real files (not symlinks) under `.claude/skills/react-doctor/`: `SKILL.md`, `LICENSE`, `references/explain.md`. Depends on `react-doctor` 0.9.14 (`package.json` line 79).
- `scripts/check_conventions.ts`: `AGENT_DOCS` check lines 319-388. Line 352 checks `CLAUDE.md`; line 363 reads `.claude/skills`. `CHECKS` line 389.
- `.githooks/pre-commit` lines 2-5 comment names `CLAUDE.md` as a harness adapter.
- `.github/workflows/ci.yml` line 107 `agent-docs` job.
- `.gitignore` line 49 and `.dockerignore` line 15: `.claude/settings.local.json` only.

## Work
- [ ] Run `bun install`, then `ls node_modules/react-doctor/dist/skills/react-doctor/` to check whether the pinned react-doctor 0.9.14 ships `references/explain.md` and `LICENSE`. If it does not, keep those files under `.agents/skills/react-doctor/` and note why in `DEPENDENCIES.md`.
- [ ] `git mv .claude/skills/react-doctor .agents/skills/react-doctor`. Real directory, so plain move; no symlink.
- [ ] Add `SKILLS.md` at root listing `react-doctor`; link it from `AGENTS.md`.
- [ ] `scripts/check_conventions.ts`: line 352 fails when `CLAUDE.md` exists. Line 363 reads `.agents/skills`. Fail on `.claude/skills`.
- [ ] `.githooks/pre-commit` lines 2-3: update comment.
- [ ] `.gitignore` line 49 and `.dockerignore` line 15: `.claude/`; add `.cursor/` to both.

## Acceptance
- [ ] `bun run check-conventions --check AGENT_DOCS` passes on a clean checkout.
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.
- [ ] `git check-ignore -v .claude/x .cursor/x` reports both ignored.

## Content references (origin/main)
- [ ] `AGENTS.md:90-91` names `.claude/skills/react-doctor/` and `.claude/settings.local.json`. Update the skill path to `.agents/skills/react-doctor/` after `git mv`.
- [ ] `AGENTS.md:7` prohibition text. Keep.
- [ ] `.githooks/pre-commit:3` comment. Already covered.
