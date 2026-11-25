<!-- EDIT ISSUE #1 -->
Umbrella: mattjaikaran/agent-run, "Track AGENTS.md migration across repos". Size: M.
Contract: https://github.com/mattjaikaran/mattstack-cli/blob/main/docs/agent-layout.md

## Contract (summary)
- Root `AGENTS.md` is the only agent instruction file. Max 200 lines, all links resolve.
- Skills: `.agents/skills/<name>/SKILL.md`, frontmatter `name` (equals dir) and `description`.
- `SKILLS.md` at root indexes every skill and is linked from `AGENTS.md`. Required only when `.agents/skills/` exists.
- Never tracked: `CLAUDE.md` (any depth), `.claude/**`, `.cursor/**`, `.cursorrules`, `.windsurf/**`, `GEMINI.md`, `.github/copilot-instructions.md`.
- `.claude/` and `.cursor/` are gitignored.

## Corrections to the original issue
- Skills go to `.agents/skills/`, not `.claude/skills/`.
- `tasks/specs/README.md` does not exist on origin/main. Remove the link or create the file.
- `docs/` does not exist on origin/main. Remove the link or create the directory.
- README says Swift 6.0; `Package.swift` says `swift-tools-version:6.2`. Make them agree on 6.2.

## Current state (origin/main)
- No `AGENTS.md`, no `SKILLS.md`, no skills.
- `.claude/settings.local.json` is tracked.
- `.gitignore` ignores only `.claude/worktrees/`.
- `.github/workflows/ci.yml`: `swift build -v` (line 24), `swift test -v` (line 27), `swiftlint ... || true` (line 40), `xcodebuild` builds (lines 53-58, 72-76).

## Work
- [ ] Create root `AGENTS.md` (under 200 lines) with the build, test and lint commands above. State that `swiftlint` is advisory until its `|| true` is removed.
- [ ] `git rm --cached .claude/settings.local.json`.
- [ ] `.gitignore`: replace the `.claude/worktrees/` line with `.claude/` and add `.cursor/`.
- [ ] Add `SKILLS.md` only when a skill is added. Do not add `.agents/skills/` empty.
- [ ] Change the README's Swift version to 6.2. `Package.swift` (`swift-tools-version:6.2`) is the source of truth; do not edit it.
- [ ] Do not mention `tasks/specs/` or `docs/` in AGENTS.md; neither exists in this repo.
- [ ] Add a step to `.github/workflows/ci.yml` that fails when `git ls-files CLAUDE.md '*/CLAUDE.md' .claude .cursor .cursorrules` prints anything.

## Acceptance
- [ ] `git ls-files | grep -E '(^|/)(CLAUDE\.md|\.claude/|\.cursor/)'` prints nothing.
- [ ] `swift build -v` and `swift test -v` pass on macOS CI.
- [ ] Every link in `AGENTS.md` resolves.

## Content references (origin/main)
- [ ] `.gitignore:29` ignores `.claude/worktrees/` only. Replace with `.claude/`, which covers it.
