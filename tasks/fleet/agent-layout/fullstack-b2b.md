Umbrella: mattjaikaran/agent-run, "Track AGENTS.md migration across repos". Size: S.
Contract: https://github.com/mattjaikaran/mattstack-cli/blob/main/docs/agent-layout.md

## Contract (summary)
- Root `AGENTS.md` is the only agent instruction file. Max 200 lines, all links resolve.
- Skills: `.agents/skills/<name>/SKILL.md`, frontmatter `name` (equals dir) and `description`.
- `SKILLS.md` at root indexes every skill and is linked from `AGENTS.md`. Required only when `.agents/skills/` exists.
- Never tracked: `CLAUDE.md` (any depth), `.claude/**`, `.cursor/**`, `.cursorrules`, `.windsurf/**`, `GEMINI.md`, `.github/copilot-instructions.md`.
- `.claude/` and `.cursor/` are gitignored.

## Current state (origin/main)
- `AGENTS.md` is the instruction file. No `CLAUDE.md`.
- One vendored file tracked: `.claude/skills/react-doctor/SKILL.md`, a real file, not a symlink. No manifest declares `react-doctor`, so it has no upstream.
- `scripts/check_agents_md.py`: line 6 docstring; line 25 `SKILLS = ROOT / ".claude" / "skills"`; line 53 `check_claude()`; line 61 `check_skills()`; line 80 `CHECKS`.
- `Makefile` line 15 help text; line 74 `agents-check`. `.pre-commit-config.yaml` line 18 `check-agents-md`.
- `.gitignore` line 26 ignores only `.claude/settings.local.json`.

## Decision
Delete the react-doctor skill. The repo has no react-doctor dependency, and adding one only to give a symlink a target is not worth it.

## Work
- [ ] `git rm -r .claude/skills`; remove the empty `.claude/` tree.
- [ ] `scripts/check_agents_md.py`: `SKILLS` (line 25) becomes `.agents/skills`. `check_claude()` (line 53) fails when `CLAUDE.md` exists. Fail on `.claude/skills`. Update docstring (line 6).
- [ ] `Makefile` line 15 help text.
- [ ] `.gitignore` line 26: replace with `.claude/`; add `.cursor/`.

## Acceptance
- [ ] `make agents-check` exits 0 on a clean checkout.
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.
- [ ] `git check-ignore -v .claude/x .cursor/x` reports both ignored.

## Content references (origin/main)
- [ ] `AGENTS.md:45` table row says `make agents-check` checks "CLAUDE.md". Rewrite.
- [ ] `.pre-commit-config.yaml:16` comment says `CLAUDE.md` must not duplicate. Rewrite.
- [ ] `scripts/check_agents_md.py:5-6` docstring says `CLAUDE.md` must not duplicate `AGENTS.md`, and skills live in `.claude/skills/`. Rewrite both.
- [ ] `scripts/check_agents_md.py:24` `CLAUDE` constant and `:57` message. Keep "must be absent" only.
