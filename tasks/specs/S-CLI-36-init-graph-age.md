# S-CLI-36: `init --graph age` builds a Postgres image with Apache AGE and pgvector

| Field | Value |
|---|---|
| Spec ID | S-CLI-36 |
| Backlog item | GitHub issue #145; `tasks/todo.md:32-33` (the AI layer's `--graph age` path: the rejection at `init_runtime.py:63-68` says the `apache/age` image has no pgvector) |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | 3458590 |
| Branch | agent/S-CLI-36 |
| Depends on | none |
| Conflicts with | S-CLI-37, S-CLI-38, S-CLI-39, S-CLI-09, S-CLI-10; S-CLI-34 (`src/mattstack/commands/add.py`, `src/mattstack/config.py`, `src/mattstack/templates/compose_env.py`); S-CLI-40 (`src/mattstack/cli_scaffold.py`) |
| Files owned | `src/mattstack/config.py`, `src/mattstack/cli_scaffold.py`, `src/mattstack/commands/init_runtime.py`, `src/mattstack/templates/compose_env.py`, `src/mattstack/templates/root_env.py`, `src/mattstack/templates/postgres_age.py` (new), `src/mattstack/generators/backend_only.py`, `src/mattstack/generators/fullstack.py`, `src/mattstack/commands/add.py`, `scripts/smoke_graph_age.py` (new) |
| Migrations | none |
| Runtime locks | none |
| Human needed | Docker daemon for acceptance row A6 only. If Docker is unavailable, stop and report; do not skip A6. |
| Size | M |
| Max files | 15 |
| Max changed lines | 800 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install` (regression only, no edits to it); `uv run python scripts/smoke_graph_age.py`; plus CLI rows A1 to A6 below |
| Acceptance criteria | A1; A2; A3; A4; A5; A6 (table below) |

## Context and verified citations

Re-verified at `3458590` (the base SHA on 2026-11-25). Line numbers below were re-read at that SHA. Earlier notes at `e89fac4` are stale.

- `src/mattstack/commands/init_runtime.py:63-68`: `if graph == "age":` prints the "not supported" error and raises `typer.Exit(code=2)`. That block is the one to remove. `init_runtime.py:70-71` maps `--graph` to `GraphStore`.
- `src/mattstack/config.py:77-81` `GraphStore` has only `CTE = "cte"` and `NEO4J = "neo4j"`. `config.py:69-73` `AiStore` has `NONE`, `PGVECTOR`, and `QDRANT`. `config.py:251-254` `use_ai` is `ai_store != NONE or graph_store != CTE`, so an AGE value sets `use_ai` without a change here.
- Every place that branches on `graph_store` (checked with `grep -rln graph_store src/mattstack --include=*.py`): `commands/init_runtime.py`, `config.py`, `runtime_profiles.py`, `templates/compose_env.py`, `templates/root_env.py`. `runtime_profiles.py:197-204` `_metadata_choice` is generic over the enum, and `runtime_profiles.py:263-264` writes `graph_store.value` generically, so `runtime_profiles.py` needs no change once `GraphStore.AGE` exists. Persisted `mattstack.yml` load and save go through the same generic path.
- `src/mattstack/cli_scaffold.py:66-72` is the `--graph` help text.
- `src/mattstack/templates/compose_env.py` is 341 lines (under the 400-line gate). `compose_env.py:29-34` `_IMAGE_DEFAULTS` sets `postgres` to `17-alpine`. `compose_env.py:52-55` `service_major()` returns the major, so the project's Postgres major is `service_major(config, "postgres")`. `compose_env.py:58-60` `pgvector_image()` returns `pgvector/pgvector:pg{major}`.
- `compose_env.py:139-160` `db_service`: line 149 is `image: ${{POSTGRES_IMAGE:-{service_image(config, "postgres")}}}`. The `db` service has no `command:` override, and this spec adds none.
- `src/mattstack/templates/root_env.py:212` `_ai_lines`: line 221 writes `POSTGRES_IMAGE={pgvector_image(config)}` whenever `use_ai` is set, and AGE sets `use_ai`. Line 225 is the `if config.graph_store == GraphStore.NEO4J:` branch.
- Compose files are written in three places: `src/mattstack/generators/backend_only.py:59`, `src/mattstack/generators/fullstack.py:80`, and `src/mattstack/commands/add.py:152` (inside the `files` list that `add.py` builds before line 152).
- `src/mattstack/runtime_profiles.py:105-108` raises when a `use_ai` project's backend has no `ai` extra. An AGE project needs the backend `ai` extra, the same as Neo4j. This spec does not change that rule.
- `scripts/gauntlet.py:290` `_gate_install`, with `sync2` at line 339 and `return _smoke_python_pin(...)` at line 343. This spec does not edit `gauntlet.py`. The new check lives in its own script, `scripts/smoke_graph_age.py`, which is called from this spec's Verification commands, so it does not conflict with S-CLI-18.
- Image pins, verified on 2026-11-25:
  - Docker Hub tags for `apache/age` (`hub.docker.com/v2/repositories/apache/age/tags`) include `release_PG17_1.7.0` and `release_PG18_1.8.0`. The map from Postgres major to AGE release is therefore `{17: "release_PG17_1.7.0", 18: "release_PG18_1.8.0"}`.
  - The `master` branch Dockerfile (`raw.githubusercontent.com/apache/age/master/docker/Dockerfile`) builds on `postgres:18` and installs `postgresql-server-dev-18` with apt. The PG17 release's base is not verified here, because the release-tag Dockerfile could not be fetched. A6 verifies it by building.
  - The pgvector README (`raw.githubusercontent.com/pgvector/pgvector/master/README.md`, lines 26-29 and 1247) builds with `make` and `make install`. It needs `pg_config` on the PATH, which the `postgresql-server-dev-<N>` package provides. The tag is `v0.8.7`.
- `tasks/specs/S-CLI-01-ci-pgvector-image.md` (READY) owns `workflow.py` and `ci_toolchain.py`, not the files above. CI for AGE projects is a non-goal (see below).

## Goal and non-goals

Goal: `mattstack init <name> --graph age` produces a project whose Compose `db` service builds `docker/postgres-age/Dockerfile`. The base image is `apache/age:release_PG{N}_{version}`, where `N` is the project's Postgres major (`service_major`). pgvector `v0.8.7` is compiled into it, so one database has both AGE and pgvector. The `--graph age` value is accepted, the rejection at `init_runtime.py:63-68` is gone, and `--graph bogus` still fails.

Non-goals:
- No change to the backend repo, its `docs/AI_LAYER.md`, or its code that uses AGE.
- No change to CI. The generated CI keeps the pgvector image for AGE projects and does not exercise AGE. This is a known gap, recorded in the PR body. `workflow.py` and `ci_toolchain.py` belong to S-CLI-01.
- No AGE-specific health check. S-CLI-39 covers Qdrant and Neo4j only.
- No change to `--ai` behavior. With `--ai pgvector` and `--graph age`, the built image already contains pgvector, so `POSTGRES_IMAGE` is not written.
- No `tests/` file and no pytest. S-CLI-18 forbids both. The regression guard is `scripts/smoke_graph_age.py`, a standalone script.
- No `command:` override on the `db` service. If one is added later, it must keep `shared_preload_libraries=age`, because a `command:` replaces the upstream CMD.

## Implementation steps

1. `config.py:77-81`: add `AGE = "age"` to `GraphStore`. Leave `use_ai` (251-254) unchanged.
2. `commands/init_runtime.py:63-68`: delete the `if graph == "age":` block. Leave the rest of the function alone.
3. `cli_scaffold.py:66-72`: change the `--graph` help text to exactly `AI layer graph: cte (recursive SQL, default), neo4j (graph profile), or age (Apache AGE; builds the db image)`.
4. New `templates/postgres_age.py`:
   - `AGE_RELEASES = {17: "release_PG17_1.7.0", 18: "release_PG18_1.8.0"}` and `PGVECTOR_TAG = "v0.8.7"`.
   - `age_base(major: int) -> str` returns `apache/age:{AGE_RELEASES[major]}`. Any other major raises `ValueError`, naming the supported majors.
   - `render_dockerfile(major: int) -> str` returns the Dockerfile below, with `{major}` substituted into `postgresql-server-dev-{major}` and `FROM` set by `age_base(major)`:
     ```
     FROM apache/age:release_PG17_1.7.0
     USER root
     RUN apt-get update \
      && apt-get install -y --no-install-recommends build-essential git postgresql-server-dev-17 \
      && git clone --depth 1 --branch v0.8.7 https://github.com/pgvector/pgvector.git /tmp/pgvector \
      && make -C /tmp/pgvector \
      && make -C /tmp/pgvector install \
      && rm -rf /tmp/pgvector /var/lib/apt/lists/*
     ```
     The example above is for PG17. The rendered text must match `age_base(major)` and `postgresql-server-dev-{major}` for the given major.
   - `render_db_build_block() -> str` returns the Compose `build:` lines: `build:`, `context: ./docker/postgres-age`, and `dockerfile: Dockerfile`.
5. `templates/compose_env.py:139-160` `db_service`: when `config.graph_store == GraphStore.AGE`, replace line 149 (`image: ...`) with the `build:` block from `render_db_build_block()`. Do not write an `image:` line for AGE. Ports, environment, volumes, and the healthcheck stay the same for dev and production.
6. `templates/root_env.py:212-227`: in `_ai_lines`, skip the `POSTGRES_IMAGE=` line when `graph_store` is AGE, using the same `if` shape as the Neo4j branch at line 225.
7. `generators/backend_only.py:59`, `generators/fullstack.py:80`, and `commands/add.py:140-152`: when the graph is AGE, also write `docker/postgres-age/Dockerfile` with `render_dockerfile(service_major(config, "postgres"))`, in the same place as the `docker-compose.yml` write.
8. New `scripts/smoke_graph_age.py`, standalone, not a gauntlet gate:
   - Checks `age_base(17)` and `age_base(18)` return the mapped tags.
   - Checks `age_base(16)` raises `ValueError`.
   - Renders `render_dockerfile(17)` and `render_dockerfile(18)`. Each must contain its `FROM` line and `postgresql-server-dev-{N}`.
   - Builds a `ProjectConfig` with `graph_store=GraphStore.AGE` and `ai_store=AiStore.PGVECTOR`, then renders `db_service` and `_ai_lines`. The db output must contain `build:` and `dockerfile: Dockerfile`, and must not contain `POSTGRES_IMAGE`. The `_ai_lines` output must not contain a `POSTGRES_IMAGE=` line. If `ProjectConfig` needs required fields beyond `name` and `path`, stop and report.
   - Exits 0 and prints `ok` on success, non-zero with the failing check otherwise.

## Machine-checkable acceptance

Run each row from the stated cwd. `$REPO` is `git rev-parse --show-toplevel` in the checkout. `$TMP` is `mktemp -d`. A row passes only when the exit code and the assertion both hold.

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | `$REPO` | `uv run mattstack init --help` | 0 | stdout contains `or age (Apache AGE; builds the db image)` |
| A2 | `$REPO` | `uv run mattstack init demo --graph age --dry-run` | 0 | stdout contains `docker/postgres-age/Dockerfile`, and no `demo/` directory is created |
| A3 | `$REPO` | `uv run mattstack init demo --graph bogus --dry-run` | non-zero | stdout or stderr lists `age` among the valid graph values |
| A4 | `$REPO` | `uv run python scripts/smoke_graph_age.py` | 0 | stdout's last line is `ok` |
| A5 | `$REPO` | `grep -c "graph age is not supported" src/mattstack/commands/init_runtime.py` | 0 (grep prints `0`, exit 1 is also a pass here) | the count is `0` |
| A6 | `$TMP` | Render `render_dockerfile(17)` to `$TMP/postgres-age/Dockerfile`, then `docker build -t mattstack-age-test "$TMP/postgres-age"`, then `docker run -d --name agetest -e POSTGRES_PASSWORD=x mattstack-age-test`, wait for `docker exec agetest pg_isready -U postgres`, then `docker exec agetest psql -U postgres -tAc "CREATE EXTENSION IF NOT EXISTS age; CREATE EXTENSION IF NOT EXISTS vector; SELECT extname FROM pg_extension WHERE extname IN ('age','vector') ORDER BY 1;"`. Remove the `agetest` container afterward. | 0 | the build succeeds, and the query prints `age` and `vector` |

A6 needs Docker. If the build fails because the PG17 release base has no `postgresql-server-dev-17` or no `apt-get`, stop and report the base; do not change the tag to get a pass.

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a new dependency, or a check that fails outside your change. Stop if `make install` cannot find `pg_config`, if `apache/age:release_PG17_1.7.0` is not pullable, if the release base lacks `apt-get` or `postgresql-server-dev-17`, if A2 needs network access to the boilerplate repo to print its dry-run plan (report it and do not work around it), or if Docker is not available for A6. Commit nothing when stopped; report the exact discrepancy.

PR body: spec ID, base `3458590` and head SHA, owned files with changed-line counts, the output of rows A1 to A6, the output of each verification command, and the known gap that the generated CI does not exercise AGE. Commit subject: `feat(init): Build an AGE image with pgvector for --graph age`. Stage only the Files owned, with explicit paths. The working tree has untracked files from other agents (`tasks/fleet/`, `tasks/specs/S-CLI-26-*`, `tasks/specs/S-CLI-27-*`, `docs/agent-layout.md`, `docs/plans/`); never stage them.
