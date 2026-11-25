Umbrella: mattjaikaran/agent-run, "Track AGENTS.md migration across repos". Size: S.
Contract: https://github.com/mattjaikaran/mattstack-cli/blob/main/docs/agent-layout.md

## Contract (summary)
- Root `AGENTS.md` is the only agent instruction file. Max 200 lines, all links resolve.
- Skills: `.agents/skills/<name>/SKILL.md`, frontmatter `name` (equals dir) and `description`.
- `SKILLS.md` at root indexes every skill and is linked from `AGENTS.md`. Required only when `.agents/skills/` exists.
- Never tracked: `CLAUDE.md` (any depth), `.claude/**`, `.cursor/**`, `.cursorrules`, `.windsurf/**`, `GEMINI.md`, `.github/copilot-instructions.md`.
- `.claude/` and `.cursor/` are gitignored.

## Current state (origin/main)
- No `CLAUDE.md` tracked. `AGENTS.md` is the instruction file.
- One skill tracked: `.claude/skills/migrations/SKILL.md`. No `SKILLS.md`.
- `scripts/check_agents_docs.py`: line 14 `SKILLS = ROOT / ".claude" / "skills"`; line 62 `check_claude()`; line 81 `check_skills()`; line 103 `main()` calls both.
- Wired via `Makefile` `agents-check` (line 60), `justfile` (line 61), `.pre-commit-config.yaml` `check-agents-docs` (line 34).
- `.gitignore` has no `.claude/` or `.cursor/` rule.

## Work
- [ ] `git mv .claude/skills/migrations .agents/skills/migrations`; remove the empty `.claude/` tree.
- [ ] Add `SKILLS.md` at root listing the migrations skill; link it from `AGENTS.md`.
- [ ] `scripts/check_agents_docs.py`: set `SKILLS` (line 14) to `.agents/skills`. `check_claude()` (line 62) fails when `CLAUDE.md` exists. `check_skills()` (line 81) requires `SKILLS.md` and the new path. Fail when `.claude/skills` exists.
- [ ] `.gitignore`: add `.claude/` and `.cursor/`.
- [ ] `Makefile` line 15 help text: update if it names `.claude/skills`.

## Acceptance
- [ ] `just agents-check` and `make agents-check` exit 0 on a clean checkout.
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.
- [ ] `check-agents-docs` pre-commit hook still runs.

## Content references (origin/main)
- [ ] `AGENTS.md:74` links `.claude/skills/migrations/SKILL.md`. Update to `.agents/skills/migrations/SKILL.md` after `git mv`, or the link breaks.
- [ ] `README.md:120` directory tree lists `.claude/`. Update the tree.
- [ ] `docs/architecture.md:68` names `.claude/skills/migrations/`. Update.
- [ ] `scripts/check_agents_docs.py:13,65` `CLAUDE` constant and "must not exist" message. Keep the rule; confirm it stays.
