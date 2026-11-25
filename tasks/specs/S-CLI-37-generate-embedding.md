# S-CLI-37: `mattstack generate embedding` adds a pgvector embedding model with an HNSW index

| Field | Value |
|---|---|
| Spec ID | S-CLI-37 |
| Backlog item | `tasks/todo.md` (AI layer: generated embedding model, the pattern `core/ai/models/document.py` already uses) |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | 3458590 |
| Branch | agent/S-CLI-37 |
| Depends on | none |
| Conflicts with | S-CLI-09, S-CLI-10 |
| Files owned | `src/mattstack/templates/embedding_model.py` (new), `src/mattstack/commands/generate_embedding.py` (new), `src/mattstack/commands/generate.py` |
| Migrations | none in this repo; the generated backend gets a migration when the user runs `makemigrations` |
| Runtime locks | none |
| Human needed | none |
| Size | S |
| Max files | 6 |
| Max changed lines | 500 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install` (regression only, no edits to it); plus CLI rows A1 to A10 below |
| Acceptance criteria | A1 to A10 (table below) |

## Context and verified citations

Re-verified at `3458590` on 2026-11-25.

- `src/mattstack/commands/generate.py:64-66`: `generate_app.command("model")(model)`, `generate_app.command("crud")(crud)`, `generate_app.command("engine")(engine)`. The new registration goes after line 66, in the same style.
- `src/mattstack/commands/generate_crud.py:44-49` defines the shared option aliases `AppOption`, `PathOption` (`--path`, `-p`), `DryRunOption` (`--dry-run`), and `ForceOption`. The new command reuses them through an import, the same way `generate_crud.py` does.
- `src/mattstack/commands/codegen/plan.py:13-21`: `FilePlan` has `root`, `creates: dict[Path, str]`, and `updates: dict[Path, str]`, with `create()` and `update()`-style methods. Writes happen after planning, and `--dry-run` prints the plan without writing.
- `src/mattstack/runtime_profiles.py:105-108` detects the backend's AI support by reading the `ai` extra from the backend pyproject. The new command uses the same extra to check that pgvector is available (see step 3).
- Reference model, verified on `origin/main` of `~/dev/boilerplates/django-ninja-boilerplate`, `core/ai/models/document.py`: line 9 `from pgvector.django import HnswIndex, VectorField`; line 16 `EMBEDDING_DIMENSIONS = 1536`; line 36 `embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)`; lines 44-52 `class Meta:` with `HnswIndex(...)` and `opclasses=["vector_cosine_ops"]` plus a comment that `hybrid_search` orders by `CosineDistance`. The generated model follows this pattern.
- Distance and opclass pairs, from the pgvector-python README (`github.com/pgvector/pgvector-python`): `CosineDistance` pairs with `vector_cosine_ops`, `L2Distance` with `vector_l2_ops`, and `MaxInnerProduct` with `vector_ip_ops`.
- HNSW dimension limit: pgvector documents a 2,000-dimension maximum for HNSW indexes on `vector`. The executor confirms this in the pgvector README before implementing step 2. If the README says otherwise, stop and report.

## Goal and non-goals

Goal: `mattstack generate embedding <Model> --app <app> [--dims N] [--metric cosine|l2|ip]` writes `<app>/models/<snake>_embedding.py`. It defines `<Model>Embedding` with a one-to-one link to `<Model>`, a `VectorField`, and an `HnswIndex` with the matching opclass. It also adds an import to `<app>/models/__init__.py` so Django discovers the model.

Non-goals:
- No change to the backend repo or to `core/ai/`.
- No embedding generation or sync logic (the model only stores vectors).
- No query-side code. The metric choice maps to a `CosineDistance` / `L2Distance` / `MaxInnerProduct` call in the docstring only.
- No `tests/` file and no pytest (S-CLI-18 forbids both). Verification is the CLI rows below.

## Implementation steps

1. New `templates/embedding_model.py`: `render_embedding_model(app: str, model: str, module: str, dims: int, metric: EmbeddingMetric) -> str`. `EmbeddingMetric` is a `StrEnum` with `COSINE = "cosine"`, `L2 = "l2"`, `IP = "ip"`, mapping to opclass `vector_cosine_ops`, `vector_l2_ops`, `vector_ip_ops`. The generated module:
   ```
   from django.db import models
   from pgvector.django import HnswIndex, VectorField

   from <app>.models.<module> import <Model>


   class <Model>Embedding(models.Model):
       item = models.OneToOneField(<Model>, on_delete=models.CASCADE, related_name="embedding")
       vector = VectorField(dimensions=<dims>)

       class Meta:
           indexes = [
               HnswIndex(
                   name="<snake>_emb_hnsw",
                   fields=["vector"],
                   m=16,
                   ef_construction=64,
                   opclasses=["<opclass>"],
               ),
           ]
   ```
   `<module>` is the file stem that defines `<Model>`, or `models` when the class is defined in `models/__init__.py` (import from `<app>.models` then).
2. New `commands/generate_embedding.py`: `embedding(name, app, dims=1536, metric=cosine, path, dry_run, force)`.
   - `--app` is required. Missing `--app` exits 2.
   - `dims` must be an integer from 1 to 2000 (HNSW limit). Otherwise exit 1 with the limit in the message.
   - Model lookup: find `class <Model>(` in `<backend>/<app>/models/*.py`, where `<backend>` is the backend directory resolved from `--path` the way the other generate commands resolve it (verify in `generate_crud.py` before writing). If not found, exit 1 with "model <Model> not found in <app>/models".
   - If the model already defines a field named `embedding`, exit 1 (the `related_name` would clash).
   - The index name is `<snake>_emb_hnsw`. Django limits index names to 30 characters. If the name is longer, exit 1 and tell the user to pick a shorter model name.
3. pgvector check: read `<backend>/pyproject.toml` with `tomllib`. `project.optional-dependencies.ai` must contain an entry starting with `pgvector`. Otherwise exit 1 with "backend pyproject has no pgvector in the 'ai' extra; add it before generating an embedding model".
4. Write `<backend>/<app>/models/<snake>_embedding.py` through `FilePlan.create`. If the file exists and `--force` is not set, exit 1. `--force` overwrites it.
5. Update `<backend>/<app>/models/__init__.py` through `FilePlan.update`. Append `from <app>.models.<snake>_embedding import <Model>Embedding  # noqa: F401` if it is not already there. If `__init__.py` does not exist, exit 1. Do not create it.
6. `--dry-run` prints the plan and writes nothing.
7. `commands/generate.py`: register `embedding` after line 66.

## Machine-checkable acceptance

Each row runs from `$REPO`, the checkout root, and uses fixtures under `$TMP`. The fixture for every row starts from the same tree:

```
$TMP/backend/pyproject.toml          # [project.optional-dependencies] ai = ["pgvector>=0.4"]
$TMP/backend/catalog/models/__init__.py
                                     # from django.db import models
                                     #
                                     # class Product(models.Model):
                                     #     name = models.CharField(max_length=10)
```

The executor first confirms that `--path "$TMP"` resolves to `$TMP/backend` (the same resolution the other generate commands use). If it resolves differently, adapt the fixture to the resolved layout and record the change in the PR body; do not change the command.

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or file assertion |
|---|---|---|---|---|
| A1 | `$REPO` | `uv run mattstack generate embedding --help` | 0 | stdout contains `--metric` and `--dims` |
| A2 | `$REPO` | Fresh fixture. `uv run mattstack generate embedding Product --app catalog --path "$TMP"` | 0 | `$TMP/backend/catalog/models/product_embedding.py` contains `VectorField(dimensions=1536)` and `vector_cosine_ops` |
| A3 | `$REPO` | Fresh fixture. `uv run mattstack generate embedding Product --app catalog --path "$TMP" --metric l2 --dims 768` | 0 | the file contains `VectorField(dimensions=768)` and `vector_l2_ops` |
| A4 | `$REPO` | Fresh fixture. `uv run mattstack generate embedding Product --app catalog --path "$TMP" --metric dot` | 2 | stderr or stdout names the valid metric choices |
| A5 | `$REPO` | Fixture with the `ai` extra set to `["django-redis>=5"]`, then `uv run mattstack generate embedding Product --app catalog --path "$TMP"` | 1 | output contains `pgvector` |
| A6 | `$REPO` | Fresh fixture. `uv run mattstack generate embedding Product --app catalog --path "$TMP" --dry-run` | 0 | `$TMP/backend/catalog/models/product_embedding.py` does not exist, and `__init__.py` is byte-identical to the fixture (`cmp` against a copy) |
| A7 | `$REPO` | Fresh fixture. `uv run mattstack generate embedding Missing --app catalog --path "$TMP"` | 1 | output contains `model Missing not found` |
| A8 | `$REPO` | Fresh fixture. `uv run mattstack generate embedding Product --app catalog --path "$TMP" --dims 4096` | 1 | output mentions the 2000-dimension HNSW limit |
| A9 | `$REPO` | After A2: `uv run python -m py_compile "$TMP/backend/catalog/models/product_embedding.py"` | 0 | no output |
| A10 | `$REPO` | After A2: rerun the same A2 command without `--force` | 1 | output mentions `--force`. Then rerun with `--force` and expect 0 |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a new dependency, a pgvector README that contradicts the 2000-dimension limit, or a check that fails outside your change. Commit nothing when stopped; report the exact discrepancy.

PR body: spec ID, base `3458590` and head SHA, owned files with changed-line counts, the output of rows A1 to A10, the output of each verification command. Commit subject: `feat(generate): Add embedding model command with HNSW index`. Stage only the Files owned, with explicit paths. Never stage the untracked `tasks/fleet/`, `tasks/specs/S-CLI-26-*`, `tasks/specs/S-CLI-27-*`, `docs/agent-layout.md`, or `docs/plans/` files from other agents.
