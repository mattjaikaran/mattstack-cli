# S-CLI-28: `fleet issue` opens one issue per matching repo, skipping duplicates

| Field | Value |
|---|---|
| Spec ID | S-CLI-28 |
| Backlog item | GitHub issue #137; `docs/plans/2026-11-25-roadmap.md:66-76` (fleet command, theme 2; untracked draft at e89fac4, commit before claiming) |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | e89fac4 (branch `main`) |
| Branch | agent/S-CLI-28 |
| Depends on | S-CLI-26 |
| Conflicts with | S-CLI-18 (`scripts/gauntlet.py`), S-CLI-23 (`scripts/gauntlet.py`), S-CLI-27 (`src/mattstack/commands/fleet.py`, `scripts/gauntlet.py`, `docs/commands.md` Fleet section); S-CLI-20 (`docs/commands.md`); S-CLI-25 (`docs/commands.md`); S-CLI-40 (`scripts/gauntlet.py`); S-CLI-41 (`scripts/gauntlet.py`) |
| Files owned | `src/mattstack/fleet/issue.py` (new), `src/mattstack/commands/fleet.py` (adds `issue`), `scripts/gauntlet.py`, `docs/commands.md` (`issue` subsection of `## Fleet` only) |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 8 |
| Max changed lines | 500 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install`; plus the CLI rows below |
| Acceptance criteria | A1 to A8 in "Machine-checkable acceptance" |

## Context and verified citations

- Depends on S-CLI-26: `src/mattstack/fleet/registry.py` (`fleet_repos`, `FleetRepo.slug` and `FleetRepo.name`) and `src/mattstack/commands/fleet.py` (`fleet_app`). Both verified in S-CLI-26.
- No-tests rule: `~/dev/agent-run-edit/repos/mattstack-cli.yml:93` and `:138` (verified). The mocking described in the assignment is replaced by a fake `gh` binary placed first on `PATH`, which keeps the tests network-free and needs no test files.
- Roadmap intent: `docs/plans/2026-11-25-roadmap.md:74-76` describes `fleet issue` with a template, one issue per repo, skipping repos with the same title, and a `fleet` label with a tracking link. This spec deliberately differs: it uses `--body-file` (per the assignment), `--label` is explicit and repeatable, and there is no automatic `fleet` label or tracking link.
- `gh` pattern: `src/mattstack/commands/protect.py:129` `_repo_slug(path, gh_bin)` and `:145` `_apply_ruleset(..., gh_bin)` take the binary name as a parameter; `:170` `run_protect(..., gh_bin: str = "gh")`. Argv lists, no shell (verified).
- Table and error helpers: `utils/console.py:63` `print_error` and `:91` `create_table` (verified).
- GitHub search is keyword-based, so an exact client-side title comparison is needed; a search hit on a different title must not count as a duplicate.

## Goal and non-goals

Goal: `mattstack fleet issue --title T --body-file F --repos GLOB [--label L]... [--dry-run]` opens one issue in each registry repo whose name matches `GLOB`, unless an open issue with exactly title `T` already exists there. It prints one line per repo and exits 1 if any repo errored.

Non-goals:
- No automatic labels, no tracking-issue link, no template rendering (the body is the file as written).
- No editing, closing, or commenting on existing issues.
- No clones needed; `--repo owner/name` is passed to `gh`.
- No `--json` output for this command.
- No retries.
- No `tests/` changes, no new dependency.

## Implementation steps

1. **Create `src/mattstack/fleet/issue.py`.**
   - `select_repos(pattern: str) -> list[FleetRepo]`: `fnmatch.fnmatchcase(repo.name, pattern)` over `fleet_repos()`. Matches registry names only, never keys or user-config repos.
   - `list_argv(gh_bin, slug, title) -> list[str]`: `[gh_bin, "issue", "list", "--repo", slug, "--state", "open", "--search", f'in:title "{title.replace(chr(34), "")}"', "--json", "title", "--limit", "200"]`.
   - `create_argv(gh_bin, slug, title, body_file, labels) -> list[str]`: `[gh_bin, "issue", "create", "--repo", slug, "--title", title, "--body-file", str(body_file.resolve()), *flatten(("--label", L) for L in labels)]`.
   - `open_titles(gh_bin, slug, title) -> list[str]`: runs `list_argv` with `subprocess.run(..., capture_output=True, text=True, timeout=60, check=False, env={**os.environ, "GH_PROMPT_DISABLED": "1"})` and `# nosec B603`. Non-zero exit or invalid JSON raises `IssueListError`.
   - Per repo, `run_issue(...)` returns a status of `created`, `skipped`, `would-create`, or `error`:
     - Run `open_titles`. On `IssueListError` or `FileNotFoundError`, record `error` and do not create.
     - If any title equals `title` exactly, record `skipped` with the match.
     - If `dry_run`, record `would-create` with `create_argv` (printed through `shlex.join`) and no create call.
     - Otherwise run `create_argv`. On success, the URL is the last stdout line starting with `https://`. On failure, record `error` with the first stderr line.
   - If the `gh` binary is not found, stop before any repo and report `gh CLI not found: <bin>`.

2. **Edit `src/mattstack/commands/fleet.py`.** Add `@fleet_app.command("issue")` with:
   - `--title TEXT` (required; must be non-empty and contain no newline, otherwise exit 2).
   - `--body-file PATH` (required; `exists=True`, `dir_okay=False`, `readable=True`, so a missing file exits 2).
   - `--repos TEXT` (required; a glob). If nothing matches, exit 2 and print the glob.
   - `--label TEXT` (repeatable).
   - `--dry-run` (flag). It still runs the read-only list call, so output includes both the list argv and the create argv.
   - No `--gh-bin` option. `open_titles` and `run_issue` take `gh_bin: str = "gh"` as an internal keyword parameter, as `commands/protect.py:170` does. Acceptance rows put a stub `gh` first on `PATH`.
   - Output lines: `created  <slug>  <url>`, `skipped  <slug>  open issue with this title exists`, `would-create  <slug>`, followed by the argv on the next indented line, or `error  <slug>  <message>`. Then one summary line with counts.
   - Exit 1 if any `error`, otherwise 0.

3. **Edit `scripts/gauntlet.py`.** Extend `_smoke_fleet` (from S-CLI-26) with an issue pass. Write a fake `gh` script at `<work>/fleet/gh` (recipe below). With `<work>/fleet` prepended to `PATH`, run `<executable> fleet issue --title "Smoke title" --body-file <work>/fleet/body.md --repos 'nextjs-*' --dry-run` and assert exit 0, and that the log has no `issue create` line. Use the same `env` prefix as in S-CLI-26.

4. **Edit `docs/commands.md`.** Add an `issue` subsection under `## Fleet`. Cover the flags, the exact-title dedupe rule, `--dry-run` behaviour, the exit codes, and the difference from the roadmap (no automatic label, no tracking link).

## Machine-checkable acceptance

Fixture F4 (fake gh). Create it once per shell after `$T` is set from F1 in S-CLI-26. The heredoc delimiter is quoted, so `$` stays literal inside the script:

```bash
mkdir -p "$T/gh-fake" && cat > "$T/gh-fake/gh" <<'SH'
#!/bin/sh
echo "$*" >> "$FAKE_GH_LOG"
slug=$(echo "$*" | sed -n 's/.*--repo \([^ ]*\).*/\1/p')
case "$1 $2" in
  "issue list")
    [ -n "$FAKE_FAIL_LIST" ] && { echo "boom" >&2; exit 1; }
    if [ "$slug" = "$FAKE_EXISTING_REPO" ]; then printf '%s' "$FAKE_EXISTING_JSON"; else printf '[]'; fi ;;
  "issue create")
    echo "https://github.com/$slug/issues/1" ;;
esac
SH
chmod +x "$T/gh-fake/gh"
printf 'Body text\n' > "$T/body.md"
export FAKE_GH_LOG="$T/gh.log"; : > "$FAKE_GH_LOG"
mkdir -p "$T/nogh"; UV=$(command -v uv)
```

Each acceptance row resets the log with `: > "$FAKE_GH_LOG"` before running.

| ID | Cwd | Exact command | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `uv run mattstack fleet issue --help` | exit 0 | output contains `--title`, `--body-file`, `--repos`, `--label`, and `--dry-run` |
| A2 | repo root | `PATH="$T/gh-fake:$PATH" uv run mattstack fleet issue --title x --body-file /nonexistent --repos 'django-*' --dry-run` | exit 2 | stderr or stdout mentions `/nonexistent` |
| A3 | repo root | `PATH="$T/gh-fake:$PATH" uv run mattstack fleet issue --title x --body-file "$T/body.md" --repos 'nope-*' --dry-run` | exit 2 | output contains `nope-*` |
| A4 | repo root | `: > "$FAKE_GH_LOG"; PATH="$T/gh-fake:$PATH" uv run mattstack fleet issue --title "Smoke title" --body-file "$T/body.md" --repos 'django-matt-*' --label fleet --label spec --dry-run` | exit 0 | output has `would-create  mattjaikaran/django-matt-starter` and `would-create  mattjaikaran/django-matt-b2b`; each argv line contains `--label fleet --label spec`; `grep -c 'issue create' "$FAKE_GH_LOG"` prints `0`; `grep -c 'issue list' "$FAKE_GH_LOG"` prints `2` |
| A5 | repo root | `: > "$FAKE_GH_LOG"; FAKE_EXISTING_REPO=mattjaikaran/django-matt-starter FAKE_EXISTING_JSON='[{"title":"Smoke title"}]' PATH="$T/gh-fake:$PATH" uv run mattstack fleet issue --title "Smoke title" --body-file "$T/body.md" --repos 'django-matt-*'` | exit 0 | output has `skipped  mattjaikaran/django-matt-starter` and `created  mattjaikaran/django-matt-b2b  https://github.com/mattjaikaran/django-matt-b2b/issues/1`; `grep -c 'issue create' "$FAKE_GH_LOG"` prints `1`; that line contains `--repo mattjaikaran/django-matt-b2b` |
| A6 | repo root | `: > "$FAKE_GH_LOG"; FAKE_EXISTING_REPO=mattjaikaran/django-matt-starter FAKE_EXISTING_JSON='[{"title":"Smoke title (old)"}]' PATH="$T/gh-fake:$PATH" uv run mattstack fleet issue --title "Smoke title" --body-file "$T/body.md" --repos 'django-matt-starter'` | exit 0 | output has `created  mattjaikaran/django-matt-starter`, not `skipped`, because the titles differ |
| A7 | repo root | `: > "$FAKE_GH_LOG"; FAKE_FAIL_LIST=1 PATH="$T/gh-fake:$PATH" uv run mattstack fleet issue --title "Smoke title" --body-file "$T/body.md" --repos 'django-matt-starter'` | exit 1 | output has `error  mattjaikaran/django-matt-starter`; `grep -c 'issue create' "$FAKE_GH_LOG"` prints `0` (no create after a failed dedupe) |
| A8 | repo root, after F4 | `UV=$(command -v uv); PATH="$T/nogh" "$UV" run mattstack fleet issue --title "Smoke title" --body-file "$T/body.md" --repos 'django-matt-starter'` | exit 1 | output contains `gh CLI not found` |

The gate row is `uv run python scripts/gauntlet.py --gate install`, which runs `_smoke_fleet` with the issue dry-run pass (exit 0, `[PASS] install`).

## Stop conditions and PR evidence

Stop and report if:
- S-CLI-26 is not merged, or `FleetRepo` and `fleet_repos` differ from the signatures described in S-CLI-26.
- `scripts/gauntlet.py` has changed under S-CLI-18 so that `_smoke_fleet` is absent.
- Implementation needs a file outside Files owned. Do not add tests, and do not run real `gh` in acceptance rows.

PR evidence: the dry-run output from A4, the skip and create output from A5, the exit codes from A7 and A8, and the verification results. Do not push to `main`. Conventional Commit subject, for example `feat(fleet): add fleet issue fan-out`.
