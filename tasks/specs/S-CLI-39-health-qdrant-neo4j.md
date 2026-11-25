# S-CLI-39: `mattstack health` checks Qdrant and Neo4j, and respects compose profiles

| Field | Value |
|---|---|
| Spec ID | S-CLI-39 |
| Backlog item | `tasks/todo.md` (AI layer: health reports for the optional vector and graph services) |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | 3458590 |
| Branch | agent/S-CLI-39 |
| Depends on | none |
| Conflicts with | S-CLI-20 (owns `cli_project.py`, which this spec does not touch) |
| Files owned | `src/mattstack/project.py`, `src/mattstack/commands/health.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | S |
| Max files | 4 |
| Max changed lines | 450 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install` (regression only, no edits to it); plus CLI rows A1 to A7 below |
| Acceptance criteria | A1 to A7 (table below) |

## Context and verified citations

Re-verified at `3458590` on 2026-11-25.

- `src/mattstack/templates/compose_env.py:91-116` `ai_services(config)` renders the optional services for development:
  - `qdrant` (rendered when `ai_store == QDRANT`): port `127.0.0.1:${QDRANT_PORT:-6333}:6333`, and `profiles: [ai]`.
  - `neo4j` (rendered when `graph_store == NEO4J`): ports `127.0.0.1:${NEO4J_HTTP_PORT:-7474}:7474` and `127.0.0.1:${NEO4J_BOLT_PORT:-7687}:7687`, and `profiles: [graph]`.
  - Both services are opt-in. A plain `docker compose up` does not start them.
- `src/mattstack/project.py:196-207` `compose_services(root)` returns every service key and ignores `profiles`. This spec adds a separate function and leaves `compose_services` unchanged for its other callers.
- `src/mattstack/project.py:182-193` `project_environment(root)` merges `.env` with `os.environ`, and the process environment wins. `COMPOSE_PROFILES` is read through this function. Docker Compose reads `COMPOSE_PROFILES` from the shell and from `.env`, so the same merge applies.
- `src/mattstack/project.py:335-336` sets the `db` port from `env` with `_port(env.get(...)) or <default>`. The new ports use the same expression.
- `src/mattstack/commands/health.py:27-33` `Check` has `service`, `status`, `detail`, and `ms`. Its `status` comment says `"UP" or "DOWN"`. This spec adds `"SKIP"`.
- `src/mattstack/commands/health.py:180` `healthy = bool(checks) and all(c.status == "UP" for c in checks)`. If SKIP were added without changing this line, a plain `docker compose up` would exit 1. This spec changes it.
- `src/mattstack/commands/health.py:195` colors each row green when `UP` and red otherwise. SKIP needs its own color.
- `src/mattstack/commands/health.py:186-188` JSON payload: `healthy` and `checks`, where each check is `asdict(c)` plus `ms`. So each entry has the keys `service`, `status`, `detail`, and `ms`.
- `src/mattstack/cli_project.py:206-222` registers `health` with `--path/-p`, `--live`, and `--json`. This spec does not change that file.

## Goal and non-goals

Goal:

1. `ResolvedProject` gets `qdrant_port` (default `6333`), `neo4j_http_port` (default `7474`), and `neo4j_bolt_port` (default `7687`), read from `QDRANT_PORT`, `NEO4J_HTTP_PORT`, and `NEO4J_BOLT_PORT` in the project environment.
2. Profile-aware status for each optional service. Let `reachable` be the port check (or, with `--live`, an HTTP 200 on `/`). For a service with compose profiles, `active` means at least one of its profiles is named in `COMPOSE_PROFILES`.
   - `reachable` → `UP`. A running service is UP however it was started, including `docker compose --profile ai up`, even when `COMPOSE_PROFILES` is unset.
   - not `reachable` and the service has no profiles → `DOWN`.
   - not `reachable` and `active` → `DOWN`. The profile is on, so the service should be running.
   - not `reachable` and not `active` → `SKIP`. The service is defined but was not started, and its profile is off.
3. `SKIP` does not make the run unhealthy. `healthy` is true when every check is `UP` or `SKIP`, and at least one check exists.
4. The table colors `SKIP` yellow.

Checks, when the service is defined in compose (`"qdrant" in defined` or `"neo4j" in defined`):

- `Qdrant`: profile `ai`, port `qdrant_port`.
- `Neo4j`: profile `graph`, port `neo4j_http_port`, HTTP probe with `--live`.
- `Neo4j Bolt`: profile `graph`, port `neo4j_bolt_port`, port check only.

Non-goals:
- No change to `cli_project.py` (S-CLI-20 owns it).
- No change to `compose_services` or to `compose_env.py`.
- No check for pgvector or AGE. The pgvector check happens through Postgres. AGE is covered by S-CLI-36.
- No handling of the `*` value in `COMPOSE_PROFILES`. Only the profile names listed explicitly count as active. This spec does not claim how Compose treats `*`.
- Health cannot see a `--profile` flag passed on the command line. So `active` only reflects `COMPOSE_PROFILES`. A service started with `--profile` and reachable is still `UP` by the first rule, so this gap only affects the wording of a SKIP detail.
- No `tests/` file and no pytest (S-CLI-18 forbids both). Verification is the CLI rows below.

## Implementation steps

1. `project.py`:
   - Add `qdrant_port: int`, `neo4j_http_port: int`, and `neo4j_bolt_port: int` to `ResolvedProject`, after the existing port fields. Read them from `project_environment(root)` with the `_port(...) or <default>` pattern.
   - Add `compose_service_profiles(root: Path) -> dict[str, frozenset[str]]`. It parses the same root compose file as `compose_services`, using the same `COMPOSE_FILENAMES` loop and the same YAML error handling. For each service it returns the `profiles` list as a frozenset, empty when the key is absent. An unreadable or invalid file returns `{}`.
   - Add `active_compose_profiles(env: Mapping[str, str]) -> frozenset[str]`. It splits `env.get("COMPOSE_PROFILES", "")` on commas, strips whitespace, and drops empty entries.
2. `commands/health.py`:
   - Update the `Check.status` comment to `"UP", "DOWN", or "SKIP"`.
   - Change line 180 to `healthy = bool(checks) and all(c.status in ("UP", "SKIP") for c in checks)`.
   - In the table, color `SKIP` yellow and leave `UP`/`DOWN` as they are.
   - In `collect_health`, after the Redis block, compute `profiles = compose_service_profiles(project.root)` and `active = active_compose_profiles(project_environment(project.root))`, then add the three checks above. Each check follows the rule in Goal item 2.
   - SKIP detail text: `not started; profile <name> is off (start with COMPOSE_PROFILES=<name> or docker compose --profile <name> up)`.
   - DOWN detail text reuses the detail strings of the existing port and HTTP helpers (health.py:34-77), with `not running` appended when the profile is active.
   - Keep the existing port and HTTP helpers (health.py:34-77) unchanged.

## Machine-checkable acceptance

Fixture for each row: a project directory under `$TMP` with a `docker-compose.yml` that defines `qdrant:` (with `profiles: [ai]`) and `neo4j:` (with `profiles: [graph]`), using the same images and ports as `ai_services`. Add `.env` as noted in each row. The executor first confirms the minimum fixture that `ResolvedProject` loads. If it needs more than `docker-compose.yml`, `.env`, and any file the loader requires, record the extra files in the PR body.

Every row runs with `env -u COMPOSE_PROFILES` unless the row sets `COMPOSE_PROFILES` in `.env`. A stray shell value would otherwise change the result.

Listeners: `python3 -m http.server <port> --bind 127.0.0.1 -d "$TMP"`, started in the background and killed after each row.

Assertions use `jq` on the `--json` output. Each check has `service`, `status`, `detail`, and `ms`. The overall `healthy` value and the exit code also depend on the host's Docker section, so rows assert on the named checks and on `healthy` only where the row says so.

| ID | Cwd | Exact command or journey step | Expected | Exact assertion |
|---|---|---|---|---|
| A1 | `$REPO` | Default ports, no profile env. Listeners on `6333`, `7474`, `7687`. `env -u COMPOSE_PROFILES uv run mattstack health --json --path "$TMP"` | the three checks `UP` | `jq -r '.checks[] \| select(.service \| test("^(Qdrant\|Neo4j\|Neo4j Bolt)$")) \| "\(.service)=\(.status)"'` prints `Qdrant=UP`, `Neo4j=UP`, `Neo4j Bolt=UP`. This covers a profiled service that is running but was started outside `COMPOSE_PROFILES`. |
| A2 | `$REPO` | Custom ports: `.env` sets `QDRANT_PORT=16333`, `NEO4J_HTTP_PORT=17474`, `NEO4J_BOLT_PORT=17687`. Listeners on those ports. Same command as A1. | the three checks `UP` | same `jq` as A1 prints three `=UP` lines |
| A3 | `$REPO` | Plain `docker compose up`: no listeners, no `COMPOSE_PROFILES`. Same command as A1. | `Qdrant`, `Neo4j`, `Neo4j Bolt` each `SKIP` | the `jq` from A1 prints `Qdrant=SKIP`, `Neo4j=SKIP`, `Neo4j Bolt=SKIP`; the detail of `Qdrant` contains `COMPOSE_PROFILES=ai`; `jq '[.checks[] \| select(.status == "DOWN" and (.service \| test("Qdrant\|Neo4j")))] \| length'` prints `0` |
| A4 | `$REPO` | Profile on: `.env` sets `COMPOSE_PROFILES=ai`. No listeners. Same command as A1. | `Qdrant` `DOWN`; `Neo4j` `SKIP` | `Qdrant=DOWN` with detail `Nothing listening on port 6333`; `Neo4j=SKIP`; `jq '.healthy'` prints `false` (the `Qdrant` DOWN makes the run unhealthy) |
| A5 | `$REPO` | Profile on and running: `.env` sets `COMPOSE_PROFILES=ai,graph`. Listeners on `6333`, `7474`, `7687`. Same command as A1. | three checks `UP` | same `jq` as A1 prints three `=UP` lines |
| A6 | `$REPO` | Fixture where `docker-compose.yml` defines no `qdrant` and no `neo4j` service. Same command as A1. | no optional-service checks | `jq '[.checks[] \| select(.service \| test("Qdrant\|Neo4j"))] \| length'` prints `0` |
| A7 | `$REPO` | A1 setup with `--live`: `env -u COMPOSE_PROFILES uv run mattstack health --json --live --path "$TMP"`. The `http.server` listeners return 200 for `/`. | `Qdrant` and `Neo4j` `UP` | `jq` prints `Qdrant=UP` and `Neo4j=UP` |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a new dependency, a default port that doesn't match `ai_services`, or a check that fails outside your change. Commit nothing when stopped; report the exact discrepancy.

PR body: spec ID, base `3458590` and head SHA, owned files with changed-line counts, the `jq` output of rows A1 to A7, the fixture files used, and the output of each verification command. Commit subject: `feat(health): Check Qdrant and Neo4j with compose profile awareness`. Stage only the Files owned, with explicit paths. Never stage the untracked `tasks/fleet/`, `tasks/specs/S-CLI-26-*`, `tasks/specs/S-CLI-27-*`, `docs/agent-layout.md`, or `docs/plans/` files from other agents.
