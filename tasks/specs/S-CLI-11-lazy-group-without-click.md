# S-CLI-11: LazyTyperGroup stops importing standalone click

| Field | Value |
|---|---|
| Spec ID | S-CLI-11 |
| Backlog item | `tasks/todo.md:16-20` (release process): make `LazyTyperGroup` work without importing standalone `click` |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | 9337e65 |
| Branch | agent/S-CLI-11 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `src/mattstack/cli.py`, `tests/test_commands/test_cli.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 2 |
| Max changed lines | 120 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_commands/test_cli.py -q`; `! grep -n 'import click' src/mattstack/cli.py`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3; A4 (table below) |

## Context and verified citations

Verified on `9337e65` (2026-10-28). Installed typer is 0.24.1 (`uv.lock:702-703`); `pyproject.toml:27` caps `typer<0.26`.

- `src/mattstack/cli.py:14` has `import click`. It is used for `click.Context` (lines 71, 74, 86, 99), `click.Command` (74, 87, 88), `click.Group(...)` (79), `click.UsageError` (90, 97) and `click.HelpFormatter` (99).
- `typer.Context` and `typer.core.TyperCommand` / `TyperGroup` are public and importable on 0.24.1 (`uv run python -c "import typer; from typer.core import TyperCommand, TyperGroup; typer.Context"`). typer 0.27.3 exports the same names (checked in a temporary venv) and vendors click as the private `typer._click`; do not import that.
- `TyperGroup.resolve_command` suggests only loaded commands, so `resolve_command` (`cli.py:85-97`) catches `UsageError` and re-raises it with lazy groups included. `mattstack sync2` prints `No such command 'sync2'. Did you mean 'sync'?` today.
- `tests/test_commands/test_cli.py` uses `runner = CliRunner()` (line 13) and `app` (line 11); `test_audit_did_you_mean` (line 46) is the style to copy.

## Goal and non-goals

`cli.py` imports no `click` and keeps its behaviour: lazy groups load on first use, root help lists them without importing their modules, and a mistyped group suggests the closest lazy group. Decision: replace the `UsageError` catch with a check before delegating. When `args[0]` does not start with `-`, is not in `list_commands(ctx)` and has close matches, call `ctx.fail(...)` with the same `No such command ... Did you mean ...?` text; otherwise call `super().resolve_command`. Use `typer.Context` and `TyperCommand` for annotations and the placeholder group in `get_command` (`TyperGroup(name=..., short_help=...)`); annotate `format_help`'s formatter as `Any`. Non-goals: leave `pyproject.toml`, `uv.lock` and the `typer<0.26` cap untouched (lifting it needs a network re-lock; see the manifest draft); no other command changes.

## Implementation steps

1. Rewrite the imports and annotations in `src/mattstack/cli.py` as above; keep `LAZY_GROUPS` and `LazyGroupSpec` unchanged.
2. Add tests to `tests/test_commands/test_cli.py`: `["sync2"]` fails with `Did you mean` and `sync`; `["--help"]` lists every `LAZY_GROUPS` name; `["sync", "--help"]` exits 0.

Stage only the Files owned, with explicit paths. Commit subject: `refactor(cli): Drop the standalone click import from LazyTyperGroup`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | see Verification commands | 0 | `! grep -n 'import click' src/mattstack/cli.py` prints nothing and exits 0 |
| A2 | repo root | see Verification commands | 0 | `mattstack sync2` exits non-zero and the output contains `Did you mean` and `sync` |
| A3 | repo root | see Verification commands | 0 | Root `--help` output contains every name in `LAZY_GROUPS`; `sync --help` exits 0 |
| A4 | repo root | see Verification commands | 0 | `uv run mypy src/` passes with no `type: ignore` added |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
