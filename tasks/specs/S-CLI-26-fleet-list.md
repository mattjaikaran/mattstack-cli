# S-CLI-26: `fleet list` shows each boilerplate's local state against origin/main

| Field | Value |
|---|---|
| Spec ID | S-CLI-26 |
| Backlog item | GitHub issue #135; `docs/plans/2026-11-25-roadmap.md:66-76` (fleet command, theme 2). That file is an untracked draft at e89fac4; commit it before claiming. |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | e89fac4 (branch `main`) |
| Branch | agent/S-CLI-26 |
| Depends on | none |
| Conflicts with | S-CLI-11 (`src/mattstack/cli.py`), S-CLI-13 (`src/mattstack/cli.py`), S-CLI-18 (`scripts/gauntlet.py`), S-CLI-23 (`scripts/gauntlet.py`); S-CLI-20 (`docs/commands.md`); S-CLI-24 (`src/mattstack/cli.py`); S-CLI-25 (`docs/commands.md`); S-CLI-27 (`docs/commands.md`, `scripts/gauntlet.py`, `src/mattstack/commands/fleet.py`); S-CLI-28 (`docs/commands.md`, `scripts/gauntlet.py`, `src/mattstack/commands/fleet.py`); S-CLI-40 (`scripts/gauntlet.py`); S-CLI-41 (`scripts/gauntlet.py`); S-CLI-43 (`src/mattstack/cli.py`) |
| Files owned | `src/mattstack/fleet/__init__.py` (new), `src/mattstack/fleet/registry.py` (new), `src/mattstack/fleet/status.py` (new), `src/mattstack/commands/fleet.py` (new), `src/mattstack/cli.py`, `scripts/check_architecture.py`, `scripts/gauntlet.py`, `docs/commands.md` (new `## Fleet` section only) |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 8 |
| Max changed lines | 500 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install`; plus the CLI rows in the acceptance table below |
| Acceptance criteria | A1 to A10 in "Machine-checkable acceptance" |

## Context and verified citations

Verified against base commit e89fac4 on 2026-11-25.

- **Agent-run rules.** `~/dev/agent-run-edit/repos/mattstack-cli.yml:93` says "Do not run pytest. Do not add or change unit tests (tests/)". Line 138 says "The factory runs no unit tests". This spec adds no tests. Proof comes from the CLI rows below and the install gate.
- **Repo registry source.** `src/mattstack/config.py:99-114` defines `REPO_URLS: dict[str, str]` with 10 keys (`django-ninja` through `swift-ios`). `config.py:117-119` defines `source_env_var(key)`, which returns `MATTSTACK_SOURCE_<KEY>`. `config.py:122-136` defines `get_repo_urls()`, which copies `REPO_URLS`, merges `get_user_repos()` (`src/mattstack/user_config.py:49-53`), and applies env overrides.
- **Consumers of `get_repo_urls()` and `REPO_URLS`.** `commands/info.py:38` (lists every repo), `commands/add.py:101`, `generators/base.py:72`, `generators/ios.py:82`, `commands/upgrade.py:195`. Presets do not reference either name (grep over `src/`, `tests/`, `scripts/`). Adding B2B repos to `REPO_URLS` would make them scaffold sources and show them in `info`. The fleet registry therefore lives in its own module.
- **The six B2B repos not in `REPO_URLS`.** `docs/plans/2026-11-25-roadmap.md:36-53` lists 16 repos. The six extras are `django-api-b2b` (line 42), `django-api-starter` (41), `django-matt-b2b` (40), `fullstack-b2b` (52), `nextjs-b2b-boilerplate` (51), and `react-vite-b2b` (47).
- **Local clones.** All 16 repo names exist as directories under `~/dev/boilerplates/` (observed 2026-11-25). The same directory holds `django-ninja-boilerplate-worktrees`, which the registry must not match.
- **Typer lazy groups.** `src/mattstack/cli.py:21-26` defines `LazyGroupSpec(module, attr, short_help)`. `cli.py:29-60` defines `LAZY_GROUPS`; its last entry is `rules`, at line 59. `cli.py:63-106` defines `LazyTyperGroup`, with `list_commands` at 72 and `get_command` at 75. A new group is one `LAZY_GROUPS` entry plus a module exposing a Typer app.
- **Typer app pattern.** `src/mattstack/commands/board.py:16-19` defines `board_app = typer.Typer(name=..., help=..., no_args_is_help=True)`. Line 37 is `@board_app.command("create")`.
- **Table helper.** `src/mattstack/utils/console.py:91` defines `create_table(title, columns)`. `commands/info.py:9` imports it with `console`.
- **Subprocess pattern.** `src/mattstack/utils/git.py:26-27` defines `git_available()`. `utils/git.py:30` defines `clone_repo`, which calls `subprocess.run` with an argv list and no shell, with a `# nosec B603` comment. Errors go through `print_error` (`utils/console.py:63`).
- **Architecture check.** `scripts/check_architecture.py:24-31` defines `CORE_LAYER`. `:32-40` defines `TOP_LEVEL_CORE`, which does not contain `fleet`. `:55-64` `_module_path` maps `fleet/registry.py` to `fleet.registry`, so the top-level name is `fleet`. Adding `"fleet"` to `TOP_LEVEL_CORE` puts the whole package under the core-layer rules.
- **File length.** `scripts/check_file_length.py:13` sets `SRC_DIR = PROJECT_ROOT / "src"`. Line 15 sets `MAX_LINES = 400`.
- **Install gate.** `scripts/gauntlet.py:253` defines `_check_agent_docs`. `:290` defines `_gate_install`. `:292` calls `_check_agent_docs`. `:343` is `return _smoke_python_pin(venv / "bin" / "python", work, timeout)`, the hook point for a fleet smoke. `:360` registers the gate. `:56` defines `_run(cmd, cwd=None, timeout=120) -> tuple[int, str]`, which has no `env` parameter. `scripts/gauntlet.py --gate install` passed on e89fac4 (`[PASS] install`).
- **Docs.** `docs/commands.md:763` is `## Project information and utilities`. `:827-834` is the `board` and `todo` section. `:836` is `## Config file format`. The new `## Fleet` section goes between line 834 and line 836. `tasks/specs/S-CLI-20-github-workflow-triggers-runner.md:14` owns only the `mattstack workflow` subsection of `docs/commands.md`, so there is no overlap.
- **Spot-checked repo state.** Local `origin/main` refs in five clones show the roadmap table is accurate: `django-ninja-boilerplate` has AGENTS.md and 7 skill files, `django-matt-starter` tracks `.claude/`, `nextjs-starter` has AGENTS.md only, `swift-ios-starter` tracks `.claude/` and has no AGENTS.md, and `react-vite-b2b` tracks `.claude/`.

## Goal and non-goals

Goal: `mattstack fleet list` prints one row per fleet repo with local presence, current branch, commits behind and ahead of `origin/main`, and dirty-file count. `--fetch` runs `git fetch --prune origin` in each present clone first. `--json` emits the same rows as a JSON array. The command runs only local git commands, apart from the optional fetch.

Non-goals:
- No change to `REPO_URLS`, `get_repo_urls()`, `info`, presets, or scaffold sources.
- User-config repos are not part of the fleet.
- No conformance checks (S-CLI-27) and no issue creation (S-CLI-28).
- No pull, checkout, reset, or clone of any repo.
- No `tests/` changes and no new dependency.

## Implementation steps

1. **Create `src/mattstack/fleet/__init__.py`.** Module docstring only: "Boilerplate fleet: registry, status, conformance, and issue fan-out." Layer rule: nothing under `src/mattstack/fleet/` imports `mattstack.commands` or `mattstack.cli*`; `commands/fleet.py` is the only importer of the package.

2. **Create `src/mattstack/fleet/registry.py`.**
   - `FLEET_EXTRA_REPOS: dict[str, str]` with six entries keyed by repo name, each URL `https://github.com/mattjaikaran/<name>.git`: `django-api-b2b`, `django-api-starter`, `django-matt-b2b`, `fullstack-b2b`, `nextjs-b2b-boilerplate`, `react-vite-b2b`.
   - `@dataclass(frozen=True) class FleetRepo` with fields `key: str` and `url: str`. Properties: `name` is the last URL path segment without `.git`. `slug` is `owner/name` from the URL path.
   - `fleet_repos() -> tuple[FleetRepo, ...]` returns `REPO_URLS` entries in order, then `FLEET_EXTRA_REPOS` entries. It reads `mattstack.config.REPO_URLS` directly and never calls `get_repo_urls()`. It raises `ValueError` on duplicate `name`.
   - `clone_path(repo: FleetRepo, root: Path) -> Path`: if `os.environ.get(source_env_var(repo.key), "").strip()` names an existing directory, return that directory. Otherwise return `root / repo.name`. For extras, `key` equals the repo name.

3. **Create `src/mattstack/fleet/status.py`.**
   - `@dataclass(frozen=True) class GitResult` with `returncode: int`, `stdout: str`, `stderr: str`.
   - `run_git(cwd: Path, *args: str, timeout: int = 30) -> GitResult`. It calls `subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})` with a `# nosec B603` comment. It catches `OSError` and `subprocess.TimeoutExpired`, returning `returncode=-1` with the message in `stderr`.
   - `@dataclass(frozen=True) class RepoStatus` with `key, name, slug, path, present, branch, behind, ahead, dirty, note`. Counts and branch are `None` when unknown.
   - `collect_status(repo: FleetRepo, root: Path, *, fetch: bool) -> RepoStatus`:
     - `present = (path / ".git").exists()`. If absent, set `note = f"no clone at {path}"` and return.
     - If `fetch`, run `git fetch --prune origin`. On failure, set `note` to `fetch failed: <first stderr line>` and continue with local refs.
     - `branch`: `git rev-parse --abbrev-ref HEAD`.
     - If `git rev-parse --verify -q origin/main` fails, set `note = "no origin/main; run with --fetch"`. Otherwise run `git rev-list --left-right --count origin/main...HEAD`. The left count is `behind` and the right count is `ahead`.
     - `dirty`: number of non-empty lines in `git status --porcelain`.

4. **Create `src/mattstack/commands/fleet.py`.**
   - `fleet_app = typer.Typer(name="fleet", help="Inspect and delegate work across the boilerplate repos.", no_args_is_help=True)`.
   - `@fleet_app.command("list")` with options `--root PATH` (default `~/dev/boilerplates`, resolved with `Path.home()` at runtime), `--fetch`, and `--json`.
   - Table via `create_table("Fleet", ["Repo", "Local", "Branch", "Behind", "Ahead", "Dirty", "Note"])`. Unknown values render as `n/a`.
   - `--json` prints `json.dumps([...], indent=2)` with plain `print`, not Rich. Each object has keys `key, name, slug, path, present, branch, behind, ahead, dirty, note`.
   - Exit 0 whatever the repo states. Notes carry problems, and invalid options exit 2 through Typer.

5. **Edit `src/mattstack/cli.py`.** Add an entry to `LAZY_GROUPS` after `rules` (line 59): `"fleet": LazyGroupSpec("mattstack.commands.fleet", "fleet_app", "Compare and delegate work across the boilerplate repos.")`.

6. **Edit `scripts/check_architecture.py`.** Add `"fleet",` to `TOP_LEVEL_CORE` (lines 32-40).

7. **Edit `scripts/gauntlet.py`.** Add `_smoke_fleet(executable: Path, work: Path, timeout: int) -> bool`. It creates a bare origin and a clone under `work / "fleet"`, one repo named `django-ninja-boilerplate` that has an `AGENTS.md` committed to `main`. It runs `<executable> fleet list --root <work>/fleet/root --json` and asserts exit 0, 16 rows, and `present` true for `django-ninja-boilerplate`. Git commands in the fixture set `GIT_CONFIG_GLOBAL=/dev/null` and `GIT_CONFIG_COUNT=0` through the environment. `_run` has no `env` parameter, so pass the variables by prefixing the command with `env`. Call `_smoke_fleet` from `_gate_install` before line 343's `return _smoke_python_pin(...)`:
   ```python
   if not _smoke_fleet(executable, work, timeout):
       return False
   ```
   The variable name for the executable must match the one already used in `_gate_install`.

8. **Edit `docs/commands.md`.** Insert a `## Fleet` section between line 834 and `## Config file format` at line 836. It should cover `fleet list`, the registry and its exclusion of user-config repos, `--root`, the `MATTSTACK_SOURCE_<KEY>` precedence, `--fetch`, and `--json`.

## Machine-checkable acceptance

Fixture recipe F1 (run once per shell, then use `$T`):

```bash
T=$(mktemp -d); export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0
G="git -c user.name=t -c user.email=t@t"
mkdir -p "$T/seed/django-ninja-boilerplate" "$T/root"
git -C "$T/seed/django-ninja-boilerplate" init -q -b main
printf '# Agents\n' > "$T/seed/django-ninja-boilerplate/AGENTS.md"
$G -C "$T/seed/django-ninja-boilerplate" add AGENTS.md && $G -C "$T/seed/django-ninja-boilerplate" commit -qm init
git clone -q --bare "$T/seed/django-ninja-boilerplate" "$T/origin.git"
git clone -q "$T/origin.git" "$T/root/django-ninja-boilerplate"
```

The 16 expected names, in registry order, are: `django-ninja-boilerplate, django-matt-starter, fastapi-boilerplate, nestjs-boilerplate, react-vite-boilerplate, react-vite-starter, react-rsbuild-boilerplate, react-rsbuild-kibo-boilerplate, nextjs-starter, swift-ios-starter, django-api-b2b, django-api-starter, django-matt-b2b, fullstack-b2b, nextjs-b2b-boilerplate, react-vite-b2b`.

| ID | Cwd | Exact command | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `uv run mattstack fleet --help` | exit 0 | output contains `list` |
| A2 | repo root, after F1 | `uv run mattstack fleet list --root "$T/root" --json > "$T/a2.json"` | exit 0 | `python -c "import json; r=json.load(open('$T/a2.json')); assert [x['name'] for x in r]==EXPECTED16; d=r[0]; assert (d['present'],d['branch'],d['behind'],d['ahead'],d['dirty'])==(True,'main',0,0,0); n=[x for x in r if x['name']=='nextjs-starter'][0]; assert n['present'] is False and n['branch'] is None"` |
| A3 | repo root, after F1 | `$G -C "$T/root/django-ninja-boilerplate" commit -q --allow-empty -m local && uv run mattstack fleet list --root "$T/root" --json` | exit 0 | the django-ninja row has `ahead == 1`, `behind == 0` |
| A4 | repo root, after F1 | `$G -C "$T/seed/django-ninja-boilerplate" commit -q --allow-empty -m up && $G -C "$T/seed/django-ninja-boilerplate" push -q "$T/origin.git" main && uv run mattstack fleet list --root "$T/root" --json` | exit 0 | django-ninja row has `behind == 0`, because no fetch ran |
| A5 | repo root, after A4 | `uv run mattstack fleet list --root "$T/root" --fetch --json` | exit 0 | django-ninja row has `behind == 1` |
| A6 | repo root, after F1 | `echo x > "$T/root/django-ninja-boilerplate/dirty.txt" && uv run mattstack fleet list --root "$T/root" --json` | exit 0 | django-ninja row has `dirty == 1` |
| A7 | repo root, after F1 | `git -C "$T/root/django-ninja-boilerplate" remote set-url origin /nonexistent && uv run mattstack fleet list --root "$T/root" --fetch --json` | exit 0 | django-ninja row `note` starts with `fetch failed:`; other fields still present |
| A8 | repo root, after F1 | `HOME="$T/home" uv run mattstack fleet list --json` | exit 0 | every row has `present == false`; output is valid JSON with 16 rows |
| A9 | repo root | `uv run python -c "from mattstack.fleet.registry import fleet_repos; from mattstack.config import REPO_URLS; print(len(fleet_repos()), len(REPO_URLS))"` | exit 0 | output `16 10` |
| A10 | repo root, after F1 | `uv run mattstack info > "$T/info.txt"; grep -c django-api-b2b "$T/info.txt"; MATTSTACK_SOURCE_NEXTJS="$T" uv run mattstack fleet list --root "$T/root" --json` | `grep` count `0`; exit 0 | `info` does not list extras; the `nextjs` row has `path == "$T"` (env override, existing dir) |

The gate row is `uv run python scripts/gauntlet.py --gate install`, which runs `_smoke_fleet` (exit 0, `[PASS] install`).

Manual smoke, not part of the gate: on a machine where `~/dev/boilerplates/` holds the 16 clones, `uv run mattstack fleet list --json` should report `present` true for all 16 rows.

## Stop conditions and PR evidence

Stop and report, without editing outside Files owned, if:
- `config.py` `REPO_URLS` or `source_env_var` no longer matches the cited lines, or the `cli.py` `LAZY_GROUPS` shape differs.
- `"fleet"` already appears in `TOP_LEVEL_CORE` or `src/mattstack/fleet/` already exists.
- `scripts/gauntlet.py` `_gate_install` no longer ends at the cited `_smoke_python_pin` call, or S-CLI-18 has already changed `_gate_install`.
- A required change would touch `tests/`. Stop; do not add tests.

PR evidence: the output of `uv run mattstack fleet --help`; the JSON from A2 and A5; the `fleet list` table output from one fixture run; the verification command results. Do not push to `main`. Use a Conventional Commit subject, for example `feat(fleet): add fleet list`.
