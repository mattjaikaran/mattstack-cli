# S-CLI-31: CRUD list query-count guard

| Field | Value |
|---|---|
| Spec ID | S-CLI-31 |
| Backlog item | `docs/plans/2026-11-25-roadmap.md:87` (Theme 3, query-count guard). The roadmap is an untracked draft: it is not in git and has no entry in `tasks/todo.md`. |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-31 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `src/mattstack/commands/codegen/api_tests.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 1 |
| Max changed lines | 200 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run python scripts/gauntlet.py --gate install`; plus generated-file rows T1 to T4 and CLI rows A1 to A5 below |
| Acceptance criteria | T1 to T4 and A1 to A5 (tables below) |

## Context and verified citations

### Current state (verified at `e89fac4`)


- `plan_backend` is in `src/mattstack/commands/codegen/crud_backend.py`. Its `if with_tests:` branch is at line 95.
- `render_api_tests` is in `src/mattstack/commands/codegen/api_tests.py:142`. `_test` is at `:59`. The `TestCase` import is at `:169`. The list test is written inside `if ninja_jwt or not owned:` at `:193-198`.
- Ownership: `DEFAULT_POLICY` in `resource_policy.py` is global. `Scope` values are `global` and `owned`. An owned resource needs `--scope owned --owner-field <name>`.
- `--fields`/`-f` takes `name:type` or `name:fk:Model`, repeatable (`generate_crud.py:35-42`).
- `make_project` is in `tests/test_commands/conftest.py:27-57`, so a new test in `tests/test_commands/` gets it without import.
- The generated file is a `django.test.TestCase` subclass, which uses `self.client`.

### Overlap and reuse

- S-CLI-07 (READY) owns only `tests/test_commands/test_generate_crud_contract.py`. It asserts file existence and substrings (lines 38-82). The guard added here changes generated output only and does not change those assertions, so the two specs do not overlap on files. Conflicts is therefore `none`.
- The repo-level test that used `make_project` (`tests/test_commands/conftest.py:27-57`) is removed by this spec. The fixture is kept for other tests.

## Goal and non-goals


When `generate crud --with-tests` writes a list test, the generated suite also fails if one list request makes more database queries than the measured baseline for its variant. This catches N+1 regressions in generated code.

**Non-goals:** No guard for owned or foreign-key resources in this slice (follow-up). No change to `generate_crud.py` flags. No pytest-style `django_assert_max_num_queries`, because generated tests are `django.test.TestCase` subclasses.

## Implementation steps

### Change


1. Build the guard only when `guard = not owned and not any(f.is_fk for f in fields)` and the list test is emitted.
2. Add `from django.db import connection` and `from django.test.utils import CaptureQueriesContext` to the imports.
3. Add `from {app}.models.{snake} import {name}` to the imports. Extend the existing condition that adds this import so it also fires when `guard` is true.
4. Emit `_test(f"test_list_{plural}_query_count")`. Create three rows with `{name}.objects.create(...)` using `py_literal(_sample(f))` for each field in `fields`. Create them outside the measured block.
5. Emit a measured block with an upper bound, not an exact count:
   ```python
   with CaptureQueriesContext(connection) as ctx:
       response = self.client.get(base, **read)
   self.assertEqual(response.status_code, 200)
   self.assertLessEqual(len(ctx.captured_queries), <BUDGET>)
   ```
   `assertNumQueries(N)` is not used. It requires an exact count, so a baseline of 2 would fail.
6. `<BUDGET>` is a literal per variant. It is not guessed:
   - The variant key is `(api_class, ninja_jwt)`. `api_class` is ninja-extra or django-matt. `ninja_jwt` is true or false.
   - Put a `_LIST_QUERY_BUDGET` dict in `api_tests.py` keyed by that tuple, with the measured baseline for each variant.
   - Measure the baseline on a real scaffold (step A2 below). Set each budget to the measured count, after three consecutive runs give the same count.
   - A per-row query adds 3 queries for 3 rows. That gives baseline + 3, which is above the budget, so the guard fails.

## Machine-checkable acceptance

Acceptance has two groups. Rows T1 to T4 check the generated test text and compile, in the temp scaffold from step A0; they replace the repo-level test, which is removed. Rows A1 to A5 are the real-backend rows: they prove the budget is right, and the generated text checks do not.

Step A0: scaffold the project. This uses the command S-CLI-22 uses (`mattstack init` takes about 2 s):

```bash
P=$(mktemp -d)
GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run mattstack init qg-smoke -p starter-fullstack -o "$P"
```

`init` prints no path. The project is at `$P/qg-smoke`. Run the rows below in order from the repo root. Each generate row passes `--path "$P/qg-smoke"`. Rows A2 to A4 run inside `$P/qg-smoke`, because they start with `cd backend`. Each row gives the expected result.
### Generated-file rows (T1 to T4)

| # | Command (run from the repo root unless it starts with `cd`) | Expected | Assertion |
|---|---|---|---|
| T1 | `uv run mattstack generate crud Widget -f title:str -f price:decimal --with-tests --path "$P/qg-smoke"` | exit 0 | `backend/core/tests/test_widget_api.py` contains `CaptureQueriesContext` and `assertLessEqual`; does not contain `assertNumQueries` |
| T2 | `uv run mattstack generate crud Shelf -f widget:fk:Widget --with-tests --path "$P/qg-smoke"` | exit 0 | `backend/core/tests/test_shelf_api.py` contains neither `CaptureQueriesContext` nor `assertLessEqual` (foreign-key resource: no guard) |
| T3 | `uv run mattstack generate crud Note -f title:str -f owner:fk:User --scope owned --owner-field owner --with-tests --path "$P/qg-smoke"` | exit 0 | `backend/core/tests/test_note_api.py` contains neither `CaptureQueriesContext` nor `assertLessEqual` (owned resource: no guard) |
| T4 | `python3 -m py_compile backend/core/tests/test_widget_api.py backend/core/tests/test_shelf_api.py backend/core/tests/test_note_api.py` | exit 0 | all three generated files compile |

T3 needs a JWT provider. `starter-fullstack` has one: the owned policy requires JWT, and the generate command exits 0 on it. T3 covers the owned branch. Owned resources always have a foreign-key owner, so T3 adds little beyond T2 except the owned-scope branch.

### Real-backend rows (A1 to A5)

These run the scaffold's own backend test runner, not the repo's `tests/`. The scaffold is a generated project, so this is a separate proof.

| # | Command (run from the repo root unless it starts with `cd`) | Expected | Assertion |
|---|---|---|---|
| A1 | `uv run mattstack generate crud Product -f title:str -f price:decimal --with-tests --path "$P/qg-smoke"` | exit 0 | `backend/core/tests/test_product_api.py` contains `test_list_products_query_count` and `CaptureQueriesContext` |
| A2 | Measure: add a temporary `print(len(ctx.captured_queries))` to the generated test and run it 3 times with the scaffold's backend test runner (`cd backend && uv run pytest core/tests/test_product_api.py -k query_count -s`). Repeat for each variant the scaffold can produce (JWT on and off, ninja-extra and django-matt). | three runs print the same count | record the counts in the PR; remove the print before A3 |
| A3 | With the budgets set to the A2 counts, run `cd backend && uv run pytest core/tests/test_product_api.py -k query_count` | exit 0 | all query-count tests pass for every variant |
| A4 | Deliberate N+1: in the generated list controller for `Product`, add a per-row query (for example `Product.objects.filter(pk=row.pk).exists()` inside the loop over rows). Run A3's command again. | exit 1 | the query-count test fails, with the captured count above budget. Do this once for a JWT variant and once for a non-JWT variant. |
| A5 | Negative control: `uv run mattstack generate crud Product -f title:str --path "$P/qg-smoke"` (no `--with-tests`) | exit 0 | `backend/core/tests/test_product_api.py` does not exist |

## Stop conditions and PR evidence

### Stop conditions


- If A1 fails on the fresh scaffold, stop and report. Do not edit the boilerplate.
- If A2's three runs differ, stop. The budget is not stable and must not be set.
- If the scaffold cannot produce a variant (for example django-matt with JWT), record that variant as not generated. Do not invent a budget for it.
- Commit nothing when stopped; report the exact discrepancy.

### Evidence for the PR

Include the A2 measured counts per variant, the A3 and A4 scaffold test results, the T1 to T4 results, and which variants were measured.

PR body: spec ID, base `e89fac4` and head SHA, owned files with changed-line counts, the output of rows T1 to T4 and A1 to A5, and the output of each verification command. Commit subject: `feat(codegen): Add query-count guard to generated list tests`. Stage only Files owned, with explicit paths.
