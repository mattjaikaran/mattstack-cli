Umbrella: mattjaikaran/agent-run, "Track AGENTS.md migration across repos". Size: S.
Contract: https://github.com/mattjaikaran/mattstack-cli/blob/main/docs/agent-layout.md

## Contract (summary)
- Root `AGENTS.md` is the only agent instruction file. Max 200 lines, all links resolve.
- Skills: `.agents/skills/<name>/SKILL.md`, frontmatter `name` (equals dir) and `description`.
- `SKILLS.md` at root indexes every skill and is linked from `AGENTS.md`. Required only when `.agents/skills/` exists.
- Never tracked: `CLAUDE.md` (any depth), `.claude/**`, `.cursor/**`, `.cursorrules`, `.windsurf/**`, `GEMINI.md`, `.github/copilot-instructions.md`.
- `.claude/` and `.cursor/` are gitignored.

## Current state (origin/main)
- No `CLAUDE.md`, no skills, no `SKILLS.md` tracked.
- `scripts/check_agent_docs.ts`: line 25 `CLAUDE_FILE = "CLAUDE.md"`; line 119 `checkClaudeFallback()`; `main()` calls it.
- `package.json` line 53 pins `react-doctor` 0.2.9. The repo does not track its skill.
- `.gitignore` line 47 ignores only `.claude/settings.local.json`.

## Work
- [ ] `scripts/check_agent_docs.ts`: remove `CLAUDE_FILE` (line 25) and `checkClaudeFallback()` (line 119). Fail when `CLAUDE.md` exists at any depth, and when `.claude/skills` exists.
- [ ] `.gitignore` line 47: replace with `.claude/`; add `.cursor/`.
- [ ] No react-doctor skill is added here. Nothing is tracked, so nothing changes for it.

## Acceptance
- [ ] `bun run check-agents` and `bun run gauntlet` pass after `bun install`.
- [ ] Adding `CLAUDE.md` on a test branch makes `check-agents` fail.
- [ ] `git check-ignore -v .claude/x .cursor/x` reports both ignored.

## Content references (origin/main)
- [ ] `scripts/check_agent_docs.ts:9` header item 4 `CLAUDE_MD_FALLBACK` and `:25` `CLAUDE_FILE`. Remove with the check.
- [ ] `scripts/check_agent_docs.ts:131` message "must be deleted or contain only @AGENTS.md". Change to "must be deleted".
- [ ] `tasks/specs/7-prepare-nested-agents-md-journey.md:21,35` lists `.claude/skills/react-doctor/SKILL.md` (delete) and "No CLAUDE.md tracked". Confirm nothing is tracked, then leave the spec as history.
- [ ] `AGENTS.md:7` prohibition text. Keep.
