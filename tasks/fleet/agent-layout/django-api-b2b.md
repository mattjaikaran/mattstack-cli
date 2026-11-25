Umbrella: mattjaikaran/agent-run, "Track AGENTS.md migration across repos". Size: S.
Contract: https://github.com/mattjaikaran/mattstack-cli/blob/main/docs/agent-layout.md

## Contract (summary)
- Root `AGENTS.md` is the only agent instruction file. Max 200 lines, all links resolve.
- Skills: `.agents/skills/<name>/SKILL.md`, frontmatter `name` (equals dir) and `description`.
- `SKILLS.md` at root indexes every skill and is linked from `AGENTS.md`. Required only when `.agents/skills/` exists.
- Never tracked: `CLAUDE.md` (any depth), `.claude/**`, `.cursor/**`, `.cursorrules`, `.windsurf/**`, `GEMINI.md`, `.github/copilot-instructions.md`.
- `.claude/` and `.cursor/` are gitignored.

## Current state (origin/main)
- `CLAUDE.md` is tracked and holds only `@AGENTS.md`.
- No skills, no `SKILLS.md`. `.claude/` is not in `.gitignore`.
- `scripts/check_agent_docs.py`: line 27 `CLAUDE = ROOT / "CLAUDE.md"`; line 77 `def check_claude()`; line 89 calls it from `main()`.

## Work
- [ ] `git rm CLAUDE.md`.
- [ ] `scripts/check_agent_docs.py`: remove `CLAUDE` (line 27), `check_claude()` (line 77) and its call (line 89). Add a failure when `CLAUDE.md` exists at any depth.
- [ ] `.gitignore`: add `.claude/` and `.cursor/`.
- [ ] `grep -rn CLAUDE Makefile .github .pre-commit-config.yaml README.md AGENTS.md`; fix every hit.

## Acceptance
- [ ] `python3 scripts/check_agent_docs.py` exits 0 on a clean checkout.
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.
- [ ] A test branch adding `CLAUDE.md` makes the checker fail.

## Content references (origin/main)
- [ ] `AGENTS.md:3` says `CLAUDE.md` "only imports it". Rewrite to say no `CLAUDE.md` exists.
- [ ] `AGENTS.md:139` names `.claude/skills/<name>/SKILL.md` as the skill location. Change to `.agents/skills/` or delete the sentence if no skills exist.
- [ ] `scripts/check_agent_docs.py:5,9,10` docstring rules mention `CLAUDE.md`. Rewrite.
- [ ] `scripts/check_agent_docs.py:81` message: remove with `check_claude()`.
