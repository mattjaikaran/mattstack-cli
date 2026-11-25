Umbrella: mattjaikaran/agent-run, "Track AGENTS.md migration across repos". Size: M.
Contract: https://github.com/mattjaikaran/mattstack-cli/blob/main/docs/agent-layout.md

## Contract (summary)
- Root `AGENTS.md` is the only agent instruction file. Max 200 lines, all links resolve.
- Skills: `.agents/skills/<name>/SKILL.md`, frontmatter `name` (equals dir) and `description`.
- `SKILLS.md` at root indexes every skill and is linked from `AGENTS.md`. Required only when `.agents/skills/` exists.
- Never tracked: `CLAUDE.md` (any depth), `.claude/**`, `.cursor/**`, `.cursorrules`, `.windsurf/**`, `GEMINI.md`, `.github/copilot-instructions.md`.
- `.claude/` and `.cursor/` are gitignored.

## Current state (origin/main)
- `CLAUDE.md` is tracked and holds only `@AGENTS.md`.
- Two skills tracked: `.claude/skills/migration-conflict/SKILL.md`, `.claude/skills/new-endpoint/SKILL.md`. No `SKILLS.md`.
- `.gitignore` lines 102-106 commit `.claude/skills/`, `.claude/agents/`, `.claude/settings.json`. Line 108 ignores `.cursor/`.
- `scripts/check_agent_docs.py`: line 32 `CLAUDE`; line 34 `IMPORT_LINE`; line 33 `DEFAULT_GLOBS` includes `.claude/skills/**/*.md`; lines 17-18 docstring.
- `.pre-commit-config.yaml` line 67 matches `\.claude/skills/.*\.md`.

## Work
- [ ] `git rm CLAUDE.md`.
- [ ] `git mv .claude/skills .agents/skills`. Remove the now-empty `.claude/` tree.
- [ ] Add `SKILLS.md` at root listing both skills, and link it from `AGENTS.md`.
- [ ] `.gitignore`: replace lines 102-106 with `.claude/`. Keep `.cursor/` at line 108.
- [ ] `scripts/check_agent_docs.py`: drop `CLAUDE` (line 32) and `IMPORT_LINE` (line 34). Set `DEFAULT_GLOBS` (line 33) to `.agents/skills/**/*.md`. Update docstring (lines 17-18). Fail when `CLAUDE.md` or `.claude/skills` exists.
- [ ] `.pre-commit-config.yaml` line 67: `\.claude/skills/` becomes `\.agents/skills/`; drop `CLAUDE`.
- [ ] `grep -rn ".claude/skills" docs tasks` and update paths.

## Acceptance
- [ ] `python3 scripts/check_agent_docs.py` exits 0 on a clean checkout.
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.
- [ ] Pre-commit runs on a change to `.agents/skills/**/SKILL.md`.

## Content references (origin/main)
- [ ] `AGENTS.md:3,5,108-110,113` describe `CLAUDE.md` and `.claude/skills/`. Rewrite to `.agents/skills/` and drop the `CLAUDE.md` import.
- [ ] `AGENTS.md:72` links `.claude/skills/migration-conflict/SKILL.md`. Update the link to `.agents/skills/...` after `git mv`, or the link breaks.
- [ ] `docs/architecture.md:101` links `../.claude/skills/migration-conflict/SKILL.md`. Update after `git mv`.
- [ ] `.pre-commit-config.yaml:64` description mentions `CLAUDE.md`. Rewrite.
- [ ] `Makefile:147` comment mentions `CLAUDE.md`. Rewrite.
- [ ] `scripts/check_agent_docs.py:7,16,17,49,107` docstring and rules mention `CLAUDE.md` and `docs/`, `tasks/`, `.claude/skills/`. Rewrite.
