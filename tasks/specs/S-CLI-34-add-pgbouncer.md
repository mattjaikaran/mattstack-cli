# S-CLI-34: `mattstack add pgbouncer` routes app DB traffic through a transaction-mode pool

| Field | Value |
|---|---|
| Spec ID | S-CLI-34 |
| Backlog item | GitHub issue #143; `docs/plans/2026-11-25-roadmap.md:90-99` (section 4, "Scaling: vertical and horizontal", PgBouncer item) |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-34 |
| Depends on | none |
| Conflicts with | S-CLI-35 (`src/mattstack/config.py`, `src/mattstack/commands/add.py`, `templates/docker_compose.py`, `templates/compose_env.py`, `runtime_profiles.py`); S-CLI-36 (`src/mattstack/commands/add.py`, `src/mattstack/config.py`, `src/mattstack/templates/compose_env.py`) |
| Files owned | `src/mattstack/commands/add_pgbouncer.py` (new), `src/mattstack/commands/add.py` (dispatch only), `src/mattstack/config.py`, `src/mattstack/runtime_profiles.py`, `src/mattstack/templates/docker_compose.py`, `src/mattstack/templates/compose_env.py`, `src/mattstack/templates/pgbouncer_service.py` (new) |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 15 |
| Max changed lines | 800 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install`; plus acceptance rows A1-A8 below |
| Acceptance criteria | A1; A2; A3; A4; A5; A6; A7 (live, needs docker); A8 (printed note) |

## Context and verified citations

Base commit `e89fac4`. Line numbers were read at that commit. Items marked `(unverified)` must be confirmed by the executor before use. A failed confirmation is a stop condition.

Delta rule (parent): the django-ninja boilerplate already ships deployment manifests (deploy/k3s and Helm, `(unverified)`) and ROADMAP 4.24 (multi-DB, read replicas). This spec ticks only the CLI-side delta: the compose service, the backend host routing, the migrate override, and the pool env lever. It does not touch k8s or Helm manifests.

### CLI code

- `src/mattstack/commands/add.py:41` `VALID_COMPONENTS = ("frontend", "backend", "ios")`. `:138` `_root_files`. `:159` `_update_root_files`. It treats existing root files as user files: without `--force` it writes `<name>.mattstack-new` when content differs and never edits `docker-compose.yml` or `.env` in place. `:198` `_save_metadata`. `:262-270` `run_add(component, project_path, framework, dry_run, force)` and its component check.
- `add.py` is near the 400-line cap (about 323 lines, `(unverified)` count). All pgbouncer logic therefore goes into the new module `commands/add_pgbouncer.py`. `add.py` gets only a dispatch branch before the component check.
- `src/mattstack/cli_scaffold.py:113` the `--dry-run` option for `add`. `(unverified)`: the path option name, read with `sed -n 100,130p src/mattstack/cli_scaffold.py`.
- `src/mattstack/config.py:172` `use_redis: bool = True`. Add `use_pgbouncer: bool = False` next to it.
- `src/mattstack/runtime_profiles.py:238` reads `redis = backend_meta.get("redis")`; `:257` `apply_runtime_metadata(backend_meta, config)` writes `backend_meta["realtime"]` at `:261`. `runtime_kwargs` is at `:207`. Use the same pattern for `backend.pgbouncer`.
- `src/mattstack/templates/docker_compose.py:29` `generate_docker_compose`. `:37` `services.append(db_service(config, production=False))`. `:72` `_migrate_service`. `backend_env` is rendered once as a shared YAML anchor, and every backend service inherits it, including `migrate`.
- `src/mattstack/templates/compose_env.py:125` `db_credentials`. `:139` `db_service`. `:186` `backend_env`. `:200` nestjs `DATABASE_URL`. `:214` python-branch `DATABASE_URL` `{scheme}://…@db:5432/{name}`. `:250` `DB_HOST: "db"`.

### pgbouncer image (edoburu)

- Image `edoburu/pgbouncer:v1.26.1-p0`. Verified in the prior pass: Docker Hub tags `v1.26.1-p0` (2026-10-19) and `latest`.
- Listens on `LISTEN_PORT`, default 5432 (`entrypoint.sh:115`, verified at master). The compose service pins `LISTEN_PORT: 5432` explicitly. The spec does not use 6432.
- Auth: `entrypoint.sh:120` defaults `auth_type` to md5. Postgres 14+ stores passwords as SCRAM-SHA-256. `entrypoint.sh:55-61` writes `userlist.txt` for `AUTH_TYPE` `plain` or `scram-sha-256` when `DB_USER` and `DB_PASSWORD` are set (verified at master). The compose env sets `AUTH_TYPE: scram-sha-256` explicitly. A live row (A7) is the real proof that logins succeed.
- The entrypoint reads these env vars (verified at master): `DATABASE_URL` (parsed at `entrypoint.sh:83-84`), `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `AUTH_TYPE`, `LISTEN_PORT`, `POOL_MODE` (`entrypoint.sh:124`), `DEFAULT_POOL_SIZE`, `MAX_CLIENT_CONN`.

### Ninja boilerplate (`~/dev/boilerplates/django-ninja-boilerplate`, `origin/main`)

- `api/settings/common.py:250` `"CONN_MAX_AGE": 0` is hardcoded. Lines 205-211 explain why it must stay 0 with the psycopg pool.
- The DB pool is enabled by `DB_POOL_ENABLED` (`api/settings/common.py:219`, default True, verified on `origin/main`). The comment at lines 216-217 says task workers fork after Django loads, and their Compose services set `DB_POOL_ENABLED=false`. This matches the design below.
- `DISABLE_SERVER_SIDE_CURSORS` is not read from env (verified: no match in `origin/main:api/settings/common.py`). Setting it needs a boilerplate change, so this spec does not set it (non-goal; see A8).
- Consequence: `CONN_MAX_AGE=0` or `DISABLE_SERVER_SIDE_CURSORS=True` in `.env` or compose does nothing for ninja. The env lever that works is `DB_POOL_ENABLED=false` on services behind pgbouncer, so the app does not pool twice.

### Django docs

- `DISABLE_SERVER_SIDE_CURSORS` is a documented `DATABASES` option (`(unverified)`: the Django 5.2 docs URL https://docs.djangoproject.com/en/5.2/ref/databases/ was not fetched in this pass). Transaction pooling needs it when `iterator()` runs server-side cursors. The CLI prints this as a manual note.
- pgbouncer config key `max_prepared_statements` (`(unverified)`: https://www.pgbouncer.org/config.html not fetched in this pass). Not set here; the executor confirms before relying on the claim that psycopg needs no prepared statements under this setup.

## Goal and non-goals

Goal: `mattstack add pgbouncer` in an existing django-ninja project:
1. Persists `backend.pgbouncer: true` in `mattstack.yml`.
2. Renders `docker-compose.yml` with a `pgbouncer` service: image pinned to `edoburu/pgbouncer:v1.26.1-p0`, `AUTH_TYPE: scram-sha-256`, `LISTEN_PORT: 5432`, `POOL_MODE: transaction`, no published ports, healthcheck via `pg_isready`, `depends_on: db: condition: service_healthy`.
3. Routes api and worker services (the shared `backend_env` anchor) to `DB_HOST: pgbouncer` and a `DATABASE_URL` host of `pgbouncer:5432`. Sets `DB_POOL_ENABLED: "false"` on those services.
4. Overrides the `migrate` service back to direct `db:5432`, because migrations use session state (`SET`, advisory locks, multi-statement DDL) that transaction pooling breaks.
5. App services `depends_on` pgbouncer.
6. Prints a manual note for `DISABLE_SERVER_SIDE_CURSORS` (boilerplate change required).

Non-goals:
- No django-matt, FastAPI, or NestJS support. Those presets refuse with exit 1 (A5).
- No k8s or Helm changes.
- No settings file patch. `DISABLE_SERVER_SIDE_CURSORS` is a printed note only.
- No replica routing (see S-CLI-35).
- No tests under `tests/`. No pytest.

## Rerun and `--force` contract

Root files are user files (`add.py`, `_update_root_files`). `add pgbouncer` follows the same contract:
- First run without `--force`: sets the flag in `mattstack.yml`. The rendered compose is written as `docker-compose.yml.mattstack-new` if it differs from the existing file. The existing `docker-compose.yml` is not edited.
- Run with `--force`: overwrites `docker-compose.yml` with the rendered content.
- Rerun after `--force`: the rendered content equals the file, so no `.mattstack-new` is created, and the file's SHA-256 does not change. This is the idempotence guarantee.
- `--dry-run`: prints the planned change, writes nothing.

## Implementation steps

1. `config.py`: add `use_pgbouncer: bool = False`.
2. `runtime_profiles.py`: read `backend_meta.get("pgbouncer", False)` as a bool into `use_pgbouncer` in `runtime_kwargs`. In `apply_runtime_metadata`, write `backend_meta["pgbouncer"] = True` when set, and `backend_meta.pop("pgbouncer", None)` when not. Do not write a `false` key, so existing `mattstack.yml` files do not change.
3. `templates/pgbouncer_service.py` (new): `pgbouncer_service(config) -> str`, returning the service YAML (image, env `DATABASE_URL` to `db:5432`, `AUTH_TYPE: scram-sha-256`, `LISTEN_PORT: 5432`, `POOL_MODE: transaction`, `DEFAULT_POOL_SIZE: 20`, `MAX_CLIENT_CONN: 200`, healthcheck `pg_isready -h 127.0.0.1 -p 5432`, `depends_on: db: condition: service_healthy`).
4. `compose_env.py` `backend_env`: when `config.use_pgbouncer`, use host `pgbouncer` at `:214` and `:250`, and set `DB_POOL_ENABLED: "false"`. Keep the python branch only (ninja).
5. `docker_compose.py`:
   - After `:37`, append `pgbouncer_service(config)` when the flag is set.
   - In `_migrate_service` (`:72`), explicitly override `environment` with `DB_HOST: "db"` and `DATABASE_URL` to `db:5432` after the merge key, so migrate stays direct.
   - App services gain `depends_on: pgbouncer`.
6. `commands/add_pgbouncer.py` (new): `run_add_pgbouncer(project_path, dry_run, force)`. It refuses with exit 1 unless the backend is django-ninja (use the existing ninja predicate `is_ninja_backend` at `config.py:262`). It sets the flag, saves metadata, renders root files via the existing `_update_root_files` contract (see the rerun section), and prints the `DISABLE_SERVER_SIDE_CURSORS` note.
7. `commands/add.py`: in `run_add`, before the component check at `:270`, dispatch `component == "pgbouncer"` to `run_add_pgbouncer`. Nothing else changes in `add.py`.
8. Run the verification commands once at the end. Do not add tests to `tests/`.

## Machine-checkable acceptance

Each row runs from the repo root. `$TMP` is a fresh `mktemp -d`. Fixtures are django-ninja projects created with `uv run mattstack init proj --preset starter-fullstack -o "$TMP"` (`(unverified)`: init flags; confirm with `uv run mattstack init --help`). `starter-fullstack` is at `src/mattstack/presets.py:66`, and its default backend framework is django-ninja (`presets.py:32`).

| ID | Cwd | Exact command | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `uv run mattstack add pgbouncer --path "$TMP/proj" --force; echo "exit=$?"; grep -c 'image: edoburu/pgbouncer:v1.26.1-p0' "$TMP/proj/docker-compose.yml"` | `exit=0`, then `1` | Exactly one pinned image line. |
| A2 | repo root | `uv run mattstack init p2 --preset starter-fullstack -o "$TMP" >/dev/null 2>&1; sha=$(sha256sum "$TMP/p2/docker-compose.yml" \| cut -d' ' -f1); uv run mattstack add pgbouncer --path "$TMP/p2"; echo "exit=$?"; test "$(sha256sum "$TMP/p2/docker-compose.yml" \| cut -d' ' -f1)" = "$sha" && echo unchanged; grep -c 'image: edoburu/pgbouncer' "$TMP/p2/docker-compose.yml.mattstack-new"` | `exit=0`, then `unchanged`, then `1` | Without `--force`, the existing compose file is untouched and the rendered version is written beside it. |
| A3 | repo root | `uv run python -c 'import sys,yaml; b=yaml.safe_load(open(sys.argv[1]))["backend"]; assert b.get("pgbouncer") is True, b; print("A3 ok")' "$TMP/proj/mattstack.yml"` | exit 0 | stdout `A3 ok`. `(unverified)`: PyYAML is importable in the project venv. If not, the executor uses `grep -c 'pgbouncer: true'` and records that. |
| A4 | repo root | `sha=$(sha256sum "$TMP/proj/docker-compose.yml" \| cut -d' ' -f1); uv run mattstack add pgbouncer --path "$TMP/proj" --force; echo "exit=$?"; test "$(sha256sum "$TMP/proj/docker-compose.yml" \| cut -d' ' -f1)" = "$sha" && echo same; test ! -e "$TMP/proj/docker-compose.yml.mattstack-new" && echo no-new-file` | `exit=0`, then `same`, then `no-new-file` | Rerun after `--force` is a no-op. |
| A5 | repo root | `mkdir -p "$TMP/api" && cp -r "$TMP/proj/." "$TMP/api/" && sed -i.bak 's/framework: django-ninja/framework: fastapi/' "$TMP/api/mattstack.yml"; uv run mattstack add pgbouncer --path "$TMP/api"; echo "exit=$?"` | `exit=1` | Output mentions `pgbouncer` and the framework. `(unverified)`: the exact framework key spelling in `mattstack.yml`; the executor reads it from the fixture first. |
| A6 | repo root | `uv run python -c 'import sys,yaml; s=yaml.safe_load(open(sys.argv[1]))["services"]; api=[k for k in s if k in ("api","backend")]; assert api, list(s); assert s[api[0]]["environment"]["DB_HOST"]=="pgbouncer"; assert s["migrate"]["environment"]["DB_HOST"]=="db", s["migrate"]; assert "pgbouncer" in str(s[api[0]].get("depends_on")); assert s["pgbouncer"]["healthcheck"]; print("A6 ok")' "$TMP/proj/docker-compose.yml"` | exit 0 | stdout `A6 ok`. `(unverified)`: the app service name (`api` or `backend`) and whether `environment` is a mapping; the executor confirms from the rendered file and records the names it used. |
| A7 | repo root | `docker compose -f "$TMP/proj/docker-compose.yml" up -d --wait db pgbouncer && docker compose -f "$TMP/proj/docker-compose.yml" exec -T db psql -h pgbouncer -p 5432 -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" -tAc 'select 1'` | exit 0, stdout `1` | Live proof that pgbouncer accepts SCRAM logins. Requires a docker daemon. If docker is unavailable the row is BLOCKED, not PASS. `(unverified)`: `POSTGRES_USER` and `POSTGRES_DB` values in the rendered `.env`. |
| A8 | repo root | `uv run mattstack add pgbouncer --path "$TMP/p2" --force 2>&1 \| grep -c 'DISABLE_SERVER_SIDE_CURSORS'` | `1` or more | The printed note is present, so the user knows the boilerplate setting is not set by the CLI. |

## Stop conditions and PR evidence

Stop and report, without editing other files, if any of these happen:
- A citation in this spec no longer matches at the base commit. Re-verify it with `sed -n` before continuing.
- The edoburu entrypoint at the pinned tag `v1.26.1-p0` does not write `userlist.txt` for `AUTH_TYPE=scram-sha-256`. The check above was done at master, not at the tag, so re-check the tag. Do not ship an unverified auth setting.
- `DB_POOL_ENABLED` is not read from env on `origin/main` of the boilerplate. Report it; `DB_POOL_ENABLED: "false"` then does nothing and must be removed from the spec.
- `docker-compose.yml` or `compose_env.py` would exceed 400 lines (`scripts/check_file_length.py`). Split out a helper first.
- The boilerplate already ships a pgbouncer service in its deploy manifests. Report it and stop (delta rule).
- A7 cannot run (no docker). Report BLOCKED. Do not mark the spec complete without A7 PASS.

PR evidence: stdout and exit codes of A1-A8, plus the output of each verification command.
