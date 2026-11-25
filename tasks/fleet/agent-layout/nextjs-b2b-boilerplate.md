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
- `.claude/skills/react-doctor/SKILL.md` is a tracked symlink to `../../../node_modules/react-doctor/dist/skills/react-doctor/SKILL.md`. Depends on `react-doctor` 0.9.14 (`package.json` line 52).
- `scripts/check_agents_md.ts`: line 76 `checkClaudeFile()`; `main()` runs it with the AGENTS check.
- `.github/workflows/ci.yml` line 31 path filter includes `CLAUDE`.
- `.gitignore` lines 45-47: `AGENTS.local.md`, `CLAUDE.local.md`, `.claude/settings.local.json`.

## Work
- [ ] `git mv .claude/skills/react-doctor .agents/skills/react-doctor`. Same depth, so the relative target `../../../node_modules/...` still resolves. Do not rewrite or copy the link.
- [ ] Add `SKILLS.md` at root listing `react-doctor`; link it from `AGENTS.md`.
- [ ] `scripts/check_agents_md.ts`: make `checkClaudeFile()` (line 76) fail when `CLAUDE.md` exists. Skills path becomes `.agents/skills`. Fail on `.claude/skills`. A skill symlink whose target is absent before install is a warning, not a failure.
- [ ] `ci.yml` line 31: drop `CLAUDE` from the path regex.
- [ ] `.gitignore`: replace lines 46-47 with `.claude/`; add `.cursor/`; drop `CLAUDE.local.md`.

## Acceptance
- [ ] After `bun install`: `test -f .agents/skills/react-doctor/SKILL.md` succeeds.
- [ ] `bun run check-agents` and `bun run gauntlet` pass after `bun install`.
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.

## Content references (origin/main)
- [ ] `AGENTS.md:4` says other tools read it "through `CLAUDE.md`". Rewrite to say no adapter is tracked.
- [ ] `AGENTS.md:92` names `.claude/skills/<name>/SKILL.md`. Change to `.agents/skills/`.
- [ ] `docs/code-standards.md:41` mentions `CLAUDE.md` allowed to be `@AGENTS.md`. Rewrite to "absent".
- [ ] `scripts/check_agents_md.ts:4,77,86,135` header, check, error and success message mention `CLAUDE.md`. Rewrite each to the "must be absent" rule; drop the success text.
