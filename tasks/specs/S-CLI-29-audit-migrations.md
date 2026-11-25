# S-CLI-29: `mattstack audit --type migrations`

| Field | Value |
|---|---|
| Spec ID | S-CLI-29 |
| Backlog item | GitHub issue #138; `docs/plans/2026-11-25-roadmap.md:80` (Theme 3, `audit migrations`). The roadmap is an untracked draft: it is not in git and has no entry in `tasks/todo.md`. |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-29 |
| Depends on | none |
| Conflicts with | S-CLI-33 (`src/mattstack/auditors/base.py`, `src/mattstack/commands/audit.py`); S-CLI-38 (`src/mattstack/auditors/base.py`, `src/mattstack/commands/audit.py`); S-CLI-40 (`src/mattstack/commands/audit.py`) |
| Files owned | `src/mattstack/auditors/base.py`, `src/mattstack/auditors/migrations.py` (new), `src/mattstack/commands/audit.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 3 |
| Max changed lines | 400 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run python scripts/gauntlet.py --gate install`; `uv run mattstack audit --help`; plus CLI rows A1 to A5 below |
| Acceptance criteria | A1 to A5 (table below) |

## Context and verified citations

### Current state (verified at `e89fac4`)


- `AuditType` is a `StrEnum` in `src/mattstack/auditors/base.py:17-23` with values `types, quality, endpoints, tests, dependencies, vulnerabilities`.
- `AuditConfig.should_run` is at `base.py:61-62`. Today it returns true for every type when `audit_types` is `None`.
- `AUDITOR_CLASSES` is at `src/mattstack/commands/audit.py:37-43`. The run loop is at `audit.py:122-125`.
- The report JSON (`AuditReport.to_dict`, `base.py:139-148`) has keys `auditors_run`, `summary` (`errors`, `warnings`, `info`, `total`) and `findings`. Each finding has a `category` equal to the AuditType value. Severity values are `error`, `warning`, `info` (`base.py:11-14`).
- `just gauntlet` runs `mattstack audit --no-todo` (`root_justfile.py:255`). That run does not include `migrations`, because of the gating below.

## Goal and non-goals


Add a static `migrations` auditor that lints Django migration files for unsafe patterns. It is opt-in: `--type migrations` runs it, and nothing else does.

**Non-goals:** No Django import, no DB access, no subprocess. No suppression comments. No `AlterField` rules. No `--diff` or git-base mode in this slice. No changes to the boilerplate's `scripts/db/check_migrations.py`.

## Implementation steps

### Change


1. `base.py`: add `MIGRATIONS = "migrations"` to `AuditType`. In `should_run`, return true for `MIGRATIONS` only when it is named in `audit_types`. Keep the existing behavior for all other types.
2. `migrations.py` (new): `MigrationsAuditor(BaseAuditor)` with `audit_type = AuditType.MIGRATIONS`. Discover files with `project_path.rglob("migrations/[0-9]*.py")`. Skip any path with a part named `.venv`, `node_modules`, or `__pycache__`. Parse each file with `ast` only. A `SyntaxError` produces one `warning` finding and no rules run for that file.
3. `commands/audit.py`: import the auditor and add `AuditType.MIGRATIONS: MigrationsAuditor` to `AUDITOR_CLASSES`.

### Severity policy (decided)


`--type migrations` scans every migration in the project, including ones already applied in production. A static scan can't tell which files are new, so an ERROR on a deploy-safety rule would fail the run forever on history. The policy is:

- **ERROR** only for the two cases that break the database or the migration graph regardless of history: `no-merge` (merge migrations are banned) and `SM018` (a concurrent index operation without `atomic = False`, which Postgres rejects inside a transaction).
- **WARNING** for every other rule (`SM001`, `SM010`, `SM011`, `SM016`, `SM006`, `SM014`, `SM002`). These are review prompts. They do not change the exit code.

Historical noise is therefore reported as warnings. The exit code is 1 only when a merge or a bad concurrent index exists.

### Rules


Every finding message starts with `[RULE_ID] `. Emit at most one finding per rule per file.

| ID | Trigger | Severity | Source |
|---|---|---|---|
| `no-merge` | File name contains `merge`, or `operations` is empty and `dependencies` lists 2 or more entries for the same app | error | boilerplate `scripts/db/check_migrations.py` (unverified line) |
| `SM018` | File uses `AddIndexConcurrently` or `RemoveIndexConcurrently` and the `Migration` class lacks `atomic = False` | error | django-safe-migrations `add_index.py` (unverified) |
| `SM001` | `AddField` whose field is not `ManyToManyField`, has no `default=` or `db_default=`, and is not `null=True` | warning | django-safe-migrations `add_field.py` (unverified) |
| `SM010` | `AddIndex` (not `AddIndexConcurrently`) on a model not created in the same file | warning | django-safe-migrations `add_index.py` (unverified) |
| `SM011` | `AddConstraint` with `UniqueConstraint` on a model not created in the same file | warning | django-safe-migrations `add_index.py` (unverified) |
| `SM016` | `RunPython` with no reverse (no second positional argument and no `reverse_code=`). `RunPython.noop` counts as explicit. | warning | django-safe-migrations reports info; warning is a deliberate deviation |
| `SM006` | `RenameField` | warning | two-deploy rule (unverified) |
| `SM014` | `RenameModel` | warning | two-deploy rule (unverified) |
| `SM002` | `RemoveField` | warning | two-deploy rule (unverified) |

"Model not created in the same file" compares lowercased `model_name` against the names in `CreateModel` calls in that file. If the model is created there, SM010 and SM011 do not fire.

The checks are approximate by design. They do not resolve imports or the migration graph.

## Machine-checkable acceptance


Step A0 writes this fixture. Each row below reads `$T`, so run A0 first and keep `$T` set. Each `migrations/` file holds one operation unless noted.

```bash
T="$(mktemp -d)"
M="$T/backend/core/migrations"
mkdir -p "$M"
# 0001: CreateModel Todo (no finding)
cat > "$M/0001_initial.py" <<'PY'
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Todo",
            fields=[("id", models.BigAutoField(primary_key=True)), ("title", models.CharField(max_length=80))],
        ),
    ]
PY
# 0002: AddField without default, NOT NULL -> SM001 warning
cat > "$M/0002_todo_priority.py" <<'PY'
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.AddField(model_name="todo", name="priority", field=models.IntegerField())]
PY
# 0003: merge migration -> no-merge error
cat > "$M/0003_merge_0002_0001.py" <<'PY'
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial"), ("core", "0002_todo_priority")]
    operations = []
PY
# 0004: AddIndex on existing table, not concurrent -> SM010 warning
cat > "$M/0004_todo_index.py" <<'PY'
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("core", "0003_merge_0002_0001")]
    operations = [migrations.AddIndex(model_name="todo", index=models.Index(fields=["title"], name="todo_title_idx"))]
PY
# 0005: RunPython without reverse -> SM016 warning
cat > "$M/0005_backfill.py" <<'PY'
from django.db import migrations

def fill(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [("core", "0004_todo_index")]
    operations = [migrations.RunPython(fill)]
PY
# 0006: RenameField + RemoveField -> SM006 warning, SM002 warning
cat > "$M/0006_rename_remove.py" <<'PY'
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [("core", "0005_backfill")]
    operations = [
        migrations.RenameField(model_name="todo", old_name="title", new_name="name"),
        migrations.RemoveField(model_name="todo", name="priority"),
    ]
PY
# 0007: UniqueConstraint on existing table -> SM011 warning
cat > "$M/0007_unique.py" <<'PY'
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("core", "0006_rename_remove")]
    operations = [migrations.AddConstraint(model_name="todo", constraint=models.UniqueConstraint(fields=["name"], name="todo_name_uniq"))]
PY
# 0008: concurrent index with atomic = False -> no finding
cat > "$M/0008_concurrent.py" <<'PY'
from django.db import migrations, models
from django.contrib.postgres.operations import AddIndexConcurrently

class Migration(migrations.Migration):
    atomic = False
    dependencies = [("core", "0007_unique")]
    operations = [AddIndexConcurrently(model_name="todo", index=models.Index(fields=["name"], name="todo_name_c_idx"))]
PY
# clean tree: 0001 and 0008 only -> no errors
mkdir -p "$T/clean/backend/core/migrations"
cp "$M/0001_initial.py" "$M/0008_concurrent.py" "$T/clean/backend/core/migrations/"
```

Expected totals for `"$T"`: 1 error (`no-merge`) and 6 warnings (`SM001`, `SM010`, `SM011`, `SM016`, `SM006`, `SM002`). No `SM018` finding, because 0008 sets `atomic = False`.

| # | Command | Expected | Assertion |
|---|---|---|---|
| A1 | `uv run mattstack audit --type migrations "$T" --no-todo --json > "$T/out.json"` | exit 1 | `python3 -c` loads `out.json` and checks: `"migrations" in auditors_run`; `summary.errors == 1`; `summary.warnings == 6`; the sorted rule IDs from `message` prefixes equal `["SM001","SM002","SM006","SM010","SM011","SM016","no-merge"]`; every finding has `category == "migrations"` |
| A2 | `uv run mattstack audit "$T" --no-todo --json > "$T/default.json"` | exit not checked | no finding has `category == "migrations"`; `"migrations" not in auditors_run` (default runs do not include the auditor) |
| A3 | `uv run mattstack audit --type migrations "$T/clean" --no-todo --json` | exit 0 | `summary.errors == 0` |
| A4 | `uv run mattstack audit --type nope "$T" --no-todo` | exit 1 | stdout contains `migrations` in the list of valid types |
| A5 | `P=$(mktemp -d)` and `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run mattstack init mig-smoke -p starter-fullstack -o "$P"` (`init` prints no path), then `uv run mattstack audit --type migrations "$P/mig-smoke" --no-todo --json` | exit 0 | `summary.errors == 0` on a fresh scaffold. If the scaffold has a `no-merge` or `SM018` finding, stop and report it; do not edit the boilerplate. |

## Stop conditions and PR evidence

### Stop conditions


- If `mattstack audit --type migrations` refuses a bare directory with no mattstack project, stop and report. A0 then needs a project fixture.
- If plain `uv run mattstack audit` on a fresh scaffold reports a different set of auditor types than before your change, stop. Do not change default behavior.
- If A5 finds an error on the fresh scaffold, stop and report it.
- Commit nothing when stopped; report the exact discrepancy.

### Evidence for the PR


Paste the A1-A5 results and the gate results.

PR body: spec ID, base `e89fac4` and head SHA, owned files with changed-line counts, the A1 to A5 results, and the output of each verification command. Commit subject: `feat(audit): Add migrations auditor to audit --type migrations`. Stage only Files owned, with explicit paths.
