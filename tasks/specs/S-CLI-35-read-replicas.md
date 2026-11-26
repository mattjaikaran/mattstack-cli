# S-CLI-35: `mattstack add read-replica` (Compose streaming replica, opt-in)

| Field | Value |
|---|---|
| Spec ID | S-CLI-35 |
| Backlog item | GitHub issue #144; `docs/plans/2026-11-25-roadmap.md` section 4 (:90-99); django-ninja router issue https://github.com/mattjaikaran/django-ninja-boilerplate/issues/96 |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-35 |
| Depends on | none |
| Conflicts with | S-CLI-34 (`src/mattstack/config.py`, `src/mattstack/commands/add.py`, `src/mattstack/runtime_profiles.py`, `src/mattstack/templates/docker_compose.py`, `src/mattstack/templates/compose_env.py`); S-CLI-36 (`src/mattstack/config.py`, `src/mattstack/commands/add.py`, `src/mattstack/templates/compose_env.py`, `src/mattstack/templates/root_env.py`) |
| Files owned | `src/mattstack/commands/add_read_replica.py` (new), `src/mattstack/commands/add.py`, `src/mattstack/config.py`, `src/mattstack/runtime_profiles.py`, `src/mattstack/templates/read_replica_service.py` (new), `src/mattstack/templates/docker_compose.py`, `src/mattstack/templates/compose_env.py`, `src/mattstack/templates/root_env.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 8 |
| Max changed lines | 400 |
| Verification commands | `uv run ruff format --check src/`; `uv run ruff check src/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install` |
| Acceptance criteria | A1-A12 (table below) |

## Context and verified citations

Citations were read at base commit `e89fac4`. `src/` has not changed since then. `scripts/` changed on main (`gauntlet.py`, `check_agent_docs.py`), but the cited lines did not move: checked again at `9443a9c` (2026-11-25). Items marked (unverified) are not confirmed against a source yet.

**Django side (boilerplate, origin/main):**
- `ROADMAP.md:185`: `| 4.24 | **Multi-Database Configuration** | P1 | Django multi-DB config for read replicas, analytics DB, external sources. Router class for read/write splitting. |`. Status is planned. The router itself is tracked in https://github.com/mattjaikaran/django-ninja-boilerplate/issues/96.
- `api/settings/common.py:242` `DATABASES = {`, `:250` `"CONN_MAX_AGE": 0`. No `DATABASE_ROUTERS` and no `replica` alias exist yet.
- The router expects a `DATABASE_REPLICA_URL` env var. When it is unset, the `replica` alias is the primary. Compose never sets `DATABASE_REPLICA_URL`: the `.env.example` line stays commented, so a plain `docker compose up` cannot point the backend at a missing `db-replica` host. This CLI spec emits that env var; it does not add the router.

**mattstack side (base commit `e89fac4`):**
- `src/mattstack/config.py:167` `use_realtime: bool`, `:172` `use_redis: bool = True`. There is no replica flag yet. Add `use_read_replica: bool = False` next to `use_redis`.
- `src/mattstack/commands/add.py:41` `VALID_COMPONENTS = ("frontend", "backend", "ios")`. `:159` `_update_root_files(config, *, dry_run, force)`. `:262` `run_add(component, project_path, framework, dry_run, force)`. `:270` component check (`Invalid component`). The dispatch branch for `read-replica` goes before `:270`. Read `add.py:159-197` (rerun contract) and `add.py:262-323` before editing.
- `src/mattstack/templates/docker_compose.py:29` `generate_docker_compose`; `:35-37` the backend block appends `db_service`.
- `src/mattstack/templates/compose_env.py:125` `db_credentials`; `:139` `db_service`. The service body (about lines 147-160) uses the image from `service_image(config, "postgres")`, and in dev publishes `127.0.0.1:${DB_PORT:-5432}:5432`.
- `src/mattstack/templates/root_env.py:46` `generate_env_example` renders `.env.example`; `_root_files` (`add.py:138`) builds it from there. `root_env.py` is 399 lines. Step 4 adds one call line, so it reaches 400, the cap. `scripts/check_file_length.py:15` `MAX_LINES = 400`. Current counts: `config.py` 375, `add.py` 323, `compose_env.py` 341, `docker_compose.py` 169, `runtime_profiles.py` 317. S-CLI-34 also adds to `config.py`, `add.py`, `docker_compose.py`, `compose_env.py`, and `runtime_profiles.py`. S-CLI-36 adds to `config.py`, `add.py`, `compose_env.py`, and `root_env.py`. The cap is a real limit.
- `src/mattstack/project.py:248` `resolve_project` is available if the command needs the component dirs.

**Persistence and read-back (checked at `9443a9c`; `src/` unchanged since `e89fac4`):**
- `src/mattstack/project.py:343` `save_project_config` starts from the existing `backend` section (`:367`), so it keeps every key already in `mattstack.yml`. It overwrites `framework`, `dir`, `redis`, and `api_prefix` (`:368-375`), then calls `apply_runtime_metadata` (`:376`). A key that `runtime_kwargs` does not read back therefore stays in the file.
- `src/mattstack/runtime_profiles.py:257-264` `apply_runtime_metadata` writes `realtime` (`:261`), `ai` (`:263`), and `graph` (`:264`). `runtime_kwargs` (`:207`) reads them back with `backend_meta.get` (`realtime` at `:235-237`) and returns `use_realtime` (`:242`). `resolve_project` (`project.py:248`) spreads the result at `:321`.
- `src/mattstack/utils/yaml_config.py` is the `init --config` loader. It is not on the `add` round trip, so this spec does not change it.
- `src/mattstack/commands/add.py:198-206` `_save_metadata` calls `save_project_config(config)` on every `add`. A key that `runtime_kwargs` does not read back stays in `mattstack.yml`, but the next `add` loads the default `False`, so the regenerated compose drops `db-replica`.

**External (unverified; the executor confirms these against the pinned Postgres image during A8):**
- `pg_basebackup -R` writes `primary_conninfo` for a standby. https://www.postgresql.org/docs/current/app-pgbasebackup.html (unverified)
- Streaming replication setup. https://www.postgresql.org/docs/current/warm-standby.html (unverified)
- `pg_hba.conf` replication entry. https://www.postgresql.org/docs/current/auth-pg-hba-conf.html (unverified)
- Official image init scripts run before the final server start, so an appended `pg_hba.conf` line takes effect. https://github.com/docker-library/docs/tree/master/postgres (unverified)
- Compose profiles and `docker compose --profile`. https://docs.docker.com/compose/how-tos/profiles/ (unverified)
- `pg_isready`, `gosu`, and `PGPASSWORD` are present in the pinned image (unverified).

## Goal and non-goals

**Goal.** `mattstack add read-replica` makes the project's Postgres replicable:
1. Sets `use_read_replica = True` and writes `read_replica: true` to `mattstack.yml` (steps 3 and 8).
2. Adds the `db-replica` service, which is a streaming replica of the project's Postgres image. It is in the `replica` Compose profile, so it does not start by default.
3. Adds a replication role and a `pg_hba.conf` line to the primary through a docker-entrypoint-initdb.d script.
4. Renders a commented `DATABASE_REPLICA_URL` line into `.env.example` through `root_env.py` (step 4), only when the flag is set.
5. Prints next steps, including the manual step for existing volumes.

**Non-goals.**
- The router, settings, and `read_replica()` helper (django-ninja issue #96).
- Failover or promotion.
- Production Compose. Only the dev `db` service gets the replication setup. The `production=True` branch of `db_service` must not change.
- Making the replica default-on.
- Editing `.env`. It is a user file. `add read-replica` does not regenerate it, because `_root_files` (`add.py:146-152`) lists `.env.example`, not `.env`.
- Changing `utils/yaml_config.py` or `project.py`. Neither is on the `add` round trip (see Context). `init --config` files do not gain the flag.
- Any `tests/` file. Acceptance is the shell rows below.
- Kubernetes or Helm.

## Implementation steps

1. **Gate (no edits).** Do not start steps 2-9 until both checks pass:
   - `gh issue view 96 -R mattjaikaran/django-ninja-boilerplate --json state --jq .state` prints `CLOSED`.
   - `gh api "repos/mattjaikaran/django-ninja-boilerplate/contents/core/db_routing.py?ref=main" --jq .path` prints `core/db_routing.py`. Issue #96's body names this file as the router.
   If either check fails, stop and report (see Stop conditions).
2. **`src/mattstack/config.py`.** Add `use_read_replica: bool = False` next to `use_redis` (`:172`). The default keeps existing output unchanged (A6).
3. **`src/mattstack/runtime_profiles.py` (persist and read back).**
   - In `apply_runtime_metadata` (`:257-264`), write `backend_meta["read_replica"] = True` beside `realtime` (`:261`) when `config.use_read_replica`. Otherwise `backend_meta.pop("read_replica", None)`. Do not write a `false` key, so existing `mattstack.yml` files do not change (same pattern as S-CLI-34, `tasks/specs/S-CLI-34-add-pgbouncer.md:87`).
   - In `runtime_kwargs` (`:207`), read `read_replica = backend_meta.get("read_replica", False)`. Reject a non-bool with the `realtime` pattern (`:235-237`). Return `"use_read_replica": read_replica` beside `use_realtime` (`:242`).
   - Both halves are needed. `_save_metadata` (`add.py:198-206`) saves the config on every `add`, so a key that is not read back resets to `false`.
4. **`src/mattstack/templates/root_env.py` (render `.env.example`).** Do not append to `.env.example`. Render it instead.
   - Extend the existing import on `:24` to `from mattstack.templates.compose_env import pgvector_image, replica_env_lines`. This adds no line.
   - In `generate_env_example` (`:46`), inside `if config.has_backend:`, add one line, `lines.extend(replica_env_lines(config))`, after `_ai_lines` (`:147`) and before `lines.append("")` (`:148`).
   - `root_env.py` goes from 399 to 400 lines, which is the cap. A second added line breaks `check_file_length.py`.
   - `replica_env_lines` returns `[]` unless `config.use_read_replica`. The default `.env.example` does not change (A6), and a rerun with the flag set renders the same bytes. `_update_root_files` (`add.py:159`) therefore writes no `.env.example.mattstack-new` (A5).
5. **`src/mattstack/templates/read_replica_service.py` (new).** Pure functions returning strings:
   - `replica_service(config) -> str` returns the YAML block for `db-replica` (two-space indent under `services:`):
     - `image:` the same postgres image as `db`, via `service_image(config, "postgres")`.
     - `profiles: ["replica"]`.
     - `depends_on: db: condition: service_healthy`.
     - `entrypoint: ["/bin/sh", "/replica/entrypoint.sh"]`.
     - `environment:` `REPLICATION_USER: "replicator"` and `REPLICATION_PASSWORD: "${REPLICATION_PASSWORD:-replicator}"`.
     - `volumes:` `postgres_replica_data:/var/lib/postgresql/data` and `./docker/postgres/replica:/replica:ro`.
     - `ports:` `"127.0.0.1:${DB_REPLICA_PORT:-5433}:5432"`.
     - `healthcheck:` `pg_isready`. Write `$$` for Compose variables inside the healthcheck (Compose escaping).
   - `primary_init_script() -> str` returns a `/bin/sh` script with `set -eu`. It runs `psql -v ON_ERROR_STOP=1` to `CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD '$REPLICATION_PASSWORD'`, then appends `host replication replicator all scram-sha-256` to `$PGDATA/pg_hba.conf`.
   - `replica_entrypoint() -> str` returns a `/bin/sh` script with `set -eu`. It exports `PGPASSWORD="$REPLICATION_PASSWORD"`. If `$PGDATA/PG_VERSION` is missing, it waits for `pg_isready -h db`, then runs `gosu postgres` `pg_basebackup -h db -U replicator -D "$PGDATA" -X stream -R`, after clearing `$PGDATA`. Finally it runs `exec docker-entrypoint.sh postgres`.
6. **`src/mattstack/templates/docker_compose.py`.** In the backend block after `db_service` (`:35-37`), when `config.use_read_replica` is true, append `replica_service(config)` to the services and `  postgres_replica_data:` to the top-level volumes.
7. **`src/mattstack/templates/compose_env.py`.** In `db_service` (`:139`), only when `not production and config.use_read_replica`:
   - add `REPLICATION_PASSWORD: "${REPLICATION_PASSWORD:-replicator}"` to the environment;
   - add the volume `./docker/postgres/replica/primary-init.sh:/docker-entrypoint-initdb.d/10-replication.sh:ro`.
   Also define `replica_env_lines(config) -> list[str]` here, not in `read_replica_service.py`. It returns `[]` unless `config.use_read_replica`. Otherwise it returns a note that the replica is opt-in with `--profile replica`, then an uncommented `DB_REPLICA_PORT=5433` (the Compose port mapping `${DB_REPLICA_PORT:-5433}` reads it too, as `DB_PORT` works for the primary at `root_env.py:59`), then the commented `# DATABASE_REPLICA_URL=postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${DB_REPLICA_PORT}/${POSTGRES_DB}`. The URL uses the same `${POSTGRES_*}` references as `DATABASE_URL` (`root_env.py:35-37`, `:68`, `:97`), so no password is hard-coded. Write those three references as string literals in `compose_env.py`. Do not import `_USER`, `_PASSWORD` or `_DB` from `root_env.py`: `root_env.py:24` already imports from `compose_env.py`, so that import would be a cycle. The replica is a physical copy of the primary, so the primary's `postgres` role and its random `POSTGRES_PASSWORD` (`root_env.py:366`, `${DB_PASSWORD}`) authenticate on it. It lives here so that step 4 adds no second import line to `root_env.py`.
8. **`src/mattstack/commands/add_read_replica.py` (new).** `run_add_read_replica(project_path: Path, *, dry_run: bool, force: bool) -> None`:
   - load the project config the same way `run_add` does (`add.py:262`); exit 1 if there is no backend;
   - set `use_read_replica = True` and save with `save_project_config`. Step 3 writes the key, and A10 checks it;
   - write `docker/postgres/replica/entrypoint.sh` and `docker/postgres/replica/primary-init.sh` using the rerun contract from `add.py:159-197` (`<name>.mattstack-new` when content differs, `--force` overwrites, `dry_run` writes nothing);
   - regenerate `docker-compose.yml` and `.env.example` through `_update_root_files` with the same flags. Step 4 renders `.env.example`, so this step does not append to it. `--force` overwrites `.env.example` like every other root file. Import `_update_root_files` inside the function to avoid an import cycle with `add.py`;
   - print next steps: `docker compose --profile replica up -d db-replica`, then copy both `DB_REPLICA_PORT=5433` and the `DATABASE_REPLICA_URL` line from `.env.example` into `.env` and uncomment the URL. The command never edits `.env` (a non-goal), so an existing `.env` lacks `DB_REPLICA_PORT`, and without it the URL has no port and libpq would connect to the primary on 5432. Also print the note that an existing `postgres_data` volume skips the init script, so the role and the `pg_hba.conf` line must be added by hand, with the two commands printed.
9. **`src/mattstack/commands/add.py`.** In `run_add` (`:262`), before the component check (`:270`), dispatch `component == "read-replica"` to `run_add_read_replica`, imported inside the branch. Do not change `VALID_COMPONENTS`. Keep the branch short.

## Machine-checkable acceptance

Each row runs from the repo root. `$TMP` is a temp dir created by row A1.

| ID | Command | Expected |
|---|---|---|
| A1 | `TMP=$(mktemp -d) && uv run mattstack init proj --preset starter-fullstack -o "$TMP" >/dev/null 2>&1; uv run mattstack add read-replica --path "$TMP/proj" --force; echo "exit=$?"` | `exit=0` |
| A2 | `grep -c '^  db-replica:' "$TMP/proj/docker-compose.yml"; grep -c 'profiles: \["replica"\]' "$TMP/proj/docker-compose.yml"` | `1` then `1` |
| A3 | `uv run python -c "import sys,yaml; d=yaml.safe_load(open(sys.argv[1])); s=d['services']; assert 'profiles' not in s['db']; assert s['db-replica']['profiles']==['replica']; assert 'postgres_replica_data' in d['volumes']; print('A3 ok')" "$TMP/proj/docker-compose.yml"` (unverified: PyYAML is in the project venv; otherwise use `uv run --with pyyaml python`) | prints `A3 ok` |
| A4 | `grep -c '^# DATABASE_REPLICA_URL=' "$TMP/proj/.env.example"; grep -c '^DATABASE_REPLICA_URL=' "$TMP/proj/.env.example"` | `1` then `0` |
| A5 | `uv run mattstack add read-replica --path "$TMP/proj" --force; echo "exit=$?"; grep -c '^# DATABASE_REPLICA_URL=' "$TMP/proj/.env.example"; uv run mattstack add read-replica --path "$TMP/proj"; find "$TMP/proj" -name '*.mattstack-new' \| wc -l` | `exit=0`, then `1` (no duplicate line), then `0` (identical rerun writes no `.mattstack-new`) |
| A6 | `TMP2=$(mktemp -d) && uv run mattstack init p --preset starter-fullstack -o "$TMP2" >/dev/null 2>&1; grep -c -e 'db-replica' -e 'postgres_replica_data' -e 'REPLICATION_PASSWORD' "$TMP2/p/docker-compose.yml"` | `0` (default output has no replica) |
| A7 | `docker compose -f "$TMP/proj/docker-compose.yml" config --services \| grep -c db-replica; docker compose -f "$TMP/proj/docker-compose.yml" --profile replica config --services \| grep -c db-replica` (needs Docker) | `0` then `1` |
| A8 | `docker compose -f "$TMP/proj/docker-compose.yml" --profile replica up -d --wait db db-replica`, then `docker compose -f "$TMP/proj/docker-compose.yml" exec -T db-replica psql -U postgres -tAc 'select pg_is_in_recovery()'`, then `docker compose -f "$TMP/proj/docker-compose.yml" exec -T db-replica psql -U postgres -c 'create table x(i int)'` (needs Docker) | `t`; the `create table` fails with `read-only transaction`; the primary's `select count(*) from pg_stat_replication where state='streaming'` run on `db` prints `1` |
| A9 | `grep -c 'DATABASE_REPLICA_URL' "$TMP/proj/docker-compose.yml"` (after `add read-replica`) | `0` (compose never hard-codes the replica URL, so default-off routing falls back to the primary) |
| A10 | `grep -c '^ *read_replica: true$' "$TMP/proj/mattstack.yml"` (after A1) | `1` |
| A11 | `uv run python -c "import sys; from pathlib import Path; from mattstack.project import resolve_project, save_project_config; from mattstack.commands.add import _update_root_files; c = resolve_project(Path(sys.argv[1])).config; print(c.use_read_replica); save_project_config(c); _update_root_files(c, dry_run=False, force=False)" "$TMP/proj"; grep -c '^  db-replica:' "$TMP/proj/docker-compose.yml"; find "$TMP/proj" -name '*.mattstack-new' \| wc -l` | `True`, then `1`, then `0`. A5 sets the flag itself, so only A11 proves the flag survives a reload and a regeneration. |
| A12 | `grep -c '^DB_REPLICA_PORT=5433$' "$TMP/proj/.env.example"; grep -c 'DB_REPLICA_PORT=5433' src/mattstack/commands/add_read_replica.py; grep -c 'import.*root_env' src/mattstack/templates/compose_env.py` | `1`, then at least `1` (the next steps tell the user to copy the port line), then `0` (no import cycle) |

A8 must pass before the PR is marked ready. If Docker is unavailable, open the PR as a draft and report A7 and A8 as not run.

Run these as well, and paste their exit codes into the PR:
- `uv run ruff format --check src/`
- `uv run ruff check src/`
- `uv run mypy src/`
- `uv run bandit -q -r src/ -c pyproject.toml`
- `uv run python scripts/check_architecture.py`
- `uv run python scripts/check_file_length.py`
- `uv run python scripts/gauntlet.py --gate install`

## Stop conditions and PR evidence

**Stop and report, do not open a PR, if:**
- Any owned file would exceed 400 lines (`scripts/check_file_length.py:15`). `root_env.py` reaches 400 at step 4, so any further line there stops the run. Check all eight owned files with `wc -l` after each edit.
- The step 1 gate fails: django-ninja-boilerplate issue #96 (https://github.com/mattjaikaran/django-ninja-boilerplate/issues/96) is not closed, or `core/db_routing.py` is not on its `main`. As of 2026-11-25, #96 is open and the file is absent. Check with `gh issue view 96 -R mattjaikaran/django-ninja-boilerplate --json state` and the `gh api` check in step 1.
- Any citation in this spec no longer matches at your HEAD: `config.py:172`, `compose_env.py:125` and `:139`, `docker_compose.py:29` and `:35-37`, `add.py:41`, `:159`, `:262`, `:270`, `runtime_profiles.py:207`, `:257-264`, `project.py:343`, `:367-376`, or `root_env.py:24`, `:46`, `:147-148`, and `root_env.py` at 399 lines before step 4.
- S-CLI-34 or S-CLI-36 is claimed by another agent (declared conflicts). If S-CLI-36 lands first, re-check `root_env.py` against the 400-line cap before step 4.
- The default (no flag) compose output changes (A6 fails).
- An unverified item fails in A8. Do not patch around it; report it.

**PR evidence:**
- Exit codes and output of A1-A11, marked as run or not run.
- Exit codes of every command in the verification list.
- The list of changed files, which must be a subset of Files owned.
- A note that the existing-volume manual step was printed and not automated.
- Overlap report: `config.py`, `add.py`, `compose_env.py`, and `root_env.py` are shared with S-CLI-36. `config.py`, `add.py`, `docker_compose.py`, `compose_env.py`, and `runtime_profiles.py` are shared with S-CLI-34. The PR must say so.
