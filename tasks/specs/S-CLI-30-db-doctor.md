# S-CLI-30: `mattstack db doctor`

| Field | Value |
|---|---|
| Spec ID | S-CLI-30 |
| Backlog item | GitHub issue #139; `docs/plans/2026-11-25-roadmap.md:84` (Theme 3, `db doctor`). The roadmap is an untracked draft: it is not in git and has no entry in `tasks/todo.md`. |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-30 |
| Depends on | none |
| Conflicts with | S-CLI-32 (`src/mattstack/commands/db.py`: both register a command on `db_app`) |
| Files owned | `src/mattstack/auditors/db_health.py` (new), `src/mattstack/commands/db_doctor.py` (new), `src/mattstack/commands/db.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 3 |
| Max changed lines | 400 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run python scripts/gauntlet.py --gate install`; plus CLI rows A1 to A7 below |
| Acceptance criteria | A1 to A7 (table below) |

## Context and verified citations

### Why not `_docker_psql_command`


`_docker_psql_command` (`src/mattstack/commands/db.py:301-319`) wraps the command in `sh -c 'exec psql ... -d "$1"' sh <dbname>`. Arguments added after the wrapper land in `$2` and later, so `-c <sql>` would be dropped `(unverified: exact trailing-argument behavior; read the function before relying on it)`. It also returns nothing unless compose has a `db` service and docker is on PATH. The doctor uses host `psql` with the DSN instead. Because `--dsn` is required, the docker path is never reached, and a missing `--dsn` is a usage error, not a silent fallback to compose.

### Current state


- `db_app` is defined at `src/mattstack/commands/db.py:25`. `_run` is at `db.py:73`.
- Existing `db` commands reach Postgres through the compose service. This spec adds a direct `--dsn` path that works for any reachable Postgres.

### Size and file length

`src/mattstack/commands/db.py` is 374 lines at `e89fac4`. `scripts/check_file_length.py` caps files at 400 lines. The stop condition below covers overflow.

## Goal and non-goals


Add `mattstack db doctor --dsn <dsn>`, a read-only health report for a Postgres database. It runs a fixed set of catalog and `pg_stat_*` queries through `psql` and reports each check as `pass`, `warn` or `fail`. It exits 1 if any check fails, and exits 2 on a usage error (missing `--dsn`).

**Non-goals:** No Docker exec path. No writes to the database. No `db tune` or other Theme 3 items. No CI test against a live database.

## Implementation steps

### Credentials: never on the command line


The DSN contains the password, and `ps` shows every argument of a running process to other users on the same host. So the DSN must not reach `psql`'s argv.

- Parse `--dsn` in Python with `urllib.parse.urlsplit`. Get host, port, user, password and database name.
- Pass them to the `psql` subprocess only through its environment: `PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE` and `PGPASSWORD`. Build the environment as `{**os.environ, ...}` for each call.
- The `psql` argv contains only `-X -A -t -F <tab> -v ON_ERROR_STOP=1 -c <sql>`. It never contains the DSN, the password, or the database name.
- Redact the password in every printed string. The redacted DSN is `postgresql://user:***@host`, and it is the only form that goes into the JSON `target` field.

This is a deliberate departure from `db_target.py`. Its comment at line 16 says it emits "engine, host, port, and name only: never credentials", so the doctor does not call it. The doctor reads the DSN itself and keeps credentials in the environment.

### Design


`db_health.py` (core, no I/O):
- `class CheckStatus(StrEnum)`: `pass`, `warn`, `fail`.
- `@dataclass(frozen=True) class CheckResult`: `name: str`, `status: CheckStatus`, `detail: str`.
- A `CHECKS` tuple of `(name, sql)` for each query, plus `def evaluate(name: str, rows: list[list[str]], *, max_connections: int | None = None) -> CheckResult`. `evaluate` is pure: given the rows, it returns the status.
- Thresholds: connections warn at 80% of `max_connections`, fail at 95%. A long transaction (active or idle in transaction, older than 5 minutes) gives warn. A dead-tuple ratio over 20% on tables with at least 1000 live rows gives warn.

`db_doctor.py` (command logic):
- `run_doctor(dsn: str, *, json_output: bool) -> int`. Find `psql` with `shutil.which`. If it is missing, return 1 and report a `fail` for `psql`.
- For each check, run `psql` with the environment above, `subprocess.run(..., capture_output=True, text=True, timeout=30)`, and `PGOPTIONS="-c default_transaction_read_only=on"` so the session is read-only. Add `# nosec` with a reason, matching `db.py`.
- The `version` check runs first. If it fails, stop and return 1.
- Output: a text table (`Check | Status | Detail`) by default, or JSON with `{"target": <redacted>, "checks": [{"name", "status", "detail"}], "summary": {"pass", "warn", "fail"}}` when `--json` is set.

Checks, in order:

| Name | Source | Result |
|---|---|---|
| `version` | `SELECT current_setting('server_version_num'), current_setting('max_connections')` | fails if the query fails; warns if below 130000 |
| `connections` | `SELECT count(*) FROM pg_stat_activity` against `max_connections` | warn at 80%, fail at 95% |
| `long-transactions` | `pg_stat_activity` where `xact_start` is older than 5 minutes | warn if any |
| `unindexed-fks` | foreign keys in `pg_constraint` with no index whose leading columns match | warn, list up to 5 |
| `unused-indexes` | `pg_stat_user_indexes` with `idx_scan = 0`, excluding unique and primary indexes | warn, list up to 5 |
| `duplicate-indexes` | indexes on one table with identical `indkey`, expressions and predicate | warn |
| `dead-tuples` | `pg_stat_user_tables` with at least 1000 live rows and dead rows over 20% of live rows | warn, labeled as a bloat proxy, not `pgstattuple` |
| `top-queries` | `pg_extension` for `pg_stat_statements`; if present, the top 10 from `pg_stat_statements` by `total_exec_time` | warn if not installed; never fail; pass with the top list otherwise |

The SQL above is written from memory of the Postgres catalogs `(unverified)`. Check each query against a real Postgres before merging. The acceptance rows use a shim, so they test the logic and output format, not the SQL.

## Machine-checkable acceptance


Step A0 writes a `psql` shim to `$S/psql`. The shim records its argv and whether `PGPASSWORD` was set, and answers only the queries it recognizes. Each acceptance row prepends `$S` to `PATH`.

```bash
S="$(mktemp -d)"
cat > "$S/psql" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$S_LOG_DIR/argv.log"
printf 'PGPASSWORD=%s\n' "${PGPASSWORD:+set}" >> "$S_LOG_DIR/env.log"
sql=""
while [ $# -gt 0 ]; do
  if [ "$1" = "-c" ]; then sql="$2"; fi
  shift
done
case "$sql" in
  *server_version_num*) printf '150004\t%s\n' "${FAKE_MAX:-100}" ;;
  *xact_start*) printf '0\n' ;;
  *"FROM pg_stat_activity"*) printf '%s\n' "${FAKE_CONN:-5}" ;;
  *"FROM pg_extension"*) [ "${FAKE_PGSS:-1}" = 1 ] && printf '1\n' ;;
  *"FROM pg_stat_statements ORDER BY"*) printf 'SELECT 1\t3\t0.5\n' ;;
esac
exit 0
SH
chmod +x "$S/psql"
export S_LOG_DIR="$S"
```

Acceptance uses this DSN: `postgresql://app:s3cret@localhost:5432/app`. The string `s3cret` is the password the checks must keep out of argv and output.

| # | Command | Expected | Assertion |
|---|---|---|---|
| A1 | `PATH="$S:$PATH" uv run mattstack db doctor --dsn postgresql://app:s3cret@localhost:5432/app --json` | exit 0 | check names, in order, are `version, connections, long-transactions, unindexed-fks, unused-indexes, duplicate-indexes, dead-tuples, top-queries`; no status is `fail` |
| A2 | `FAKE_CONN=10 FAKE_MAX=10 PATH="$S:$PATH" uv run mattstack db doctor --dsn postgresql://app:s3cret@localhost:5432/app --json` | exit 1 | the `connections` check has status `fail` |
| A3 | `FAKE_PGSS=0 PATH="$S:$PATH" uv run mattstack db doctor --dsn postgresql://app:s3cret@localhost:5432/app --json` | exit 0 | the `top-queries` check has status `warn` |
| A4 | the A1 command, text output (no `--json`), and the same with `--json` | exit 0 | neither the text output nor the JSON contains `s3cret`; `"$S/argv.log"` contains no `s3cret` and no `postgresql://`; `"$S/env.log"` contains `PGPASSWORD=set` |
| A5 | `PATH="$S:$PATH" uv run mattstack db doctor --json` (no `--dsn`) | exit 2 | usage error; no `psql` call is recorded in `"$S/argv.log"` for this run |
| A6 | `uv run mattstack db doctor --help` | exit 0 | help contains `--dsn` and `--json` |
| A7 | `uv run mattstack db --help` | exit 0 | help lists `doctor` |

## Stop conditions and PR evidence

### Stop conditions


- If `db.py` is over the file-length cap after adding the command, stop. Move the registration into `db_doctor.py` and report. Do not split `db.py` silently.
- If A4 finds the password in argv, output or the JSON, stop. Redaction and env-only credentials are hard requirements.
- Commit nothing when stopped; report the exact discrepancy.

### Evidence for the PR


Paste the A1-A7 results and the gate results. Note that the SQL has not been run against a real Postgres `(unverified)`.

PR body: spec ID, base `e89fac4` and head SHA, owned files with changed-line counts, the A1 to A7 results, and the output of each verification command. Commit subject: `feat(db): Add db doctor command`. Stage only Files owned, with explicit paths.
