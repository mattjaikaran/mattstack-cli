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
- `.claude/skills/react-doctor/SKILL.md` is a tracked symlink to `../../../node_modules/react-doctor/dist/skills/react-doctor/SKILL.md`. Depends on `react-doctor` 0.9.14 (`package.json` line 72).
- `tasks/specs/7-prepare-nested-agents-md-journey.md` lines 58-59 decided to keep `.claude/skills/react-doctor/SKILL.md`. This ticket overrides that decision. Update the spec to say it is superseded.
- `scripts/check_agent_docs.ts`: line 9 header; line 93 `checkClaudeImport()`; line 114 `checkSkills()` reads `.claude/skills` (lines 115-147); `main()` line 157.
- `package.json` line 28 `check:agents`; `Makefile` line 68 `check-agents`; `.github/workflows/agents.yml` line 27.
- `.gitignore` line 20 has an "agent personal overrides" comment and no `.claude/` rule.

## Work
- [ ] `git mv .claude/skills/react-doctor .agents/skills/react-doctor`. Same depth, so the relative target still resolves. Do not rewrite or copy the link.
- [ ] Add `SKILLS.md` at root listing `react-doctor`; link it from `AGENTS.md`.
- [ ] `scripts/check_agent_docs.ts`: `checkSkills()` (line 114) reads `.agents/skills`. `checkClaudeImport()` (line 93) fails when `CLAUDE.md` exists. Fail on `.claude/skills`. A dangling symlink before install is a warning. Update header (line 9).
- [ ] Amend `tasks/specs/7-prepare-nested-agents-md-journey.md` lines 58-59 to note the decision is superseded by this ticket.
- [ ] `.gitignore` line 20 block: add `.claude/` and `.cursor/`.

## Acceptance
- [ ] After `bun install`: `test -f .agents/skills/react-doctor/SKILL.md` succeeds.
- [ ] `make check-agents` and `bun run check:agents` pass after `bun install`.
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.

## Content references (origin/main)
- [ ] `scripts/check_agent_docs.ts:8` item 3 and `:94,99` read `CLAUDE.md` with import check. Remove the import check; fail when it exists.
- [ ] `scripts/check_agent_docs.ts:9,128,138,147` skill paths `.claude/skills/${entry}`. Change to `.agents/skills/${entry}`.
- [ ] `AGENTS.md:6` prohibition text. Keep.
- [ ] `tasks/specs/7-prepare-nested-agents-md-journey.md:8,21,35,58-59`. Lines 58-59 are overridden by this ticket; amend them (already listed above). The rest is history.
