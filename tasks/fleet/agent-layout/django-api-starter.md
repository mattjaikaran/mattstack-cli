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
- `scripts/check_agent_docs.py`: line 18 `CLAUDE = ROOT / "CLAUDE.md"`; line 46 `def claude_errors()`; `main()` calls it.

## Work
- [ ] `git rm CLAUDE.md`.
- [ ] `scripts/check_agent_docs.py`: remove `CLAUDE` (line 18), `claude_errors()` (line 46) and its call. Add a failure when `CLAUDE.md` exists at any depth.
- [ ] `.gitignore`: add `.claude/` and `.cursor/`.
- [ ] `grep -rn CLAUDE Makefile .github .pre-commit-config.yaml README.md AGENTS.md`; fix every hit.

## Acceptance
- [ ] `python3 scripts/check_agent_docs.py` exits 0 on a clean checkout.
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.
- [ ] A test branch adding `CLAUDE.md` makes the checker fail.

## Content references (origin/main)
- [ ] `AGENTS.md:4` says `CLAUDE.md` "only imports it". Rewrite.
- [ ] `AGENTS.md:111` names `.claude/skills/<name>/SKILL.md`. Change to `.agents/skills/`.
- [ ] `scripts/check_agent_docs.py:7` docstring; `:47` docstring and `:53` message of `claude_errors()`. Remove with the function.
