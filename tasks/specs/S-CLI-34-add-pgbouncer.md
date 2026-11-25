# S-CLI-34: `mattstack add pgbouncer` routes Django app DB traffic through a transaction-mode pool

| Field | Value |
|---|---|
| Spec ID | S-CLI-34 |
| Backlog item | `docs/plans/2026-11-25-roadmap.md:90-99` (section 4, "Scaling: vertical and horizontal", PgBouncer item) |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-34 |
| Depends on | none |
| Conflicts with | S-CLI-35 (`templates/docker_compose.py`, `templates/compose_env.py`, `post_processors/customizer.py`) |
| Files owned | `src/mattstack/commands/add.py`, `src/mattstack/config.py`, `src/mattstack/runtime_profiles.py`, `src/mattstack/templates/docker_compose.py`, `src/mattstack/templates/compose_env.py`, `src/mattstack/templates/pgbouncer_service.py` (new), `src/mattstack/post_processors/customizer.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 15 |
| Max changed lines | 800 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install`; plus acceptance rows A1-A6 below |
| Acceptance criteria | A1; A2; A3; A4; A5; A6 (table below) |

## Context and verified citations

Base commit `e89fac4`. Line numbers were read at that commit. Items marked `(unverified)` must be confirmed by the executor before use. A failed confirmation is a stop condition.

Delta rule (parent): the django-ninja boilerplate already ships deployment manifests (deploy/k3s and Helm, `(unverified)`) and ROADMAP 4.24 (multi-DB, read replicas). This spec ticks only the CLI-side delta: the compose service, the backend host routing, and the Django settings patch. It does not touch any k8s or Helm manifests.

- `src/mattstack/commands/add.py:41` `VALID_COMPONENTS = ("frontend", "backend", "ios")`. `:138` `_root_files`. `:159` `_update_root_files` (writes `<name>.mattstack-new` when content differs, unless `--force`). `:198` `_save_metadata`. `:262-270` `run_add(component, project_path, framework, dry_run, force)` and its component check. `pgbouncer` is not a component, so add a branch before the check at `:270`.
- `src/mattstack/cli_scaffold.py:113` the `--dry-run` option for `add` (`(unverified)`: the `add` command's exact option names, including the path option, are read with `sed -n 100,130p src/mattstack/cli_scaffold.py`).
- `src/mattstack/config.py:172` `use_redis: bool = True`. Add `use_pgbouncer: bool = False` next to it.
- `src/mattstack/runtime_profiles.py:238` reads `redis = backend_meta.get("redis")`, and `:257` `apply_runtime_metadata(backend_meta, config)` writes `backend_meta["realtime"]` at `:261`. `_metadata_choice` is at `:197`, `runtime_kwargs` at `:207`. Use the same pattern for `backend.pgbouncer`.
- `src/mattstack/project.py:27` imports `apply_runtime_metadata, runtime_kwargs`. `:372` `"redis": config.use_redis`. `:376` `apply_runtime_metadata(backend, config)`.
- `src/mattstack/templates/docker_compose.py:29` `generate_docker_compose`. `:37` `services.append(db_service(config, production=False))`. `:41` redis append. Add the pgbouncer append after `:37`.
- `src/mattstack/templates/compose_env.py:125` `db_credentials`. `:139` `db_service` (`image: ${POSTGRES_IMAGE:-…}`, dev-only `ports` `127.0.0.1:${DB_PORT:-5432}:5432`, `pg_isready` healthcheck). `:186` `backend_env`. `:214` python-branch `DATABASE_URL` `{scheme}://…@db:5432/{name}`. `:243` comment, `:250` `DB_HOST: "db"`. Both must read `pgbouncer` when the flag is set.
- `src/mattstack/post_processors/customizer.py:46` `_customize_django_backend(config)` patches backend files by `str.replace` (`:52`, `:56`, `:61`, `:64`, `:65`). Add the settings patch here.
- Compose-level pgbouncer image: `edoburu/pgbouncer:v1.26.1-p0`. Verified in the prior research pass: Docker Hub tags `v1.26.1-p0` (2026-10-19) and `latest`. Listens on port 5432 by default. Almost every pgbouncer.ini key can be set by env var. MD5 auth is the default in the README.
- `(unverified)` Auth type. Postgres 14+ defaults to SCRAM. Whether the edoburu image accepts `AUTH_TYPE=scram-sha-256` is not confirmed. The executor confirms it against the image README before the compose env is final. If not confirmed, stop (see stop conditions).
- pgbouncer config key `max_prepared_statements` exists (verified at https://www.pgbouncer.org/config.html). Not used here, because Django's psycopg binding does not need it by default. `(unverified: Django version default)`.
- Django docs: `DISABLE_SERVER_SIDE_CURSORS` is a documented `DATABASES` option (verified at https://docs.djangoproject.com/en/5.2/ref/databases/). Transaction pooling requires it.
- Boilerplate: `api/settings/common.py:250` `"CONN_MAX_AGE": 0`. The trailing comma in the exact anchor text is `(unverified)`. The executor counts matches for the anchor (see A6).
- Ninja settings do not currently read `DISABLE_SERVER_SIDE_CURSORS`. Verified by grep at `e89fac4`'s boilerplate `origin/main`. So the CLI must patch the settings file, not only set an env var.

## Goal and non-goals

Goal: `mattstack add pgbouncer` in an existing django-ninja project:
1. Persists `backend.pgbouncer: true` in `mattstack.yml`.
2. Regenerates `docker-compose.yml` with a `pgbouncer` service (image pinned to `edoburu/pgbouncer:v1.26.1-p0`, `POOL_MODE=transaction`, port 5432 internal, no published ports, healthcheck via `pg_isready`).
3. Points the backend `DATABASE_URL` and `DB_HOST` at `pgbouncer` instead of `db`.
4. Adds `"DISABLE_SERVER_SIDE_CURSORS": True,` after the `"CONN_MAX_AGE": 0,` anchor in `api/settings/common.py`.
5. Is idempotent: a second run changes nothing.

Non-goals:
- No django-matt, FastAPI, or NestJS support. Those presets refuse with exit 1 (A5).
- No k8s or Helm changes. Those belong to the boilerplate (delta rule).
- No live connection test in CI (docker not required by the acceptance rows).
- No replica routing (see S-CLI-35).
- No tests under `tests/`. No pytest.

## Implementation steps

1. `config.py`: add `use_pgbouncer: bool = False` next to `use_redis`.
2. `runtime_profiles.py`: in `runtime_kwargs`, read `backend_meta.get("pgbouncer", False)` as a bool and pass it as `use_pgbouncer`. In `apply_runtime_metadata`, write `backend_meta["pgbouncer"] = True` when set, and `backend_meta.pop("pgbouncer", None)` when not. Do not write a `false` key, so existing `mattstack.yml` files do not change.
3. `project.py`: add `"pgbouncer": config.use_pgbouncer` to the runtime dict next to `"redis"` (`:372`) only if that dict is what the metadata writer uses. The executor confirms this with `sed -n 360,380p src/mattstack/project.py`.
4. New `templates/pgbouncer_service.py`: `pgbouncer_service(config) -> str` returning the service YAML (image, env: `DATABASE_URL` to `db:5432`, `POOL_MODE: transaction`, `DEFAULT_POOL_SIZE: 20`, `MAX_CLIENT_CONN: 200`, healthcheck `pg_isready -h 127.0.0.1 -p 5432`, `depends_on: db: condition: service_healthy`).
5. `docker_compose.py`: after line 37, `if config.use_pgbouncer: services.append(pgbouncer_service(config))`.
6. `compose_env.py`: in the python branch of `backend_env`, use host `pgbouncer` when `config.use_pgbouncer`, else `db`, for both the `DATABASE_URL` at `:214` and `DB_HOST` at `:250`.
7. `commands/add.py`: in `run_add`, before the component check at `:270`, handle `component == "pgbouncer"`. Refuse with exit 1 unless the backend is django-ninja. Set the flag, save metadata, and call `_update_root_files` for the root files so compose regenerates. Respect `--dry-run`.
8. `customizer.py`: in `_customize_django_backend`, when `config.use_pgbouncer`, replace the single `"CONN_MAX_AGE": 0,` occurrence in `api/settings/common.py` with the same line plus `"DISABLE_SERVER_SIDE_CURSORS": True,`. If the anchor count is not exactly one, stop.
9. Run the verification commands once at the end. Do not add tests to `tests/`.

## Acceptance criteria

Each row runs the CLI from the repo root. `$TMP` is a fresh `mktemp -d`. The fixture is a django-ninja project created with `uv run mattstack init "$TMP/proj" --preset starter-fullstack` (`(unverified)`: init flags; the executor confirms them with `uv run mattstack init --help`). The preset `starter-fullstack` is at `src/mattstack/presets.py:66`. Its default backend framework is django-ninja (`presets.py:32`).

| ID | Cwd | Exact command | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `uv run mattstack add pgbouncer --path "$TMP/proj"; echo "exit=$?"; grep -c 'image: edoburu/pgbouncer:v1.26.1-p0' "$TMP/proj/docker-compose.yml"` | `exit=0`, then `1` | Exactly one pinned image line. |
| A2 | repo root | `grep -c 'DB_HOST: "pgbouncer"' "$TMP/proj/docker-compose.yml"; grep -c '@db:5432' "$TMP/proj/docker-compose.yml"` | `1` (backend DB_HOST), then `1` (only the pgbouncer upstream URL; app URLs no longer point at `db`) | No backend env value points at `db:5432`. `(unverified)`: the exact `DB_HOST` line format; the executor confirms it from the rendered file. |
| A3 | repo root | `uv run python -c 'import sys,yaml; d=yaml.safe_load(open(sys.argv[1])); b=d["backend"]; assert b.get("pgbouncer") is True, b; print("A3 ok")' "$TMP/proj/mattstack.yml"` | exit 0 | stdout `A3 ok`. |
| A4 | repo root | `sha=$(sha256sum "$TMP/proj/docker-compose.yml" \| cut -d' ' -f1); uv run mattstack add pgbouncer --path "$TMP/proj"; echo "exit=$?"; test "$(sha256sum "$TMP/proj/docker-compose.yml" \| cut -d' ' -f1)" = "$sha" && echo same; test ! -e "$TMP/proj/docker-compose.yml.mattstack-new" && echo no-new-file` | `exit=0`, then `same`, then `no-new-file` | Second run is a no-op. |
| A5 | repo root | `mkdir -p "$TMP/api" && cp -r "$TMP/proj/." "$TMP/api/" && sed -i.bak 's/framework: django-ninja/framework: fastapi/' "$TMP/api/mattstack.yml"; uv run mattstack add pgbouncer --path "$TMP/api"; echo "exit=$?"` | `exit=1` | Output mentions `pgbouncer` and the framework. `(unverified)`: the exact framework key spelling in `mattstack.yml`; the executor reads it from the fixture first. |
| A6 | repo root | `grep -c '"DISABLE_SERVER_SIDE_CURSORS": True' "$TMP/proj/backend/api/settings/common.py"; grep -c '"CONN_MAX_AGE": 0' "$TMP/proj/backend/api/settings/common.py"` | `1` then `1` | The settings patch lands once, and the anchor was matched exactly once before the patch. |

## Stop conditions and PR evidence

Stop and report, without editing other files, if any of these happen:
- A citation in this spec no longer matches at the base commit. Re-verify it with `sed -n` before continuing.
- The edoburu image README does not confirm `AUTH_TYPE` as an env var, or the auth type cannot be matched to the Postgres server's password hashing. Report it. Do not ship an unverified auth setting.
- The `"CONN_MAX_AGE": 0,` anchor count is not exactly one in `api/settings/common.py`.
- `docker-compose.yml` or `compose_env.py` would exceed 400 lines (`scripts/check_file_length.py`). Split out a helper first.
- The boilerplate already ships a pgbouncer service in its deploy manifests. Report it and stop. Do not duplicate it (delta rule).

PR evidence: stdout and exit codes of A1-A6, plus the output of each verification command.
