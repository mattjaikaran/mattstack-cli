# S-CLI-38: `mattstack audit --type vectors` checks pgvector fields, indexes, and opclasses

| Field | Value |
|---|---|
| Spec ID | S-CLI-38 |
| Backlog item | `tasks/todo.md` (AI layer: static checks for pgvector usage in generated and hand-written backends) |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | 3458590 |
| Branch | agent/S-CLI-38 |
| Depends on | none |
| Conflicts with | S-CLI-09, S-CLI-10; S-CLI-29 (`src/mattstack/auditors/base.py`, `src/mattstack/commands/audit.py`); S-CLI-33 (`src/mattstack/auditors/base.py`, `src/mattstack/commands/audit.py`); S-CLI-40 (`src/mattstack/commands/audit.py`) |
| Files owned | `src/mattstack/auditors/base.py`, `src/mattstack/auditors/vectors.py` (new), `src/mattstack/commands/audit.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | S |
| Max files | 6 |
| Max changed lines | 500 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install` (regression only, no edits to it); plus CLI rows A1 to A8 below |
| Acceptance criteria | A1 to A8 (table below) |

## Context and verified citations

Re-verified at `3458590` on 2026-11-25.

- `src/mattstack/auditors/base.py:11-14` `Severity` has `ERROR = "error"`, `WARNING = "warning"`, `INFO = "info"`.
- `src/mattstack/auditors/base.py:17-23` `AuditType` has `TYPES`, `QUALITY`, `ENDPOINTS`, `TESTS`, `DEPENDENCIES`, `VULNERABILITIES`. This spec adds `VECTORS = "vectors"` after line 23.
- `src/mattstack/auditors/base.py:26-43` `AuditFinding` has `category`, `severity`, `file`, `line`, `message`, `suggestion`, and `to_dict()`. The auditor returns a list of these from `run()`.
- `src/mattstack/auditors/base.py:44-62` `AuditConfig` has `project_path: Path`, `audit_types`, `live`, `write_todo`, `json_output`, `fix`, `base_url`, `min_severity`, and `should_run(audit_type)`.
- `src/mattstack/commands/audit.py:37-44` `AUDITOR_CLASSES` maps each `AuditType` to its auditor class. This spec adds `AuditType.VECTORS: VectorAuditor` after line 43.
- `src/mattstack/commands/audit.py:122` iterates `AUDITOR_CLASSES.items()` and runs each auditor the config selects.
- `src/mattstack/commands/audit.py:197-200`: `if error_count: raise typer.Exit(code=1)`. So a finding with `Severity.ERROR` makes the command exit 1. Warnings and info do not.
- `src/mattstack/cli_scaffold.py:190-205`: the audit command takes a positional `path` (default cwd), `--type/-t` (repeatable or comma-separated), `--live`, and `--no-todo` (skips writing `tasks/todo.md`).
- `src/mattstack/parsers/django_models.py:36-42` parses fields with a regex only. It does not see `class Meta: indexes = [...]`, and it cannot resolve `dimensions=EMBEDDING_DIMENSIONS`. This spec does not change the shared parser. The vector auditor uses `ast` directly.
- Reference model (boilerplate `origin/main`, `core/ai/models/document.py`): line 16 `EMBEDDING_DIMENSIONS = 1536` (module-level constant); line 36 `embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)`; lines 44-52 `Meta.indexes` containing `HnswIndex(..., opclasses=["vector_cosine_ops"])`. The auditor must pass this file with no findings.
- Opclass and distance pairs, from the pgvector-python README: `vector_cosine_ops` with `CosineDistance`, `vector_l2_ops` with `L2Distance`, `vector_ip_ops` with `MaxInnerProduct`.

## Goal and non-goals

Goal: a new `VectorAuditor` that scans the backend's Python files with `ast` and reports:

1. **error**: a `VectorField` whose `dimensions` is not a positive int, after resolving module-level int constants in the same file. A non-literal that cannot be resolved is a warning, not an error (see step 2).
2. **warning**: a `VectorField` with no `HnswIndex` or `IvfflatIndex` in the same model's `Meta.indexes` whose `fields` include it.
3. **error**: an index whose `opclasses` does not match the distance function used on the same field across the backend. Distance functions are read from calls `CosineDistance("field", ...)`, `L2Distance("field", ...)`, and `MaxInnerProduct("field", ...)` where the first argument is a string literal. The pairs are the ones listed above.

Non-goals:
- No change to `parsers/django_models.py` or any other shared parser (see the citation above).
- No `--fix` behavior. The auditor reports only; `config.fix` is ignored.
- No live probing and no database connection.
- No `tests/` file and no pytest (S-CLI-18 forbids both). Verification is the CLI rows below.

## Implementation steps

1. `auditors/base.py`: add `VECTORS = "vectors"` to `AuditType` after line 23.
2. New `auditors/vectors.py`: `class VectorAuditor(BaseAuditor)` with `run() -> list[AuditFinding]`.
   - Walk `config.project_path` for `**/*.py` under a `backend` directory, skipping `.venv`, `migrations`, and `node_modules`. Use the same backend resolution as the other auditors (verify in `auditors/endpoints.py` before writing). If there is no backend directory, return no findings.
   - Parse each file with `ast.parse`. Collect module-level assignments whose value is an int literal, including annotated assignments such as `EMBEDDING_DIMENSIONS: int = 1536`. These are the constant table for that file.
   - For each `class` body, find `VectorField(...)` assignments. Resolve `dimensions`:
     - int literal: use it. Must be > 0, otherwise error.
     - name in the file's constant table: use the value. Must be > 0, otherwise error.
     - name not in this file's table: warning "cannot resolve dimensions for <field>; define it in this module or use an int literal". This keeps the audit from failing on imports.
     - missing or any other expression: error.
   - In the same class's `Meta.indexes` list, find `HnswIndex(...)` and `IvfflatIndex(...)` calls whose `fields` list includes the field name. If none exists, warning "vector field <field> has no HNSW or IVFFlat index".
   - Read `opclasses` from each matching index. The first entry must be one of `vector_cosine_ops`, `vector_l2_ops`, `vector_ip_ops`. Other values are an error.
   - Across all backend files, record each distance call's `(field, distance)` pair. For each field with an index, compare the index opclass with the distance calls. A mismatch is an error: "index on <field> uses <opclass> but <distance> is used on it".
   - Findings carry the file path and the line number of the node.
3. `commands/audit.py`: import `VectorAuditor` and add `AuditType.VECTORS: VectorAuditor` to `AUDITOR_CLASSES` after line 43.

## Machine-checkable acceptance

Fixtures are created under `$TMP`. Each row runs from `$REPO`. The JSON assertions use `AuditFinding.to_dict()`, so each finding has `category` and `severity` keys. A row passes only when the exit code and the assertion both hold.

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | `$REPO` | Fixture `$TMP/backend/catalog/models/doc.py` with `EMBEDDING_DIMENSIONS = 1536` and a class `Doc` containing `embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS)` and a `Meta.indexes` `HnswIndex(fields=["embedding"], opclasses=["vector_cosine_ops"], ...)`, plus a `CosineDistance("embedding", q)` call in `catalog/services.py`. Run `uv run mattstack audit --type vectors "$TMP" --json --no-todo`. | 0 | `findings` is an empty list for category `vectors` |
| A2 | `$REPO` | Fixture with `VectorField(dimensions=1536)` and no index on that field. Same command as A1. | 0 | one finding with `category` `vectors`, `severity` `warning`, and a message containing `no HNSW or IVFFlat index` |
| A3 | `$REPO` | Fixture with `VectorField(dimensions="1536")` (a string literal). Same command. | 1 | one finding with `severity` `error` and a message containing `dimensions` |
| A4 | `$REPO` | Fixture with `HnswIndex(fields=["embedding"], opclasses=["vector_l2_ops"], ...)` and `CosineDistance("embedding", q)` in `catalog/services.py`. Same command. | 1 | one finding with `severity` `error` and a message containing `vector_l2_ops` and `CosineDistance` |
| A5 | `$REPO` | Fixture with `VectorField(dimensions=DIMS)` where `DIMS` is imported from another module and not defined in this file. Same command. | 0 | one finding with `severity` `warning` and a message containing `cannot resolve dimensions` |
| A6 | `$REPO` | Fixture with `VectorField(dimensions=1536)` and `HnswIndex(fields=["embedding"], opclasses=["vector_cosine_ops"])`, but in a `.venv/` directory under the backend. Same command. | 0 | no findings from `.venv` paths |
| A7 | `$REPO` | `uv run mattstack audit --help` | 0 | stdout lists `vectors` among the `--type` values |
| A8 | `$REPO` | Confirm `tasks/todo.md` is not modified by the A1 to A6 runs (`git diff --quiet -- tasks/todo.md` after `--no-todo`) | 0 | no diff |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a new dependency, or a check that fails outside your change. Stop if `auditors/endpoints.py` resolves the backend directory differently from what step 2 assumes, and report the difference instead of guessing. Commit nothing when stopped; report the exact discrepancy.

PR body: spec ID, base `3458590` and head SHA, owned files with changed-line counts, the JSON output of rows A1 to A6, and the output of each verification command. Commit subject: `feat(audit): Add vectors audit for pgvector fields and indexes`. Stage only the Files owned, with explicit paths. Never stage the untracked `tasks/fleet/`, `tasks/specs/S-CLI-26-*`, `tasks/specs/S-CLI-27-*`, `docs/agent-layout.md`, or `docs/plans/` files from other agents.
