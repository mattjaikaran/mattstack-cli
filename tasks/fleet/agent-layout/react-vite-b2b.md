Umbrella: mattjaikaran/agent-run, "Track AGENTS.md migration across repos". Size: S.
Contract: https://github.com/mattjaikaran/mattstack-cli/blob/main/docs/agent-layout.md

## Contract (summary)
- Root `AGENTS.md` is the only agent instruction file. Max 200 lines, all links resolve. Nested `AGENTS.md` only where a package needs its own rules.
- Skills: `.agents/skills/<name>/SKILL.md`, frontmatter `name` (equals dir) and `description`.
- `SKILLS.md` at root indexes every skill and is linked from `AGENTS.md`. Required only when `.agents/skills/` exists.
- Never tracked: `CLAUDE.md` (any depth), `.claude/**`, `.cursor/**`, `.cursorrules`, `.windsurf/**`, `GEMINI.md`, `.github/copilot-instructions.md`.
- `.claude/` and `.cursor/` are gitignored.

## Current state (origin/main)
- No `CLAUDE.md`. `AGENTS.md` is the instruction file.
- `.claude/skills/react-doctor/SKILL.md` is a tracked symlink to `../../../node_modules/react-doctor/dist/skills/react-doctor/SKILL.md`. Depends on `react-doctor` 0.9.14 (`package.json` line 55).
- `scripts/check_agents.ts`: lines 13-17 check list names `.claude/skills`; line 152 `checkLegacyFiles()` checks `CLAUDE.md`; line 180 `checkTrackedFiles()`; line 209 `checkSkills()` reads `.claude/skills` (line 211); `main()` line 249.
- `.github/workflows/ci.yml` line 155 `check-agents` job.
- `.gitignore` line 17 "Personal agent config" comment; no `.claude/` rule.

## Work
- [ ] `git mv .claude/skills/react-doctor .agents/skills/react-doctor`. Same depth, so the relative target still resolves. Do not rewrite or copy the link.
- [ ] Add `SKILLS.md` at root listing `react-doctor`; link it from `AGENTS.md`.
- [ ] `scripts/check_agents.ts`: `checkSkills()` (line 209) reads `.agents/skills`. `checkLegacyFiles()` (line 152) fails when `CLAUDE.md` exists. Fail on `.claude/skills`. Update check list (lines 13-17). A dangling symlink before install is a warning.
- [ ] `checkTrackedFiles()` (line 180): fail on any tracked path under `.claude/` or `.cursor/`, or named `CLAUDE.md`.
- [ ] `.gitignore` line 17 block: add `.claude/` and `.cursor/`.

## Acceptance
- [ ] After `bun install`: `test -f .agents/skills/react-doctor/SKILL.md` succeeds.
- [ ] `bun run check-agents` passes after `bun install`.
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.

## Content references (origin/main)
- [ ] `AGENTS.md:4` says `CLAUDE.md` is read by tools. Rewrite.
- [ ] `AGENTS.md:84` rule "a CLAUDE.md that is not @AGENTS.md". Rewrite to "a CLAUDE.md".
- [ ] `scripts/check_agents.ts:9` header item 4 `CLAUDE_COPY`, `:13` item 8 path `.claude/skills`. Update both.
- [ ] `scripts/check_agents.ts:154,161,163` `CLAUDE.md` check. Already covered; fail when it exists.
