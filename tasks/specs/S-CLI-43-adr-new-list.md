# S-CLI-43: `mattstack adr new` and `mattstack adr list`

| Field | Value |
|---|---|
| Spec ID | S-CLI-43 |
| Backlog item | `docs/plans/2026-11-25-roadmap.md:120` (section 6: `adr new <title>` writes `docs/adr/NNNN-title.md`) |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-43 |
| Depends on | none |
| Conflicts with | S-CLI-11 and S-CLI-13 (both own `src/mattstack/cli.py`; this spec adds one `LAZY_GROUPS` entry there); S-CLI-24 (`src/mattstack/cli.py`); S-CLI-26 (`src/mattstack/cli.py`) |
| Files owned | `src/mattstack/commands/adr.py` (new), `src/mattstack/cli.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | S |
| Max files | 8 |
| Max changed lines | 300 |
| Verification commands | `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install`; plus the CLI rows A1-A8 below |
| Acceptance criteria | A1-A8 (table below) |

Rules for this spec: do not add or change files under `tests/`, do not run pytest, do not add a dependency. This spec does not touch `scripts/gauntlet.py`, so it adds no conflict on that file.

## Context and verified citations

Verified on `e89fac4` (2026-11-25).

- `docs/plans/2026-11-25-roadmap.md:120` asks for `adr new <title>` to write `docs/adr/NNNN-title.md`.
- `src/mattstack/cli.py:29-60` is the `LAZY_GROUPS` dict. The `sync` entry at L42-46 is the model: `LazyGroupSpec("mattstack.commands.sync", "sync_app", "<help>")`. Add an `adr` entry the same way.
- `src/mattstack/commands/sync.py:14` shows the sub-app pattern (`sync_app = typer.Typer(...)` with a callback), to copy for `adr_app`.
- `mattstack-cli` has no `docs/adr/` (checked: `docs/` has `architecture.md`, `commands.md`, `deployment-guide.md`, `ecosystem.md`, `plugin-guide.md`, `release.md`, `plans/`). The `django-ninja-boilerplate` `origin/main` (`fcea3e0`) has no ADR files either. So there is no existing convention to match; the template below is new.

## Goal and non-goals

Goal:
- `mattstack adr new "<title>" [--path PROJECT]` writes `<PROJECT>/docs/adr/NNNN-<slug>.md` from a Nygard-style template and prints the created path.
- `mattstack adr list [--path PROJECT] [--json]` lists ADRs in number order.

Non-goals:
- No status transitions, no supersede links, no editing of existing ADRs.
- No docs update in `docs/commands.md` (that file's workflow section is owned by S-CLI-20).
- No gauntlet change.

## Exact behavior

Numbering: scan `docs/adr/` for files matching `^(\d{4})-.+\.md$`. The next number is max + 1, or `1` when there are none. Numbers are never reused. If the next number would exceed 9999, exit 2.

Slug: `re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60].strip("-")`. An empty slug exits 2.

Title validation: `title.strip()` must be non-empty and contain no newline. Otherwise exit 2.

Filename: `NNNN-<slug>.md`, with `NNNN` zero-padded to 4 digits.

Template (exact; `<date>` is `date.today().isoformat()`):

```
# NNNN. <title as given, stripped>

- Status: Proposed
- Date: <date>

## Context

## Decision

## Consequences
```

`adr list`: for each matching file in number order, read the first line `# NNNN. <title>` for the title and the `- Status: <value>` line for the status. If either is missing, use the slug from the filename (with `-` replaced by spaces) for the title and `unknown` for the status. A missing `docs/adr/` directory prints nothing and exits 0.

List output (human): one line per ADR, `NNNN  <status>  <title>`. Empty output prints `No ADRs in docs/adr.` and exits 0.

List output (`--json`): a JSON list of `{"number": int, "status": str, "title": str, "file": "<path relative to PROJECT, POSIX>"}`.

## Implementation steps

1. Create `src/mattstack/commands/adr.py` with `adr_app = typer.Typer(...)` and commands `new` and `list`. Put the parsing and numbering in plain functions that return values. Keep the module under 400 lines.
2. `src/mattstack/cli.py`: add `"adr": LazyGroupSpec("mattstack.commands.adr", "adr_app", "Architecture decision records (docs/adr).")` to `LAZY_GROUPS`, next to the `sync` entry.
3. Do not touch `tests/`. Do not add dependencies.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `rm -rf /tmp/s-cli-43 && mkdir -p /tmp/s-cli-43/p && uv run mattstack adr new "Use Postgres" --path /tmp/s-cli-43/p` | 0 | Output contains `0001-use-postgres.md` |
| A2 | repo root | `uv run mattstack adr new "Queue choice" --path /tmp/s-cli-43/p` | 0 | Output contains `0002-queue-choice.md` |
| A3 | repo root | `python3 -c "import os; print(sorted(os.listdir('/tmp/s-cli-43/p/docs/adr')))"` | 0 | Prints `['0001-use-postgres.md', '0002-queue-choice.md']` |
| A4 | repo root | `uv run mattstack adr new "A  B/C" --path /tmp/s-cli-43/p` | 0 | Creates `0003-a-b-c.md` |
| A5 | repo root | `uv run mattstack adr list --path /tmp/s-cli-43/p --json > /tmp/s-cli-43/list.json && python3 -c "import json; print([(x['number'], x['status'], x['title']) for x in json.load(open('/tmp/s-cli-43/list.json'))])"` | 0 | Prints `[(1, 'Proposed', 'Use Postgres'), (2, 'Proposed', 'Queue choice'), (3, 'Proposed', 'A  B/C')]` |
| A6 | repo root | `uv run mattstack adr new "   " --path /tmp/s-cli-43/p` | 2 | Error message; no file is created |
| A7 | repo root | `uv run mattstack adr list --path /tmp/s-cli-43/none --json > /tmp/s-cli-43/none.json && python3 -c "import json; print(json.load(open('/tmp/s-cli-43/none.json')))"` | 0 | Prints `[]` |
| A8 | repo root | `uv run mattstack adr --help` | 0 | Help lists `new` and `list` |

## Stop conditions and PR evidence

Stop on:
- A wrong citation, or a missing file.
- A needed change outside Files owned. In particular, do not edit `docs/commands.md`.
- A new dependency.
- Any need to change the `LAZY_GROUPS` mechanism itself, rather than adding one entry.

PR evidence: the output of A1-A8, the generated template for `0001`, and the `adr --help` text.
