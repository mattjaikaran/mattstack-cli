# S-CLI-33: `mattstack audit --type scale` flags single-process production blockers

| Field | Value |
|---|---|
| Spec ID | S-CLI-33 |
| Backlog item | `docs/plans/2026-11-25-roadmap.md` (section 4, "Scaling", scale audit item) |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-33 |
| Depends on | none |
| Conflicts with | S-CLI-29 (`src/mattstack/auditors/base.py`, `src/mattstack/commands/audit.py`); S-CLI-38 (`src/mattstack/auditors/base.py`, `src/mattstack/commands/audit.py`); S-CLI-40 (`src/mattstack/commands/audit.py`) |
| Files owned | `src/mattstack/auditors/scale.py` (new), `src/mattstack/auditors/base.py` (one enum member), `src/mattstack/commands/audit.py` (one `AUDITOR_CLASSES` entry) |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 15 |
| Max changed lines | 800 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install`; plus acceptance rows A1-A6 below |
| Acceptance criteria | A1 fresh scaffold has no ERROR; A2 bad fixture fires four rules; A3 test-only settings fire nothing; A4 no prod settings gives one INFO; A5 `--json` output has no ERROR; A6 default `audit` run includes the scale auditor and no ERROR |

## Context and verified citations

Base commit `e89fac4`. Items marked `(unverified)` must be confirmed by the executor before use. A failed confirmation is a stop condition.

- `src/mattstack/auditors/base.py:17-23` `AuditType` enum. The new member `SCALE = "scale"` goes after line 23.
- `src/mattstack/auditors/base.py:56-62` `run_all` returns True when `audit_types is None`, and `should_run` returns `run_all or audit_type in (audit_types or [])`. **Verified.** Consequence: once registered, the scale auditor runs on every plain `mattstack audit`, including the gauntlet recipe that runs `mattstack audit --no-todo` (verified in the generated root justfile source under `src/mattstack/`). Every finding this auditor emits must therefore be WARNING or INFO. ERROR is forbidden.
- `src/mattstack/commands/audit.py:150` `error_count = sum(1 for f in report.findings if f.severity == Severity.ERROR)`. **Verified.** Only ERROR findings affect the exit path, so WARNING findings do not change any existing exit status.
- `src/mattstack/commands/audit.py:37-44` `AUDITOR_CLASSES` mapping. Add one entry for `AuditType.SCALE`.
- The audit command's type option: `(unverified)` the option name (`--type`) and its handling of comma lists. Confirm with `uv run mattstack audit --help`.
- Architecture: `auditors/` is a core layer and must not import from `commands/` (`scripts/check_architecture.py:7,130-134`). **Verified** from the prior pass. Therefore `auditors/scale.py` must NOT import `settings_texts` from `commands/codegen/backend_layout.py:137`. The module owns its own file discovery and reads raw text. It may use `stack_detection.settings_module_from_manage` (core) if it needs the module name.
- `settings_texts` strips comments with `#.*` and reads every settings file. The scale auditor does NOT reuse it. Comment handling is per-line: skip any line whose first non-space character is `#`. The rules do not depend on comments.

## Goal and non-goals

Goal: a new auditor, `scale`, reports settings and layout patterns that block running more than one web process. Every check is WARNING, except the no-prod-settings case, which is INFO.

Rules (every rule ID is the constant shown; the executor copies the strings exactly):

- R1 `scale.local_mem_cache`: production settings select `django.core.cache.backends.locmem.LocMemCache`. Each process has its own cache, so cache state diverges across processes.
- R2 `scale.file_sessions`: production settings set `SESSION_ENGINE` to `django.contrib.sessions.backends.file`. Sessions live on one machine's disk.
- R3 `scale.local_media`: production settings set `MEDIA_ROOT` and do not reference an S3 storage backend (`storages.backends.s3boto3`, `(unverified)`: the exact backend string the boilerplate uses; confirm in `~/dev/boilerplates/django-ninja-boilerplate` on `origin/main`).
- R4 `scale.in_process_scheduler`: any backend `.py` file (excluding `tests/` and `migrations/`) imports `apscheduler`, `schedule`, or uses `BackgroundScheduler`. Each process would run its own copy of every job.
- R5 `scale.no_health_route`: no backend `urls*.py` or api module contains the string `health`. Load balancers need a health route. WARNING.

Non-goals:
- No ERROR findings. No change to exit codes of existing audits.
- No `CONN_MAX_AGE` rule. The ninja boilerplate hardcodes `CONN_MAX_AGE: 0` on purpose (`api/settings/common.py:250`, `origin/main`), and the pool replaces it, so a `CONN_MAX_AGE` check would be a false positive on a fresh scaffold.
- No DB pool rule. Pool settings are S-CLI-34's concern.
- No changes under `tests/`. No pytest.

## Settings discovery (exact rule)

- Production settings files are matched by glob against the project's backend directory: `backend/**/settings/prod*.py` and `backend/**/settings/production*.py`. Only these files are checked by R1-R3.
- If no production settings file exists, the auditor emits ONE INFO finding with rule `scale.no_prod_settings` and skips R1-R3. It does not fall back to `settings.py`, because `settings.py` is usually a dev configuration.
- R4 and R5 scan backend files, not settings files.

## Implementation steps

1. `auditors/base.py`: add `SCALE = "scale"` to `AuditType` after line 23.
2. `auditors/scale.py` (new): a class implementing the existing auditor interface (`(unverified)`: the base-class name and method signature in `auditors/base.py`; the executor copies an existing auditor such as the one at `auditors/` for the signature). Implements discovery, R1-R5, and `scale.no_prod_settings`. Every finding uses `Severity.WARNING`, except `scale.no_prod_settings`, which uses `Severity.INFO`.
3. `commands/audit.py`: add `AuditType.SCALE: ScaleAuditor` to `AUDITOR_CLASSES`.
4. Run the verification commands once at the end. Do not add tests to `tests/`.

## Machine-checkable acceptance

Each row runs from the repo root. `$TMP` is a fresh `mktemp -d`. Fixtures are built by writing files into `$TMP` with `printf` or `cat <<'EOF'`.

Rule IDs in the output are the strings above. Assertions are on stdout text, because the JSON shape is `(unverified)`.

| ID | Cwd | Exact command | Expected exit/status | Exact output or assertion |
|---|---|---|---|---|
| A1 | repo root | `uv run mattstack init "$TMP/fresh" --preset starter-fullstack >/dev/null 2>&1; uv run mattstack audit --type scale "$TMP/fresh" > "$TMP/a1.out" 2>&1; echo "exit=$?"; ! grep -q 'ERROR' "$TMP/a1.out" && echo no-error` | `exit=0` or `exit=` with warnings only, then `no-error` | A fresh scaffold has no ERROR finding from the scale auditor. Warnings are allowed, because the boilerplate may still fire R5 or R1. Init flags are `(unverified)`: confirm with `uv run mattstack init --help`. |
| A2 | repo root | `mkdir -p "$TMP/bad/backend/config/settings" && cd "$TMP/bad" && printf 'CACHES={"default":{"BACKEND":"django.core.cache.backends.locmem.LocMemCache"}}\nSESSION_ENGINE="django.contrib.sessions.backends.file"\nMEDIA_ROOT="/srv/media"\n' > backend/config/settings/prod.py && printf 'from apscheduler.schedulers.background import BackgroundScheduler\n' > backend/config/jobs.py && cd - >/dev/null && uv run mattstack audit --type scale "$TMP/bad" > "$TMP/a2.out" 2>&1; for r in scale.local_mem_cache scale.file_sessions scale.local_media scale.in_process_scheduler; do grep -c "$r" "$TMP/a2.out"; done` | each count `1` or more | Four lines, each at least 1: R1, R2, R3, R4. R5 also fires here (no `health` route), which is fine. |
| A3 | repo root | `mkdir -p "$TMP/t/backend/config/settings" && printf 'CACHES={"default":{"BACKEND":"django.core.cache.backends.locmem.LocMemCache"}}\n' > "$TMP/t/backend/config/settings/test.py" && uv run mattstack audit --type scale "$TMP/t" > "$TMP/a3.out" 2>&1; grep -c 'scale.local_mem_cache' "$TMP/a3.out"` | `0` | Test settings are not checked. `scale.no_prod_settings` may appear, that is fine. |
| A4 | repo root | `mkdir -p "$TMP/np/backend/config/settings" && printf 'DEBUG=True\n' > "$TMP/np/backend/config/settings/dev.py" && uv run mattstack audit --type scale "$TMP/np" > "$TMP/a4.out" 2>&1; grep -c 'scale.no_prod_settings' "$TMP/a4.out"; grep -c 'INFO' "$TMP/a4.out"` | `1` then `1` or more | Exactly one `scale.no_prod_settings`, emitted as INFO. |
| A5 | repo root | `uv run mattstack audit --type scale "$TMP/bad" --json > "$TMP/a5.json" 2>/dev/null; uv run python -c 'import sys; t=open(sys.argv[1]).read(); assert "scale.local_mem_cache" in t, "no finding"; assert "\"ERROR\"" not in t and "\"error\"" not in t, "error severity present"; print("A5 ok")' "$TMP/a5.json"` | exit 0, stdout `A5 ok` | `--json` output contains the findings and no error-severity marker. `(unverified)`: JSON severity key casing; the executor checks the actual output and adjusts the two literal strings only if the shape differs. |
| A6 | repo root | `uv run mattstack audit "$TMP/fresh" > "$TMP/a6.out" 2>&1; grep -c 'scale' "$TMP/a6.out"; ! grep -q 'ERROR' "$TMP/a6.out" && echo no-error` | count `1` or more, then `no-error` | A plain `audit` run includes the scale auditor (the count is at least 1), and the fresh scaffold has no ERROR from it. Other auditors may report errors; this row checks only the scale auditor's contribution, so the executor compares against the base-commit output of `audit` on the same fixture and confirms the ERROR set is unchanged. |

## Stop conditions and PR evidence

Stop and report if any of these happen:
- A citation in this spec no longer matches at the base commit. Re-verify with `sed -n` before continuing.
- A rule string cannot be checked without importing from `commands/`. Stop; do not add the import (architecture rule).
- A fresh scaffold produces an ERROR from the scale auditor. Downgrade the rule to WARNING and report; never leave an ERROR.
- A2 fires fewer than four rules on the bad fixture. Fix the rule, not the fixture.

PR evidence: stdout and exit codes of A1-A6, plus the output of each verification command.
