# S-CLI-27: `fleet check` evaluates conformance rules on origin/main

| Field | Value |
|---|---|
| Spec ID | S-CLI-27 |
| Backlog item | GitHub issue #136; `docs/plans/2026-11-25-roadmap.md:66-76` (fleet command, theme 2; untracked draft at e89fac4, commit before claiming) |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | e89fac4 (branch `main`) |
| Branch | agent/S-CLI-27 |
| Depends on | S-CLI-26 |
| Conflicts with | S-CLI-18 (`scripts/gauntlet.py`), S-CLI-23 (`scripts/gauntlet.py`), S-CLI-28 (`src/mattstack/commands/fleet.py`, `scripts/gauntlet.py`, `docs/commands.md` Fleet section); S-CLI-20 (`docs/commands.md`); S-CLI-25 (`docs/commands.md`); S-CLI-40 (`scripts/gauntlet.py`); S-CLI-41 (`scripts/gauntlet.py`) |
| Files owned | `src/mattstack/fleet/rules.py` (new), `src/mattstack/commands/fleet.py` (adds `check`), `scripts/gauntlet.py`, `docs/commands.md` (`check` subsection of `## Fleet` only) |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 8 |
| Max changed lines | 500 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install`; plus the CLI rows below |
| Acceptance criteria | A1 to A8 in "Machine-checkable acceptance" |

## Context and verified citations

- Depends on S-CLI-26: `src/mattstack/fleet/registry.py` (`fleet_repos`, `clone_path`), `src/mattstack/fleet/status.py` (`run_git`, `--fetch` behaviour), and `src/mattstack/commands/fleet.py` (`fleet_app`).
- No-tests rule: `~/dev/agent-run-edit/repos/mattstack-cli.yml:93` and `:138`. This spec adds no `tests/` files and runs no pytest.
- Target layout: `docs/plans/2026-11-25-roadmap.md:23-32` (AGENTS.md only; skills at `.agents/skills/<name>/SKILL.md` with `name` and `description` frontmatter; no tracked `.claude/`). Adapter names `.cursorrules`, `.cursor/rules`, `GEMINI.md` at `:27-28`. The "without cloning" intent is at `:72`.
- Repo state (verified, local `origin/main`, 2026-11-25): `django-ninja-boilerplate` has AGENTS.md and 7 skills; `django-matt-starter` tracks `.claude/`; `nextjs-starter` has AGENTS.md and nothing else flagged; `swift-ios-starter` tracks `.claude/` and has no AGENTS.md; `react-vite-b2b` tracks `.claude/`.
- Symlinked skill files (for example a `react-doctor` skill whose SKILL.md is a symlink into `node_modules`) are described in the roadmap at `:55-58`. A symlink blob holds only the target path, so its frontmatter cannot be read from the tree.
- Tree reads: `git ls-tree -r -z --full-tree origin/main` gives mode, type, sha, and path. `git cat-file blob <sha>` reads content. No checkout occurs.
- Install gate hook: `scripts/gauntlet.py:290` (`_gate_install`) and `:343` (`return _smoke_python_pin(...)`), verified in S-CLI-26.
- Docs anchor: `docs/commands.md` `## Config file format` at line 836 (verified in S-CLI-26); `## Fleet` is inserted before it by S-CLI-26.

## Goal and non-goals

Goal: `mattstack fleet check` evaluates a registry of conformance rules against each present clone's `origin/main` tree and prints a repo-by-rule matrix. `--json` gives the same data. Exit 1 if any rule FAILs. SKIPPED never fails the command.

Rules (initial set, in `RULES`):
- `R1 agents-md`: root `AGENTS.md` is a blob. Violation: `AGENTS.md missing`.
- `R2 no-claude-md`: no root `CLAUDE.md`. Violation: `CLAUDE.md present`.
- `R3 no-harness-adapters`: no tracked `.cursorrules`, `GEMINI.md`, or path under `.cursor/rules/`. One violation per path.
- `R4 no-tracked-claude-dir`: no tracked path matching `(^|/)\.claude/`. Report the first five paths and a count.
- `R5 skills-frontmatter`: for every `.agents/skills/<name>/` (paths with at least three `/` segments), `SKILL.md` must exist. If it is a symlink (mode `120000`), add a note and do not fail. Otherwise its frontmatter must have non-empty `name:` and `description:` lines.

Non-goals:
- No checkout, pull, or write to any clone.
- No `--repos` filter (not requested).
- No additional rules beyond R1 to R5. The registry makes adding one a single `Rule` entry.
- No `tests/` changes, no new dependency.

## Implementation steps

1. **Create `src/mattstack/fleet/rules.py`.**
   - `@dataclass(frozen=True) class TreeEntry` with `mode`, `sha`, `path`.
   - `@dataclass(frozen=True) class TreeSnapshot` with `sha: str` and `entries: dict[str, TreeEntry]`. `TreeSnapshot.load(path: Path) -> TreeSnapshot | str`: returns an error string when `origin/main` is missing (`git rev-parse --verify -q origin/main^{commit}`). Otherwise it runs `git ls-tree -r -z --full-tree origin/main` via `run_git` from `fleet/status.py`, and splits on `\0`. `blob(path) -> str` runs `git cat-file blob <sha>` via `run_git`, decodes UTF-8 with `errors="replace"`.
   - `@dataclass(frozen=True) class RuleOutcome` with `violations: tuple[str, ...]` and `notes: tuple[str, ...]`. Status is FAIL if violations are present, otherwise PASS.
   - `@dataclass(frozen=True) class Rule` with `rule_id: str`, `summary: str`, and `evaluate: Callable[[TreeSnapshot], RuleOutcome]`.
   - `RULES: tuple[Rule, ...]` with R1 to R5 in the order above. R5 finds skill names from the third path segment of entries under `.agents/skills/`.

2. **Edit `src/mattstack/commands/fleet.py`.** Add `@fleet_app.command("check")` with `--root PATH` (same default as `list`), `--fetch`, and `--json`. For each `fleet_repos()` entry: if the clone is absent, emit SKIPPED for every rule with reason `no clone`. If `--fetch` is given and the clone is present, run the fetch as in S-CLI-26. Load the snapshot; if it fails, SKIPPED with the error. Otherwise evaluate every rule.
   - Table: rows are repos; columns are rule ids; cells PASS, FAIL, or SKIPPED. Below the table, list each FAIL as `<repo>: <rule_id>: <violation>`.
   - JSON schema:
     ```
     {"ref": "origin/main",
      "rules": [{"id": str, "summary": str}],
      "repos": [{"key": str, "name": str, "path": str,
                 "status": "checked" | "skipped", "skip_reason": str | null,
                 "sha": str | null,
                 "results": {rule_id: {"status": "PASS" | "FAIL" | "SKIPPED",
                                       "violations": [str], "notes": [str]}}}],
      "failed": int}
     ```
   - Exit 1 if `failed > 0`, else 0.

3. **Edit `scripts/gauntlet.py`.** Extend `_smoke_fleet` (added in S-CLI-26) with a check pass. Create a second repo, `nextjs-starter`, in the fixture root that tracks a `CLAUDE.md`. Run `<executable> fleet check --root <work>/fleet/root --json`, assert exit 1, and assert R2 is FAIL for `nextjs-starter` and PASS for `django-ninja-boilerplate`. Use the same `env` prefix for git as S-CLI-26.

4. **Edit `docs/commands.md`.** Add a `check` subsection under `## Fleet` covering the rules, exit codes, SKIPPED semantics, and `--json` schema.

## Machine-checkable acceptance

Fixture F2 (builds on F1 from S-CLI-26; `$T` and `$G` as defined there):

```bash
mkdir -p "$T/seed/nextjs-starter" && git -C "$T/seed/nextjs-starter" init -q -b main
printf '# Agents\n' > "$T/seed/nextjs-starter/AGENTS.md"
printf '# Claude\n' > "$T/seed/nextjs-starter/CLAUDE.md"
mkdir -p "$T/seed/nextjs-starter/.claude" && echo '{}' > "$T/seed/nextjs-starter/.claude/settings.json"
echo 'rules' > "$T/seed/nextjs-starter/.cursorrules"
mkdir -p "$T/seed/nextjs-starter/.agents/skills/foo" "$T/seed/nextjs-starter/.agents/skills/bar"
printf '# no frontmatter\n' > "$T/seed/nextjs-starter/.agents/skills/foo/SKILL.md"
printf -- '---\nname: bar\ndescription: demo\n---\n' > "$T/seed/nextjs-starter/.agents/skills/bar/SKILL.md"
$G -C "$T/seed/nextjs-starter" add -A && $G -C "$T/seed/nextjs-starter" commit -qm init
git clone -q --bare "$T/seed/nextjs-starter" "$T/origin-next.git"
git clone -q "$T/origin-next.git" "$T/root/nextjs-starter"
```

Repoint the clone so that `origin` is the bare repo built here: `git -C "$T/root/nextjs-starter" remote -v` must show `$T/origin-next.git`. `git clone` already sets this.

| ID | Cwd | Exact command | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `uv run mattstack fleet check --help` | exit 0 | output contains `--json`, `--fetch`, and `--root` |
| A2 | repo root, after F1 | `uv run mattstack fleet check --root "$T/root" --json > "$T/a2.json"; echo $?` | prints `0` | `python -c "import json; r=json.load(open('$T/a2.json')); d=[x for x in r['repos'] if x['name']=='django-ninja-boilerplate'][0]; assert all(v['status']=='PASS' for v in d['results'].values()); s=[x for x in r['repos'] if x['name']=='fastapi-boilerplate'][0]; assert s['status']=='skipped' and s['skip_reason']; assert r['failed']==0"` |
| A3 | repo root, after F2 | `uv run mattstack fleet check --root "$T/root" --json > "$T/a3.json"; echo $?` | prints `1` | `python -c "import json; r=json.load(open('$T/a3.json')); n=[x for x in r['repos'] if x['name']=='nextjs-starter'][0]['results']; assert n['no-claude-md']['status']=='FAIL'"`  |
| A4 | repo root, after F2 | same JSON as A3 | exit (from A3) | `no-tracked-claude-dir` FAIL; `no-harness-adapters` FAIL; `skills-frontmatter` FAIL with a violation mentioning `foo` and no violation mentioning `bar` |
| A5 | repo root, after F2 | `rm "$T/root/nextjs-starter/AGENTS.md"; uv run mattstack fleet check --root "$T/root" --json` | exit 1 (from A3) | `agents-md` is PASS for `nextjs-starter`, because the evaluation reads `origin/main`, not the working tree; `git -C "$T/root/nextjs-starter" status --porcelain` still shows ` D AGENTS.md` (uncommitted change untouched) |
| A6 | repo root, after F2 | `uv run mattstack fleet check --root "$T/root"` | exit 1 | output contains `FAIL` and `nextjs-starter` |
| A7 | repo root | `uv run python -c "from mattstack.fleet.rules import RULES; print([r.rule_id for r in RULES])"` | exit 0 | output lists exactly the five ids `agents-md`, `no-claude-md`, `no-harness-adapters`, `no-tracked-claude-dir`, `skills-frontmatter` |
| A8 | repo root, after F2 | `mkdir -p "$T/seed/nextjs-starter/.agents/skills/baz" && ln -s ../../../node_modules/x/SKILL.md "$T/seed/nextjs-starter/.agents/skills/baz/SKILL.md" && $G -C "$T/seed/nextjs-starter" add -A && $G -C "$T/seed/nextjs-starter" commit -qm baz && git -C "$T/seed/nextjs-starter" push -q "$T/origin-next.git" main && uv run mattstack fleet check --root "$T/root" --fetch --json > "$T/a8.json"` | exit 1 (other failures remain) | `skills-frontmatter` for `nextjs-starter` has no violation mentioning `baz`, and has a note containing `symlink` |

The gate row is `uv run python scripts/gauntlet.py --gate install`, which runs `_smoke_fleet` with the check pass.

## Stop conditions and PR evidence

Stop and report if:
- S-CLI-26 is not merged, or `fleet/status.py` `run_git` has a different signature from what is described above.
- `scripts/gauntlet.py` has changed under S-CLI-18 so that `_smoke_fleet` is absent.
- Implementation needs a file outside Files owned. Do not add tests.

PR evidence: the JSON output for A2 and A3, the table output for A6, and the verification results. Do not push to `main`. Conventional Commit subject, for example `feat(fleet): add fleet check conformance rules`.
