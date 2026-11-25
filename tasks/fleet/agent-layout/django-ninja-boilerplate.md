Umbrella: mattjaikaran/agent-run, "Track AGENTS.md migration across repos". Size: S.
Contract: https://github.com/mattjaikaran/mattstack-cli/blob/main/docs/agent-layout.md

This is the reference layout. `AGENTS.md` links `SKILLS.md` (AGENTS.md lines 5 and 150), the skills live in `.agents/skills/`, and `scripts/check_agent_docs.py` enforces it (`SKILLS_DIR` line 31, `SKILLS_INDEX` line 32). Only ignore rules are missing.

## Contract (summary)
- Root `AGENTS.md` is the only agent instruction file. Max 200 lines, all links resolve.
- Skills: `.agents/skills/<name>/SKILL.md`, frontmatter `name` (equals dir) and `description`.
- `SKILLS.md` at root indexes every skill and is linked from `AGENTS.md`.
- Never tracked: `CLAUDE.md` (any depth), `.claude/**`, `.cursor/**`, `.cursorrules`, `.windsurf/**`, `GEMINI.md`, `.github/copilot-instructions.md`.
- `.claude/` and `.cursor/` are gitignored.

## Current state (origin/main)
- `.gitignore` line 134 ignores `.claude/`. No `.cursor/` rule.
- `.dockerignore` excludes neither `.claude/` nor `.cursor/`.

## Work
- [ ] `.gitignore`: add `.cursor/` next to line 134.
- [ ] `.dockerignore`: add `.claude/` and `.cursor/` in the local-development block (around line 118).

## Acceptance
- [ ] `git check-ignore -v .cursor/x .claude/x` reports both ignored.
- [ ] `docker build` context excludes both (check with `--progress=plain`).
- [ ] `python3 scripts/check_agent_docs.py` still passes.

## Content references (origin/main, `git grep -nE 'CLAUDE\.md|\.claude/'`)
- [ ] `scripts/check_agent_docs.py:33` `CLAUDE_NAME` and `:12` rule 6 already say "does not exist". Keep the rule; rename the constant to `FORBIDDEN_CLAUDE` if desired.
- [ ] `docs/CONSTRAINT_TOOLS.md:82` AGENT-DOCS row: confirm wording matches the current checker.
- [ ] `SKILLS.md:6` forbids copying into `.claude/skills/`. Keep.
- [ ] `CHANGELOG.md` history mentions: leave unchanged.
- [ ] Local `HEAD` lags `origin/main` by 3 commits. Re-verify against `origin/main` before merge.
