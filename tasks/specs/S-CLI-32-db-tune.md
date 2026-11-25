# S-CLI-32: `mattstack db tune` prints pgtune web settings from memory and CPU

| Field | Value |
|---|---|
| Spec ID | S-CLI-32 |
| Backlog item | `docs/plans/2026-11-25-roadmap.md:90-99` (section 4, "Scaling: vertical and horizontal", item `db tune --memory 8GB --cpus 4`) |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-32 |
| Depends on | none |
| Conflicts with | S-CLI-30 (`src/mattstack/commands/db.py`) |
| Files owned | `src/mattstack/pg_tuning.py` (new), `src/mattstack/commands/db_tune.py` (new), `src/mattstack/commands/db.py` (register one command) |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | S |
| Max files | 8 |
| Max changed lines | 300 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install`; plus acceptance rows A1-A6 below |
| Acceptance criteria | A1; A2; A3; A4; A5; A6 (table below) |

## Context and verified citations

Base commit `e89fac4`. Line numbers were read at that commit. The pgtune source was read from `le0pard/pgtune` at commit `ce7a7325f6cc2a7b72062736ccc5971603c79974` (master HEAD at fetch time, 2026-11-25). Every pgtune citation below refers to this commit.

- `src/mattstack/commands/db.py:27` defines `db_app = typer.Typer(name="db", ...)`. It is the Django `db` group, lazy-loaded by `src/mattstack/cli.py:41` (`LazyGroupSpec("mattstack.commands.db", "db_app", ...)`). The file is 374 lines, so only a few lines can be added there (400-line cap, `scripts/check_file_length.py:15`, `MAX_LINES = 400`).
- `src/mattstack/config.py` already has no pgtune concept. There is no existing memory or CPU input anywhere in `src/`.
- Architecture rule (`scripts/check_architecture.py:130-134`): core modules must not import `commands/`. `pg_tuning.py` is pure and imports nothing from `commands/`. `commands/db_tune.py` may import it.
- pgtune source, `src/features/configuration/configurationSelectors.js` (fetched 2026-11-25):
  - shared_buffers = floor(RAM/4) for web, rounded down to whole MB (`selectSharedBuffers`, lines 98-108; `roundDownToMb` at lines 57-59).
  - effective_cache_size = floor(RAM x 3/4) for web (lines 123-133).
  - maintenance_work_mem = floor(RAM/16) for web, capped at 8 GB on Linux (lines 142-167).
  - wal_buffers = clamp(floor(shared_buffers / 8 / 32) x 8 kB, 64 kB, 16 MB) (lines 203-209).
  - checkpoint_completion_target = 0.9 when PostgreSQL < 14, otherwise not set (lines 196-200).
  - min_wal_size = 1 GB and max_wal_size = 4 GB for web (lines 171-190).
  - random_page_cost: 1.1 if the DB fits in RAM; 4 if HDD; otherwise 1.1 for web (lines 218-241).
  - effective_io_concurrency: Linux only; HDD 2, SSD 200, SAN 300, NVMe 1000 (lines 244-259). maintenance_io_concurrency mirrors it for PostgreSQL >= 13 (lines 261-266).
  - Parallel settings are emitted only when cpus >= 4 (lines 271-273). per_gather = ceil(workers/2), capped at 4. max_worker_processes = max(workers, 8). max_parallel_workers = workers. max_parallel_maintenance_workers = ceil(workers/2), capped at 4 (PostgreSQL >= 11) (lines 271-318).
  - Defaults when no CPU is given: max_connections 100, max_worker_processes 8, max_parallel_workers 8 (`DEFAULT_DB_SETTINGS`, lines 28-36).
  - max_connections = max(100, min(200 for web, floor((RAM - shared_buffers) / (4 MB x 3)) - parallel_workers)) unless the user gives one (lines 340-368).
  - work_mem = floor((RAM - shared_buffers) / ((max_connections + parallel_workers) x 3)), floored to 4 MB, rounded down to whole MB. Web has no size multiplier (lines 372-420). `parallel_workers` is the emitted `max_parallel_workers` when present, else the default 8 (`selectParallelWorkersForWorkMem`, lines 325-336).
- pgtune defaults (`src/features/configuration/configurationParams.js` lines 13-22 and `constants.js` line 2): dbType web, osType linux, hdType ssd, dbSize mid_ram, and DEFAULT_DB_VERSION 19.
- Golden snapshots checked against the formulas above, as `src/features/configuration/__tests__/__snapshots__/configurations/`:
  - `pg10-linux-web-2gb-ssd.conf`: shared_buffers 512MB, effective_cache_size 1536MB, maintenance_work_mem 128MB, wal_buffers 16MB, random_page_cost 1.1, effective_io_concurrency 200, work_mem 4MB, max_connections 120, checkpoint_completion_target 0.9, min_wal_size 1GB, max_wal_size 4GB.
  - `pg12-linux-web-4gb-2cpu-san-2000-connections.conf`: max_connections 2000, shared_buffers 1GB, effective_cache_size 3GB, maintenance_work_mem 256MB, wal_buffers 16MB, random_page_cost 1.1, effective_io_concurrency 300, work_mem 4MB, checkpoint_completion_target 0.9, min_wal_size 1GB, max_wal_size 4GB. No parallel keys (2 CPUs).
  - Note: the snapshots also contain keys that are out of scope here (`wal_compression`, `vacuum_cost_page_miss`, `autovacuum_vacuum_cost_delay`, `jit`). Do not emit them.
- The brief's wording "work_mem = (RAM - shared_buffers) / (3 x max_connections)" is simplified. The source divides by `(max_connections + parallel_workers) x 3`. Use the source.
- The brief's maintenance_work_mem cap of 2 GB is wrong for Linux. The source caps it at 8 GB (lines 142-167). Use 8 GB.

## Goal and non-goals

Goal: `mattstack db tune` prints PostgreSQL settings for a web workload, computed with the pgtune formulas above, from `--memory` and `--cpus`. It also has `--json` for machine checks and `--output FILE` to write a `postgresql.conf` fragment.

Non-goals:
- No other pgtune workloads (oltp, dw, desktop, mixed). Only `web`.
- No macOS or Windows settings. The output always uses Linux rules.
- No huge_pages, jit, autovacuum, or wal_compression keys.
- No compose or k8s wiring. The command does not edit `docker-compose.yml`. Mounting the file is a follow-up.
- No tests under `tests/`. No pytest. Proof comes from the acceptance CLI rows.

## Implementation steps

1. Create `src/mattstack/pg_tuning.py`. Keep it pure: a dataclass `TuningInput(memory_kb, cpus | None, disk, pg_version, db_size, connections | None)` and a function `compute_web_settings(inp) -> dict[str, str]`. Port the formulas from the Context section, in kB internally. Render each value as `GB` when it is a multiple of 1048576 kB, `MB` when it is a multiple of 1024 kB, otherwise `kB`. Apply the version gates from the Context section (checkpoint_completion_target < 14; maintenance_io_concurrency >= 13; max_parallel_workers >= 10; max_parallel_maintenance_workers >= 11).
2. Create `src/mattstack/commands/db_tune.py` with a Typer function `tune`. Options:
   - `--memory` (required). Accepts `^\d+(MB|GB)$`, case-insensitive. Any other value raises `typer.BadParameter` (exit 2).
   - `--cpus` (optional int). If absent, emit no parallel keys and use default parallel worker count 8 in the formulas.
   - `--disk` with choices `ssd|hdd|san|nvme`. Default `ssd`.
   - `--db-size` with choices `less_ram|mid_ram|greater_ram`. Default `mid_ram`. `less_ram` multiplies work_mem by 1.3; `greater_ram` by 0.9 (source lines 390-400).
   - `--pg-version` int, default 19, must be 10-19 (`BadParameter` otherwise).
   - `--connections` int, optional.
   - `--json` prints `{"settings": {...}}`.
   - `--output PATH` writes a `postgresql.conf` fragment with a `#` header line, one `key = value` per line.
   - Default: print the same fragment to stdout.
3. Register it in `src/mattstack/commands/db.py` with one line, e.g. `db_app.command("tune")(tune)`, and one import. Do not reorganise the file.
4. Do not change `docker_compose.py`, `compose_env.py`, or any template.
5. Run the verification commands once at the end. Do not run the formulas in a test file.

## Machine-checkable acceptance

Each row runs the CLI from the repo root. `$TMP` is a fresh `mktemp -d`.

| ID | Cwd | Exact command | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `uv run mattstack db tune --memory 2GB --pg-version 10 --disk ssd --json \| uv run python -c 'import json,sys; s=json.load(sys.stdin)["settings"]; exp={"max_connections":"120","shared_buffers":"512MB","effective_cache_size":"1536MB","maintenance_work_mem":"128MB","checkpoint_completion_target":"0.9","wal_buffers":"16MB","random_page_cost":"1.1","effective_io_concurrency":"200","work_mem":"4MB","min_wal_size":"1GB","max_wal_size":"4GB"}; assert {k:s[k] for k in exp}==exp, s; assert set(s)==set(exp), sorted(s); print("A1 ok")'` | exit 0 | stdout `A1 ok`. This matches `pg10-linux-web-2gb-ssd.conf` for every key it emits. |
| A2 | repo root | `uv run mattstack db tune --memory 4GB --cpus 2 --disk san --connections 2000 --pg-version 12 --json \| uv run python -c 'import json,sys; s=json.load(sys.stdin)["settings"]; exp={"max_connections":"2000","shared_buffers":"1GB","effective_cache_size":"3GB","maintenance_work_mem":"256MB","checkpoint_completion_target":"0.9","wal_buffers":"16MB","random_page_cost":"1.1","effective_io_concurrency":"300","work_mem":"4MB","min_wal_size":"1GB","max_wal_size":"4GB"}; assert {k:s[k] for k in exp}==exp, s; assert set(s)==set(exp), sorted(s); print("A2 ok")'` | exit 0 | stdout `A2 ok`. This matches `pg12-linux-web-4gb-2cpu-san-2000-connections.conf`. With 2 CPUs there are no parallel keys. |
| A3 | repo root | `uv run mattstack db tune --memory 8GB --cpus 4 --disk nvme --pg-version 17 --json \| uv run python -c 'import json,sys; s=json.load(sys.stdin)["settings"]; exp={"shared_buffers":"2GB","effective_cache_size":"6GB","maintenance_work_mem":"512MB","wal_buffers":"16MB","work_mem":"10MB","max_connections":"200","random_page_cost":"1.1","effective_io_concurrency":"1000","maintenance_io_concurrency":"1000","max_worker_processes":"8","max_parallel_workers_per_gather":"2","max_parallel_workers":"4","max_parallel_maintenance_workers":"2","min_wal_size":"1GB","max_wal_size":"4GB"}; assert {k:s[k] for k in exp}==exp, s; assert set(s)==set(exp), sorted(s); print("A3 ok")'` | exit 0 | stdout `A3 ok`. Expected values are derived by hand from the source formulas (no golden file exists for 4 CPUs). `checkpoint_completion_target` and `default_statistics_target` must be absent on PostgreSQL 17 and web. |
| A4 | repo root | `uv run mattstack db tune --memory 8 --pg-version 17; echo "exit=$?"` then `uv run mattstack db tune --memory 8GB --disk floppy; echo "exit=$?"` | Both print `exit=2` | Both print Typer or BadParameter usage errors on stderr. The first mentions `--memory`. The second mentions `floppy`. |
| A5 | repo root | `uv run mattstack db tune --memory 2GB --pg-version 10 --output "$TMP/tuning.conf" && uv run python -c 'import sys,pathlib; lines=[l for l in pathlib.Path(sys.argv[1]).read_text().splitlines() if l and not l.startswith("#")]; assert len(lines)==11, lines; assert all(" = " in l for l in lines); print("A5 ok")' "$TMP/tuning.conf"` | exit 0 | stdout `A5 ok`. The file has at least one `#` header line. |
| A6 | repo root | `uv run mattstack db tune --help \| grep -E -- '--memory\|--cpus\|--json\|--output'` | exit 0 | All four flags appear in help output. Architecture is covered by the verification command `scripts/check_architecture.py`. |

## Stop conditions and PR evidence

Stop and report, without editing other files, if any of these happen:
- A citation in this spec no longer matches at the base commit. Re-verify it with `sed -n` before continuing.
- `src/mattstack/commands/db.py` has a group callback that requires a project. `db tune` must run without a project. Check `db_app.callback`, and stop if one exists that requires `resolve_project`.
- The new file would push `db.py` past 400 lines (`scripts/check_file_length.py`).
- A pgtune formula in the Context section no longer matches the cited source. Re-fetch `le0pard/pgtune` and stop if the change affects A1-A3.
- Any acceptance row fails. Do not change the expected values to make a row pass.

PR evidence: the output of A1-A6 (stdout and exit codes), plus the output of each verification command.
