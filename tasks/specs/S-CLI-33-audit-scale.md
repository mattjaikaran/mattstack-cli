# S-CLI-33: `mattstack audit --type scale` flags single-process production blockers

| Field | Value |
|---|---|
| Spec ID | S-CLI-33 |
| Backlog item | `docs/plans/2026-11-25-roadmap.md:90-99` (section 4, "Scaling: vertical and horizontal", audit item) |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-33 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `src/mattstack/auditors/scale.py` (new), `src/mattstack/auditors/base.py` (one enum value), `src/mattstack/commands/audit.py` (one dict entry) |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 15 |
| Max changed lines | 800 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install`; plus acceptance rows A1-A5 below |
| Acceptance criteria | A1; A2; A3; A4; A5 (table below) |

## Context and verified citations

Base commit `e89fac4`. Line numbers were read at that commit.

- `src/mattstack/auditors/base.py:11` `class Severity`. `:17` `class AuditType(StrEnum)`, with `TYPES = "types"` at `:18` through `VULNERABILITIES = "vulnerabilities"` at `:23`. Add `SCALE = "scale"` after `:23`.
- `src/mattstack/auditors/base.py:47-48` `AuditConfig.project_path: Path`; `:55` `min_severity`. `BaseAuditor.__init__(self, config)` at `:70`. `add_finding(severity, file, line, message, suggestion)` and `_rel` are on the base class (signatures read earlier; the executor confirms the exact keyword names with `sed -n 70,120p`).
- `src/mattstack/commands/audit.py:37-44` `AUDITOR_CLASSES` dict. Add `AuditType.SCALE: ScaleAuditor`. `:47` `run_audit`. `:122` loop `for audit_type, auditor_cls in AUDITOR_CLASSES.items()`. Without `--type`, all auditors run. The default run includes scale after this change, so its findings must be WARNING and must not change the exit code. `typer.Exit(code=1)` is raised at `:69`, `:88`, `:102`, `:200`, `:222` (the executor confirms none of these is triggered by WARNING-only findings).
- `src/mattstack/auditors/types.py` (62 lines) is the pattern for a small auditor.
- `src/mattstack/config.py:330-331` `ProjectConfig.backend_dir` returns `self.path / "backend"`. Audit has no ProjectConfig, so the auditor uses `self.config.project_path / "backend"` (same convention; unverified that every auditor does the same).
- Architecture: `scripts/check_architecture.py:130-134` (core modules must not import `commands/`). The scale auditor must not import anything from `commands/`. `scripts/check_file_length.py:15` `MAX_LINES = 400`.
- Django-ninja boilerplate (`~/dev/boilerplates/django-ninja-boilerplate`, `origin/main`), read earlier:
  - `api/settings/common.py:250` `"CONN_MAX_AGE": 0`. Lines 205-211 explain why it must stay 0 with the psycopg pool.
  - `api/settings/common.py:458-481` `CACHES`. Backends are `django_vcache.backend.ValkeyCache` (vcache, default), `django_valkey.cache.ValkeyCache` (valkey), and `django.core.cache.backends.redis.RedisCache` (redis). All are shared caches, so they are not LocMemCache.
  - `api/settings/common.py:490` session engine `django.contrib.sessions.backends.cache`.
  - `api/settings/test.py:53` LocMemCache, used by tests only. Must not be flagged.
  - `api/settings/common.py:367-372` S3 storage branch, guarded by production and `AWS_STORAGE_BUCKET_NAME`. The literal text `storages.backends.s3boto3` used by the R3 check is `(unverified)`. The executor confirms it with `grep -n s3 api/settings/common.py` before relying on it.
  - `api/healthcheck.py:46` `@api_controller("/health", tags=["Health"])`, mounted at `/api/health`.
  - Production settings file: `api/settings/prod.py` (exists on the boilerplate; the executor confirms its path).
- Delta rule (parent): the boilerplate already ships deployment manifests (deploy/k3s and Helm, `(unverified)`). This spec adds only the CLI audit rules. It does not change those manifests.

## Goal and non-goals

Goal: `mattstack audit --type scale` reads production settings and backend code, and reports WARNING findings for patterns that break when the app runs with more than one process or replica:

- R1 `LocMemCache` configured in a production settings file. Per-process cache.
- R2 `SESSION_ENGINE` set to `django.contrib.sessions.backends.file`. Per-host sessions.
- R3 `MEDIA_ROOT` set in production with no S3 or other remote storage string in the same settings file. Local uploads.
- R4 An in-process scheduler import (`apscheduler`, `BackgroundScheduler`, `schedule`) in `backend/**/*.py`. Each replica would run its own copy.
- R5 No `/health` route found in `backend/**/*.py`. Load balancers need one.

Each finding is WARNING. Settings with `CONN_MAX_AGE = 0`, `CACHES` pointing at a shared backend, or `SESSION_ENGINE` set to the cache or db backend must produce no finding.

Non-goals:
- No ERROR severity. No change to exit codes.
- No auto-fix (`--fix` is not used).
- No live checks (`--live` is not used).
- No changes to the boilerplate.
- No tests under `tests/`. No pytest. Proof comes from the acceptance rows.

## Implementation steps

1. Add `SCALE = "scale"` to `AuditType` in `src/mattstack/auditors/base.py` after line 23.
2. Create `src/mattstack/auditors/scale.py` with `class ScaleAuditor(BaseAuditor)` and `run() -> list[AuditFinding]`:
   - Find production settings: `backend/**/settings/prod*.py` and `backend/**/settings/production*.py` (glob, sorted). If none exist, add one INFO finding ("no production settings module found; settings rules skipped") and skip R1-R3.
   - R1-R3 are text checks on each production settings file: `LocMemCache` in `CACHES`; `sessions.backends.file`; `MEDIA_ROOT` with no `storages` or `S3` substring in the same file.
   - R4 and R5 scan `backend/**/*.py`, skipping `tests/`, `migrations/`, and `.venv`.
   - R1 must not flag `test.py`. Only production files are read.
3. Register `AuditType.SCALE: ScaleAuditor` in `AUDITOR_CLASSES` (`src/mattstack/commands/audit.py:37-44`) and add the import.
4. Keep `scale.py` under 400 lines.
5. Run the verification commands once at the end. Do not add tests to `tests/`.

## Acceptance criteria

Each row runs the CLI from the repo root. `$TMP` is a fresh `mktemp -d`. The fixtures are built with heredocs in the row. JSON assertions search the output text rather than a fixed schema, because the exact JSON shape is `(unverified)`.

| ID | Cwd | Exact command | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `mkdir -p "$TMP/clean/backend/api/settings" && printf 'CONN_MAX_AGE = 0\nCACHES = {"default": {"BACKEND": "django_valkey.cache.ValkeyCache"}}\nSESSION_ENGINE = "django.contrib.sessions.backends.cache"\n' > "$TMP/clean/backend/api/settings/prod.py" && uv run mattstack audit --type scale "$TMP/clean" --json > "$TMP/clean.json"; echo "exit=$?"` then `uv run python -c 'import sys; t=open(sys.argv[1]).read(); bad=[k for k in ["LocMemCache","sessions.backends.file","MEDIA_ROOT"] if k in t]; assert not bad, bad; print("A1 ok")' "$TMP/clean.json"` | `exit=0`, then stdout `A1 ok` | No finding is reported for the clean fixture. |
| A2 | repo root | `mkdir -p "$TMP/bad/backend/api/settings" "$TMP/bad/backend/jobs" && printf 'CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}\nSESSION_ENGINE = "django.contrib.sessions.backends.file"\nMEDIA_ROOT = "/srv/media"\n' > "$TMP/bad/backend/api/settings/prod.py" && printf 'from apscheduler.schedulers.background import BackgroundScheduler\n' > "$TMP/bad/backend/jobs/sched.py" && uv run mattstack audit --type scale "$TMP/bad" --json > "$TMP/bad.json"; echo "exit=$?"` then `uv run python -c 'import sys; t=open(sys.argv[1]).read(); missing=[k for k in ["LocMemCache","sessions.backends.file","MEDIA_ROOT","apscheduler"] if k not in t]; assert not missing, missing; print("A2 ok")' "$TMP/bad.json"` | `exit=0` (warnings do not change exit), then stdout `A2 ok` | Each of the four rule triggers appears in the output. |
| A3 | repo root | `mkdir -p "$TMP/testonly/backend/api/settings" && printf 'CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}\n' > "$TMP/testonly/backend/api/settings/test.py" && uv run mattstack audit --type scale "$TMP/testonly" --json > "$TMP/testonly.json"; echo "exit=$?"` | `exit=0` | `uv run python -c 'import sys; t=open(sys.argv[1]).read(); assert "LocMemCache" not in t, t; print("A3 ok")' "$TMP/testonly.json"` prints `A3 ok`. LocMemCache in `test.py` is not flagged. |
| A4 | repo root | `mkdir -p "$TMP/noprod/backend/api" && printf 'x = 1\n' > "$TMP/noprod/backend/api/settings.py" && uv run mattstack audit --type scale "$TMP/noprod" --json > "$TMP/noprod.json"; echo "exit=$?"` | `exit=0` | `uv run python -c 'import sys; t=open(sys.argv[1]).read(); assert "no production settings" in t, t; print("A4 ok")' "$TMP/noprod.json"` prints `A4 ok`. |
| A5 | repo root | `uv run mattstack audit --type scale --help; echo "exit=$?"` then `uv run mattstack audit --type nosuchtype "$TMP/clean"; echo "exit=$?"` | Help exits 0. Unknown type exits non-zero (existing behaviour). | Help output lists `scale` as a type or accepts `--type`. The unknown-type run prints an error. |

## Stop conditions and PR evidence

Stop and report, without editing other files, if any of these happen:
- A citation in this spec no longer matches at the base commit. Re-verify it with `sed -n` before continuing.
- Any WARNING-only run changes the exit code of `audit`. Check `audit.py:69`, `:88`, `:102`, `:200`, `:222` first.
- The clean fixture (A1) produces a finding. That is a false positive. Do not loosen the rule to make A1 pass without reporting it.
- The R3 string check (`storages.backends.s3boto3`) is not present in the boilerplate. Report it; do not invent a new string.
- `scale.py` would exceed 400 lines.

PR evidence: stdout and exit codes of A1-A5, plus the output of each verification command.
