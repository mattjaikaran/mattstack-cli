# S-CLI-22: Endpoint audit resolves the controller prefix and class-level auth

| Field | Value |
|---|---|
| Spec ID | S-CLI-22 |
| Backlog item | `tasks/todo.md:46-49` (done check: `make gauntlet` on a fresh `starter-fullstack` scaffold; `mattstack audit` is part of it) and `tasks/completed.md:53-54` (`@api_controller`/`@http_*` support in `parsers/django_routes.py`), found on a real scaffold: 8 false `Duplicate route` errors and 44 `No auth on write endpoint` warnings |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | f4c5525 |
| Branch | agent/S-CLI-22 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `src/mattstack/parsers/controller_scope.py` (new), `src/mattstack/auditors/endpoints.py`, `tests/test_auditors/test_endpoints_controller_scope.py` (new) |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 15 |
| Max changed lines | 800 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_auditors/test_endpoints_controller_scope.py tests/test_auditors/test_endpoints.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3; A4 (table below) |

## Context and verified citations

Verified on `f4c5525` (2026-11-11).

- `tasks/todo.md:46-49` asks for a done check on a real scaffold, and the generated `just gauntlet` ends with `mattstack audit --no-todo` (`src/mattstack/templates/root_justfile.py:233`). On a fresh `starter-fullstack` scaffold, `uv run mattstack audit <project> --no-todo --json` exits 1 with 366 errors; 8 of them are the `Duplicate route` errors below. The other errors (180 `Known vulnerability` from the live OSV lookup, 165 Zod drift, 12 hardcoded credentials in boilerplate scripts, 1 duplicate dependency) are not this spec's concern, so the full audit will still exit 1 afterwards. With `--type endpoints` the same scaffold gives 52 findings: those 8 errors and 44 `No auth on write endpoint` warnings.
- The duplicates are false. `src/mattstack/auditors/endpoints.py:149-170` (`_check_duplicates`) keys on `(method, path)` where `path` is the decorator path only. `src/mattstack/parsers/django_routes.py:56` (`parse_routes_file`) matches `@http_*` decorators (`HTTP_DECORATOR_RE`, line 34) without the enclosing `@api_controller` prefix. The scaffold has `todo_controller.py` (`/todos`), `todo_controller_basic.py` (`/todos-basic`), `todo_controller_declarative.py` (`/todos-declarative`) and `todo_controller_partial.py` (`/todos-partial`), each defining `GET /completed`, so the auditor reports `GET /completed defined 4 times`; the real URLs differ.
- The auth warnings are mostly false. `endpoints.py:184-193` (`_check_auth`) uses `Route.has_auth`, which `parse_routes_file` sets from the endpoint's own decorator only (`django_routes.py:69-74`). Generated controllers set `auth=JWTAuth()` on the class (`@api_controller("/todos", tags=["Todos"], auth=JWTAuth())` in the scaffold's `todos/controllers/todo_controller.py`).
- `endpoints.py:64-67` (`_parse_all_routes`) is where each route file is parsed; `django_routes.py:159` (`CONTROLLER_CLASS_RE`) only matches class names ending in `Controller`, so `parse_controller_file` skips `TodoControllerBasic` and `TodoControllerPartial`. Do not reuse it: the new module scans decorators itself and leaves `django_routes.py` alone, which `S-CLI-02` and `S-CLI-03` own.
- Prototype on the same scaffold (decorator scan with balanced-parenthesis argument text, routes inside an indented class body inherit the nearest preceding `@api_controller`): 0 duplicate routes remain and the write-endpoint warnings drop from 44 to 6. The 6 are `POST /signup`, `/login`, `/login/username`, `/passwordless/login/verify` in `core/controllers/auth_controller.py` and `/refresh`, `/logout` in `core/controllers/session_controller.py`: each decorator sets its own `auth=` (public by design), so they keep the warning.
- `tests/test_auditors/test_endpoints.py:29-80` has duplicate and auth tests with plain `@router.*` routes; they must keep passing unchanged. That file belongs to `S-CLI-03`, so new tests go in a new file.
- `endpoints.py` is 280 lines, so about 40 new lines fit under the 400-line cap.

## Goal and non-goals

The endpoint auditor judges a controller route by its full URL path and by the auth its controller declares, so two controllers with different prefixes never collide and an endpoint under `@api_controller(..., auth=X)` is not reported as unauthenticated unless it sets its own falsy `auth=`. Non-goals: no change to `django_routes.py`, to django-matt controllers, to `context routes` output or to live probing (`_live_probe` keeps the decorator path); no change to naming checks or stub detection; no new finding types; the `CONTROLLER_CLASS_RE` suffix limitation is only noted, not fixed.

## Implementation steps

1. Create `src/mattstack/parsers/controller_scope.py` with `class ControllerIndex` built from a file's text: `ControllerIndex(text: str)`, `full_path(route: Route) -> str` and `has_auth(route: Route) -> bool`. Import `Route` from `mattstack.parsers.django_routes`.
2. Scopes: every line-start `@api_controller(` decorator opens a scope that runs to the next such decorator or the end of the file. Read the decorator's call text with a string-aware balanced-parenthesis scan (arguments span lines and contain parentheses, as in `auth=JWTAuth()` and `tags=["Todos — Basic (no decorators)"]`). Scope prefix: the first positional string literal, or none. Scope auth: a top-level `auth=` keyword whose value is not `None` or `False`.
3. A route belongs to a scope only when its decorator line is indented (it is inside a class body) and the scope's decorator line is at or before it; a module-level `@router.get` never inherits a prefix. `full_path`: with a prefix, `prefix.rstrip("/") + "/" + path.lstrip("/")`; otherwise `route.path` unchanged. `has_auth`: `route.has_auth`, or the scope's auth when the scope has it and the route's own decorator call (read the same way, starting at `route.line`) contains no `auth=` keyword at all.
4. In `endpoints.py`, build one `ControllerIndex` per route file in `_parse_all_routes` and keep them by file path on the auditor. `_check_duplicates` keys on `(method, index.full_path(route))` and prints the full path in the message; `_check_auth` uses `index.has_auth(route)` and prints the full path. Leave `_check_stubs`, `_check_naming` and `_live_probe` on `route.path`.
5. Create `tests/test_auditors/test_endpoints_controller_scope.py` that runs `EndpointAuditor` on a `tmp_path` project like `tests/test_auditors/test_endpoints.py:18-41` and asserts on findings. Cover: two controllers with different prefixes and the same `GET /` produce no `Duplicate` finding, with a class name that does not end in `Controller` and a decorator split over several lines; the same prefix in two files still reports one duplicate with the full path in the message; a module-level `@router.get` next to a controller keeps its own path; a controller with `auth=JWTAuth()` and an undecorated `@http_post` gives no `No auth` finding; an endpoint with `auth=None` under such a controller still gives one; a controller without `auth` still gives the finding; `tags=[... (text) ...]` parentheses do not break the prefix.

Stage only the Files owned, with explicit paths. Commit subject: `fix(audit): Resolve controller prefix and class auth`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_auditors/test_endpoints_controller_scope.py tests/test_auditors/test_endpoints.py -q` | 0 | All tests pass; the existing endpoint tests are unchanged |
| A2 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run mattstack init audit-smoke -p starter-fullstack -o /tmp/s-cli-22` | 0 | Creates `/tmp/s-cli-22/audit-smoke` |
| A3 | repo root | `uv run mattstack audit /tmp/s-cli-22/audit-smoke --type endpoints --no-todo --json > /tmp/s-cli-22/audit.json; python3 -c "import json; f=json.load(open('/tmp/s-cli-22/audit.json'))['findings']; print(sum('Duplicate route' in x['message'] for x in f))"` | 0 | Prints `0` (it was 8 on the base commit) |
| A4 | repo root | `python3 -c "import json; f=json.load(open('/tmp/s-cli-22/audit.json'))['findings']; print(sum('No auth on write endpoint' in x['message'] for x in f) <= 6)"` | 0 | Prints `True` (it was 44 on the base commit; the prototype gives 6) |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a new dependency, or a check that fails outside your change. If A3 or A4 does not hold because the scaffold's backend changed upstream, report the counts and the remaining findings instead of loosening the assertion. The PR body lists the spec ID, base and head SHA, owned files with changed-line counts, the duplicate and auth counts before and after, and each criterion with its observed result.
