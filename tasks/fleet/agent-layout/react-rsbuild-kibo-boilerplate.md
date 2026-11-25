Umbrella: mattjaikaran/agent-run, "Track AGENTS.md migration across repos". Size: S.
Contract: https://github.com/mattjaikaran/mattstack-cli/blob/main/docs/agent-layout.md

## Contract (summary)
- Root `AGENTS.md` is the only agent instruction file. Max 200 lines, all links resolve.
- Skills: `.agents/skills/<name>/SKILL.md`, frontmatter `name` (equals dir) and `description`.
- `SKILLS.md` at root indexes every skill and is linked from `AGENTS.md`. Required only when `.agents/skills/` exists.
- Never tracked: `CLAUDE.md` (any depth), `.claude/**`, `.cursor/**`, `.cursorrules`, `.windsurf/**`, `GEMINI.md`, `.github/copilot-instructions.md`.
- `.claude/` and `.cursor/` are gitignored.

## Current state (origin/main)
- No `CLAUDE.md`. `AGENTS.md` is the instruction file.
- `.claude/skills/react-doctor/SKILL.md` is a tracked symlink to `../../../node_modules/react-doctor/dist/skills/react-doctor/SKILL.md`. Depends on `react-doctor` 0.9.14 (`package.json` line 85).
- `scripts/check_agent_docs.ts`: line 80 `checkHarnessAdapters()` checks for `CLAUDE.md`; line 95 `checkLegacyRules()`; `main()` line 111.
- `package.json` line 28 `check-agent-docs`; `Makefile` line 74; `.github/workflows/agent-docs.yml`.
- `.gitignore` has no `.claude/` or `.cursor/` rule.

## Work
- [ ] `git mv .claude/skills/react-doctor .agents/skills/react-doctor`. Same depth, so the relative target still resolves. Do not rewrite or copy the link.
- [ ] Add `SKILLS.md` at root listing `react-doctor`; link it from `AGENTS.md`.
- [ ] `scripts/check_agent_docs.ts`: `checkHarnessAdapters()` (line 80) fails when `CLAUDE.md` exists. Read `checkLegacyRules()` (line 95) and confirm it covers `.cursor/` and `.cursorrules`; add them if not. Fail on `.claude/skills`.
- [ ] `.gitignore`: add `.claude/` and `.cursor/`.

## Acceptance
- [ ] After `bun install`: `test -f .agents/skills/react-doctor/SKILL.md` succeeds.
- [ ] `make check-agent-docs` passes after `bun install`.
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.

## Content references (origin/main)
- [ ] `scripts/check_agent_docs.ts:4,81,87,90` header and `CLAUDE.md` check and messages. Rewrite to "must be absent".
- [ ] `AGENTS.md:7` prohibition text. Keep.
- [ ] `DESIGN.md` is not on `origin/main`; the local copy lags. Do not edit unless it appears on `origin/main`.
