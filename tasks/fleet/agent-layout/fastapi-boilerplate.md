Umbrella: mattjaikaran/agent-run, "Track AGENTS.md migration across repos". Size: S.
Contract: https://github.com/mattjaikaran/mattstack-cli/blob/main/docs/agent-layout.md

## Contract (summary)
- Root `AGENTS.md` is the only agent instruction file. Max 200 lines, all links resolve.
- Skills: `.agents/skills/<name>/SKILL.md`, frontmatter `name` (equals dir) and `description`.
- `SKILLS.md` at root indexes every skill and is linked from `AGENTS.md`. Required only when `.agents/skills/` exists.
- Never tracked: `CLAUDE.md` (any depth), `.claude/**`, `.cursor/**`, `.cursorrules`, `.windsurf/**`, `GEMINI.md`, `.github/copilot-instructions.md`.
- `.claude/` and `.cursor/` are gitignored.

## Current state (origin/main)
- `AGENTS.md` is the instruction file. No `CLAUDE.md`, no skills, no `SKILLS.md` tracked.
- `scripts/check_agent_docs.py` has the old alias rule, which is inverted by this ticket:
  - line 33 `SKILLS = ROOT / ".claude" / "skills"`; line 34 `ALT_SKILLS = ROOT / ".agents" / "skills"`
  - line 96 `check_claude()`; line 122 `check_skills()`
  - line 126-129: requires `.agents/skills` to be a symlink to `.claude/skills`. This is the inverted rule.
- `.pre-commit-config.yaml` line 38 matches `^(AGENTS|CLAUDE)\.md$` and `^\.claude/skills/.*/SKILL\.md$`.
- `.gitignore` line 41 ignores only `.claude/settings.local.json`. No `.cursor/` rule.

## Work
- [ ] `scripts/check_agent_docs.py`: remove `SKILLS` (line 33). `.agents/skills` becomes the only skills directory. Delete the symlink requirement at lines 126-129. Require a real directory and a `SKILLS.md` index. Fail on `.claude/skills` and on `CLAUDE.md`.
- [ ] `check_claude()` (line 96): fail when `CLAUDE.md` exists.
- [ ] `.pre-commit-config.yaml` line 38: match `^AGENTS\.md$` and `^\.agents/skills/.*/SKILL\.md$`.
- [ ] `.gitignore` line 41: replace with `.claude/`; add `.cursor/`.
- [ ] Confirm `justfile` and `Makefile` `agents-check` still call the checker.

## Acceptance
- [ ] `just agents-check` exits 0 on a clean checkout.
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.
- [ ] A test branch with `.agents/skills/x/SKILL.md` but no `SKILLS.md` fails the checker.
- [ ] A test branch with a `.agents/skills` symlink fails the checker.

## Content references (origin/main)
- [ ] `scripts/check_agent_docs.py:5-6` docstring says `CLAUDE.md` "may only import" `AGENTS.md`, and skills live in `.claude/skills`. Rewrite both.
- [ ] `scripts/check_agent_docs.py:12-13` rules `link` and `claude` describe `CLAUDE.md`. Remove the `claude` rule and the `CLAUDE.md` link target.
- [ ] `scripts/check_agent_docs.py:15` docstring says skills outside `.claude/skills`. Rewrite.
- [ ] `scripts/check_agent_docs.py:32` `CLAUDE` constant and `:100` message. Remove the import rule; keep "must not exist".
- [ ] `CHANGELOG.md:14` history: leave unchanged.
