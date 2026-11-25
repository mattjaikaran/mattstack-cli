Umbrella: mattjaikaran/agent-run, "Track AGENTS.md migration across repos". Size: M.
Contract: https://github.com/mattjaikaran/mattstack-cli/blob/main/docs/agent-layout.md

## Contract (summary)
- Root `AGENTS.md` is the only agent instruction file. Max 200 lines, all links resolve.
- Skills: `.agents/skills/<name>/SKILL.md`, frontmatter `name` (equals dir) and `description`.
- `SKILLS.md` at root indexes every skill and is linked from `AGENTS.md`. Required only when `.agents/skills/` exists.
- Never tracked: `CLAUDE.md` (any depth), `.claude/**`, `.cursor/**`, `.cursorrules`, `.windsurf/**`, `GEMINI.md`, `.github/copilot-instructions.md`.
- `.claude/` and `.cursor/` are gitignored.

## Current state (origin/main)
- No `CLAUDE.md`. `AGENTS.md` is the instruction file.
- `.claude/skills/react-doctor/SKILL.md` is a tracked symlink to `../../../node_modules/react-doctor/dist/skills/react-doctor/SKILL.md`. Depends on `react-doctor` 0.9.14 (`package.json` line 57). No `.agents/` path is tracked.
- `scripts/check_agent_docs.ts` expects the reverse layout, and this ticket inverts it:
  - line 14 check 7 header: `.agents/skills`, when present, links to `.claude/skills`
  - line 34 `SKILLS_DIR = join('.claude', 'skills')`
  - line 187 `checkSkillsLocation()` requires `.agents/skills` to be a symlink (lines 189-200). It already has an `isDanglingSymlink` guard at line 215.
  - line 109 `checkClaudeImport()`; `main()` line 283.
- `.github/workflows/ci.yml` lines 189-208 `agent-docs` job; the final job on line 208 gates on it.
- `.gitignore` already contains `.claude/` (line 134).

## Work
- [ ] `git mv .claude/skills .agents/skills`. The react-doctor entry is a symlink with the same relative target, so it still resolves.
- [ ] Add `SKILLS.md` at root listing `react-doctor`; link it from `AGENTS.md`.
- [ ] `scripts/check_agent_docs.ts`: `SKILLS_DIR` (line 34) becomes `.agents/skills`. Replace `checkSkillsLocation()` (line 187) with a check that `.agents/skills` is a real directory and `.claude/skills` is absent. Remove the alias logic. Update check 7 in the header (line 14).
- [ ] `checkClaudeImport()` (line 109) fails when `CLAUDE.md` exists.
- [ ] `.gitignore`: add `.cursor/` next to `.claude/` (line 134).

## Acceptance
- [ ] After `bun install`: `test -f .agents/skills/react-doctor/SKILL.md` succeeds.
- [ ] `bun run check-agent-docs` passes after `bun install`. Before install the dangling link is a warning.
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.
- [ ] A test branch with `.claude/skills/x/SKILL.md` fails the checker.

## Content references (origin/main)
- [ ] `scripts/check_agent_docs.ts:10` item 4 `CLAUDE_IMPORT`, `:117-119` fallback message "must start with @AGENTS.md". Rewrite to "must be absent".
- [ ] `scripts/check_agent_docs.ts:12` item 6 path `.claude/skills/`, `:14` item 7 `SKILLS_LOCATION`. Rewrite to `.agents/skills` as canonical.
- [ ] `scripts/check_agent_docs.ts:197` message "must be a symlink to .claude/skills". Remove with the alias check.
- [ ] `scripts/check_agent_docs.ts:283` `claudePath` in `main()`. Keep the check, invert it.
- [ ] `AGENTS.md:7` prohibition text. Keep.
- [ ] `tasks/specs/9-prepare-nested-agents-md-journey.md:26` spec history. Leave.
