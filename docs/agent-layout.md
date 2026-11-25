# Agent layout contract

Every mattstack boilerplate and every project mattstack generates follows
this layout. It works with any agent harness that reads `AGENTS.md`. The
repository's agent-docs checker enforces it in pre-commit and the gauntlet.

## Rules

1. `AGENTS.md` is the only agent instruction file. A component may have a
   nested `AGENTS.md` (for example `backend/AGENTS.md`); the nearest one wins.
2. `CLAUDE.md` does not exist anywhere in the tree. It is not allowed even as a
   one-line `@AGENTS.md` import.
3. No harness adapters are tracked: no `.cursorrules`, `.cursor/rules/`,
   `.windsurf/`, `.kiro/`, `GEMINI.md`, or `.github/copilot-instructions.md`.
4. Skills live in `.agents/skills/<name>/SKILL.md`. Each `SKILL.md` starts
   with YAML frontmatter that sets `name` (equal to `<name>`) and
   `description`. A skill shipped by a package may be a relative symlink into
   `node_modules`; move the link, do not copy its target.
5. Nothing under `.claude/` or `.cursor/` is tracked. `.gitignore` lists both
   directories whole:

   ```gitignore
   # Harness-local agent state
   .claude/
   .cursor/
   ```

6. Hard rules live in hooks and gates, not in prose. `AGENTS.md` links to
   `docs/` for reference material and stays under 200 lines.

## Checker requirements

Each repository's agent-docs checker (`scripts/check_agent_docs.py` or
`.ts`, whatever the repo already uses) fails when:

- `AGENTS.md` is missing or a relative link in it does not resolve;
- `CLAUDE.md` exists at any depth;
- `git ls-files .claude .cursor .cursorrules .windsurf GEMINI.md` prints a path;
- a `.agents/skills/*/SKILL.md` lacks `name` or `description` frontmatter,
  or its symlink does not resolve after dependencies are installed.

## Migrating a repository

Skills that are symlinks keep the same directory depth, so their targets
stay valid:

```bash
mkdir -p .agents/skills
git mv .claude/skills/<name> .agents/skills/<name>
git rm -r --cached .claude CLAUDE.md .cursorrules 2>/dev/null
```

Then update the checker, `.gitignore`, pre-commit `files:` patterns, and any
prose that names `.claude/` or `CLAUDE.md`, all in the same pull request.
`mattstack fleet check` (S-CLI-27) verifies every boilerplate against this
contract.
