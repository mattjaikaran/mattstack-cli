# S-CLI-41: `sync check --breaking` diffs the OpenAPI spec against a base ref

| Field | Value |
|---|---|
| Spec ID | S-CLI-41 |
| Backlog item | GitHub issue #150; `docs/plans/2026-11-25-roadmap.md:116-117` (section 6: `sync check --breaking`) |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-41 |
| Depends on | none |
| Conflicts with | S-CLI-18, S-CLI-23 and S-CLI-40 (all four edit `scripts/gauntlet.py`; this spec adds one check inside `_gate_install`); S-CLI-26 (`scripts/gauntlet.py`); S-CLI-27 (`scripts/gauntlet.py`); S-CLI-28 (`scripts/gauntlet.py`) |
| Files owned | `src/mattstack/parsers/openapi_diff.py` (new), `src/mattstack/utils/git.py`, `src/mattstack/commands/openapi.py`, `src/mattstack/commands/sync.py` (only if `check` is wrapped there; otherwise unchanged), `scripts/gauntlet.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | S |
| Max files | 8 |
| Max changed lines | 300 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install`; plus the CLI rows A1-A10 below |
| Acceptance criteria | A1-A10 (table below) |

Rules for this spec: do not add or change files under `tests/`, do not run pytest, do not add a dependency. Behavior is proven by the CLI rows and the install gate.

## Context and verified citations

Verified on `e89fac4` (2026-11-25).

- `src/mattstack/commands/sync.py:14-31` defines `sync_app`, with subcommands `openapi` (L30) and `check` (L31). Deprecated aliases are at L45-46.
- `src/mattstack/commands/openapi.py:225-255` defines `sync_check`. It regenerates through `_generate`, which needs the pinned `@hey-api/openapi-ts` binary (`_tool` at L125-149), and then diffs generated files. So `--breaking` must branch before any generation and must not require node.
- `src/mattstack/commands/openapi.py:90-104` defines `_job(path, schema, output)`, which calls `resolve_schema` and `load_contract`. `PathOption` and `SchemaOption` are at L40-48.
- `src/mattstack/parsers/openapi_spec.py:20` is `ROOT_SCHEMA = openapi.json`. `:22` is `NINJA_SCHEMA = docs/openapi/openapi.json` (relative to the backend directory). `resolve_schema` is at L50-79 and `load_contract` at L82-92.
- `src/mattstack/project.py:53-55` has `root` and `backend_dir` on `ResolvedProject`. `resolve_project` is at L248. The spec's repo root may be different from `project.root` (the backend is nested), so the git top level must be found with `git rev-parse --show-toplevel`.
- `src/mattstack/utils/git.py:26` (`git_available`), `:30` (`clone_repo`), `:58` (`copy_worktree`). Helpers use `subprocess.run([...])` with a list and `# nosec B603, B607`. There is no `git show <ref>:<path>` helper yet.
- Prior art (not imported): `django-ninja-boilerplate` at `fcea3e0` (origin/main) has `scripts/openapi/generate_changelog.py`. It defines a `BreakingChange` enum at L31-36 and classifies changes at L144-368. This spec re-implements a Python subset in mattstack; it does not depend on the boilerplate.
- `_gate_install` in `scripts/gauntlet.py:290-348` already runs `sync --help` in a loop at L334-338. The install gate is at `GATES` L360.

## Goal and non-goals

Goal: `mattstack sync check <project> --breaking [--base REF] [--json]` loads the OpenAPI spec at `REF` and in the working tree, reports breaking changes, and exits 1 if there are any.

Non-goals:
- No node, no generator, no generated-file diff in `--breaking` mode. The existing `sync check` behavior without `--breaking` is unchanged.
- No markdown changelog. No OpenAPI 2.0. No external `$ref` files.
- No check of request-body fields that are removed (clients sending fewer fields is not breaking here).

## Breaking rules (exact)

`kind` values are part of the contract and must be spelled exactly.

| kind | Breaking when |
|---|---|
| `path_removed` | a path in base is absent in head |
| `operation_removed` | an HTTP method under a path in base is absent in head |
| `status_removed` | a 2xx response code of an operation in base is absent in head |
| `property_removed` | a property of a 2xx `application/json` response schema in base is absent in head |
| `enum_value_removed` | an enum value of a property in base is absent in head (request or response) |
| `type_changed` | the `type` of a property or parameter schema differs between base and head |
| `required_added` | an existing operation has a parameter (by `in` + `name`) or a request-body property that is required in head but was not required in base, or was absent in base |

Non-breaking, counted in `non_breaking`: added paths, added operations, added response codes, added response properties, added optional request properties, and required-to-optional changes.

Schema resolution: follow `$ref` values of the form `#/components/schemas/<Name>`, with a visited set to stop cycles. A cycle is not reported; the unresolved node is compared as it is.

Parameters: merge path-level and operation-level `parameters`; the operation-level entry wins for the same `(in, name)`.

Request and response bodies: only `content["application/json"].schema` is compared.

## Implementation steps

1. `src/mattstack/utils/git.py`: add `repo_toplevel(path: Path) -> Path` (`git rev-parse --show-toplevel`) and `show_file(repo: Path, ref: str, rel: str) -> str | None`. The second returns `None` when the path does not exist at `ref`. It raises `ValueError` when `ref` does not resolve (check with `git rev-parse --verify --quiet <ref>^{commit}` first). Use argument lists, `# nosec B603, B607`.
2. Create `src/mattstack/parsers/openapi_diff.py` with a pure function `breaking_changes(base: dict, head: dict) -> DiffResult`. `DiffResult` has `breaking: list[Change]` and `non_breaking: int`. `Change` has `kind`, `method` (or `""`), `path`, and `detail`. No I/O. Keep the module under 400 lines.
3. `src/mattstack/commands/openapi.py` `sync_check`: add `--breaking` (bool, default False), `--base` (str, default `origin/main`), and `--json` (bool, default False, meaningful only with `--breaking`). When `--breaking` is set:
   - Resolve the project and `schema = resolve_schema(project, schema)`.
   - Find `top = repo_toplevel(spec.parent)` and `rel = spec.relative_to(top).as_posix()`.
   - Call `show_file(top, base, rel)`. If it returns `None`, print `no base spec at <base>; nothing to compare` and exit 0.
   - Load base and head with `json.loads`. Run `breaking_changes`.
   - Print one line per change: `BREAKING <kind> <METHOD> <path>: <detail>`, then a summary line. With `--json`, print `{"base": base, "spec": rel, "breaking": [{"kind", "method", "path", "detail"}], "non_breaking": n}`.
   - Exit 1 if any breaking change, else 0.
   - On `ValueError` from `show_file` (unknown ref), print the message and exit 2.
   Do not call `_generate` or any node tool in this branch.
4. `src/mattstack/commands/sync.py`: change only if the `check` subcommand is wrapped and hides the new options. Otherwise leave the file as it is.
5. `scripts/gauntlet.py` `_gate_install`: after the existing `sync --help` loop, run `[executable, "sync", "check", "--help"]`. Require exit 0 and `--breaking` in the output. Otherwise print the output and return False.
6. Do not touch `tests/`. Do not add dependencies.

## Machine-checkable acceptance

Each row uses a fresh project under `/tmp/s-cli-41` and gives explicit paths. `$SPEC` is found with `glob` in each row, not with shell variables.

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `rm -rf /tmp/s-cli-41 && GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run mattstack init sync-smoke -p starter-fullstack -o /tmp/s-cli-41` | 0 | Creates `/tmp/s-cli-41/sync-smoke` |
| A2 | repo root | `git -C /tmp/s-cli-41/sync-smoke init -q && git -C /tmp/s-cli-41/sync-smoke add -A && git -C /tmp/s-cli-41/sync-smoke -c user.name=ci -c user.email=ci@example.invalid commit -qm base` | 0 | A base commit exists at HEAD |
| A3 | repo root | `python3 -c "import glob; print(len(glob.glob('/tmp/s-cli-41/sync-smoke/**/openapi.json', recursive=True)))"` | 0 | Prints `1`. If not, stop: the spec location is ambiguous |
| A4 | repo root | `python3 -c "import glob,json; p=glob.glob('/tmp/s-cli-41/sync-smoke/**/openapi.json', recursive=True)[0]; s=json.load(open(p)); s['paths']['/x-s41-added']={'get': {'responses': {'200': {'description': 'ok'}}}}; json.dump(s, open(p,'w'))" && uv run mattstack sync check /tmp/s-cli-41/sync-smoke --breaking --base HEAD --json > /tmp/s-cli-41/add.json` | 0 | Adding a path is not breaking |
| A5 | repo root | `python3 -c "import json; d=json.load(open('/tmp/s-cli-41/add.json')); print(d['breaking'], d['non_breaking'] >= 1)"` | 0 | Prints `[] True` |
| A6 | repo root | `python3 -c "import glob,json; p=glob.glob('/tmp/s-cli-41/sync-smoke/**/openapi.json', recursive=True)[0]; s=json.load(open(p)); del s['paths'][list(s['paths'])[0]]; json.dump(s, open(p,'w'))" && uv run mattstack sync check /tmp/s-cli-41/sync-smoke --breaking --base HEAD --json > /tmp/s-cli-41/rm.json` | 1 | Removing a path from base is breaking |
| A7 | repo root | `python3 -c "import json; d=json.load(open('/tmp/s-cli-41/rm.json')); print(any(x['kind']=='path_removed' for x in d['breaking']))"` | 0 | Prints `True` |
| A8 | repo root | `uv run mattstack sync check /tmp/s-cli-41/sync-smoke --breaking --base no-such-ref` | 2 | Output names `no-such-ref` |
| A9 | repo root | `env PATH=/usr/bin:/bin "$(which uv)" run mattstack sync check /tmp/s-cli-41/sync-smoke --breaking --base HEAD --json > /tmp/s-cli-41/nonode.json` | 1 | Runs with no node on PATH and still reports the removal (`/tmp/s-cli-41/nonode.json` contains a `path_removed` entry). If `git` is not in `/usr/bin`, stop and record it |
| A10 | repo root | `uv run python scripts/gauntlet.py --gate install` | 0 | Install gate passes, including the new `sync check --help` check |

## Stop conditions and PR evidence

Stop on:
- A wrong citation, or a missing file.
- A needed change outside Files owned.
- `resolve_project` failing on a scaffolded project, or A3 not printing `1`.
- `git rev-parse --show-toplevel` not matching the directory that contains the spec.
- A new dependency.
- A `$ref` cycle that the rules above cannot handle without a decision. Report it; do not invent a rule.

PR evidence: the output of A1-A10, the `sync check --help` text, and the list of `kind` values exercised.
