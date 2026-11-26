# S-CLI-40: `audit --baseline` records findings and fails only on new ones

| Field | Value |
|---|---|
| Spec ID | S-CLI-40 |
| Backlog item | GitHub issue #149; `docs/plans/2026-11-25-roadmap.md:114-115` (section 6, "Standards that ratchet": `audit --baseline`) |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-40 |
| Depends on | none |
| Conflicts with | S-CLI-18, S-CLI-23 and S-CLI-41 (all four edit `scripts/gauntlet.py`; this spec adds one check inside `_gate_install`); S-CLI-26 (`scripts/gauntlet.py`); S-CLI-27 (`scripts/gauntlet.py`); S-CLI-28 (`scripts/gauntlet.py`); S-CLI-29 (`src/mattstack/commands/audit.py`); S-CLI-33 (`src/mattstack/commands/audit.py`); S-CLI-36 (`src/mattstack/cli_scaffold.py`); S-CLI-38 (`src/mattstack/commands/audit.py`); S-CLI-42 (`src/mattstack/commands/audit.py`) |
| Files owned | `src/mattstack/auditors/baseline.py` (new), `src/mattstack/commands/audit.py`, `src/mattstack/cli_scaffold.py`, `src/mattstack/auditors/report.py`, `scripts/gauntlet.py` |
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

- `src/mattstack/auditors/base.py:26-43` defines `AuditFinding` with fields `category`, `severity`, `file: Path`, `line: int`, `message`, `suggestion`. There is no rule id and no fingerprint. `to_dict` is at L35. This spec does not add a field; identity comes from existing fields.
- Messages contain volatile text, so identity must normalize them. `src/mattstack/auditors/quality.py:82` builds `f"{tag} comment: {line.strip()[:80]}"` (the message embeds the source line). `quality.py:94` builds `"Possible mock/placeholder: '{m.group(0)}'"`. Counts and versions are embedded elsewhere, for example `dependencies.py:80-199` and `endpoints.py:109-228`. Consequence: editing the text of a TODO line counts as one fixed finding plus one new finding. This is accepted and recorded in the PR evidence.
- `src/mattstack/cli_scaffold.py:189` defines the `audit` command (options `--type`, `--no-todo`, `--json`, `--severity`, `--html`, `--versions`).
- `src/mattstack/commands/audit.py:47-59` defines `run_audit`. The severity filter is at L153-155. Exit 1 on any ERROR is at L199-200. `write_todo` writes `tasks/todo.md` unless `--no-todo` is set.
- `src/mattstack/auditors/report.py:59` defines `print_json`. Adding a top-level key needs this file, so it is in Files owned.
- Typer probe, run in a scratch file outside the repo with typer 0.24.1: `--baseline` with no value exits 2 ("requires an argument"), and `--baseline PATH` works. So the option takes a required path.
- `scripts/gauntlet.py:290-348` is `_gate_install`. The `sync2` typo check is at L339-342, and `return _smoke_python_pin(...)` is at L343. `GATES` is at L350; the install gate is at L360.

## Goal and non-goals

Goal:
- `mattstack audit ... --write-baseline PATH` records the current findings (after `--severity` filtering) to a JSON file.
- `mattstack audit ... --baseline PATH` reports and fails only on findings that are not in the baseline. Exit 1 if any new finding remains, else exit 0. Fixed findings are counted, not reported as failures.

Non-goals:
- No changes to `base.py`, `endpoints.py`, or any other auditor. No new rule ids.
- No automatic baseline update on a passing run.
- No change to output or exit code when neither flag is given.
- No default baseline path; the path is always explicit.

## Implementation steps

1. Create `src/mattstack/auditors/baseline.py` with these functions:
   - `normalize_message(message: str) -> str`: (a) replace `'[^']*'`, `"[^"]*"` and `` `[^`]*` `` with `Q`; (b) replace each run of digits `\d+` with `N`; (c) collapse whitespace; (d) strip.
   - `fingerprint(finding: AuditFinding, root: Path) -> str`: key = `category`, then `file` as a POSIX path relative to `root` (the raw string if it is not under `root`), then `normalize_message(message)`, joined with `\x1f`. Return the sha256 hex digest of the key. The line is excluded, so moved code keeps its baseline.
   - `write_baseline(path: Path, findings, root: Path) -> None`: writes `{"version": 1, "entries": [...]}` sorted by fingerprint. Each entry has `fingerprint`, `category`, `file`, `message` (normalized) and `count`. Creates parent directories.
   - `load_baseline(path: Path) -> dict[str, int]`: raises `ValueError` for a missing file, invalid JSON, or `version != 1`.
   - `apply_baseline(findings, counts, root) -> BaselineResult`: walk findings in order. A finding consumes one unit of its fingerprint if one is available (unchanged), otherwise it is new. `fixed` is the sum of the leftover units. `BaselineResult` has `new`, `fixed`, `unchanged`.
   Use `hashlib.sha256`. Keep the module under 400 lines.
2. `src/mattstack/cli_scaffold.py` `audit` (L189): add `baseline_file` for `--baseline` and `write_baseline_file` for `--write-baseline`, both `str | None` with default `None`. Pass them to `run_audit` as keyword arguments of the same names.
3. `src/mattstack/commands/audit.py` `run_audit` (L47-59): add keyword arguments `baseline_file: str | None = None` and `write_baseline_file: str | None = None`. After the severity filter (L153-155):
   - If both are set, print a message and exit 2.
   - If `write_baseline_file` is set, write the baseline for the filtered findings, print `Wrote N findings to PATH`, and exit 0.
   - If `baseline_file` is set, call `load_baseline` (on `ValueError`, print the message and exit 2) and then `apply_baseline`. Use `result.new` as the findings for display and for the exit code. Exit 1 if `result.new` is non-empty, else 0. With `--json`, add a top-level key `baseline` = `{"new": len(new), "fixed": fixed, "unchanged": unchanged}`.
   - If neither is set, the behavior is unchanged, including the L199-200 exit rule.
4. `src/mattstack/auditors/report.py` `print_json` (L59): accept an optional `extra: dict | None = None` that is merged into the top-level object. With no `extra`, output must be byte-identical to today.
5. `scripts/gauntlet.py` `_gate_install`: after the `sync2` check, run `[executable, "audit", "--help"]`. Require exit 0 and that the output contains `--baseline` and `--write-baseline`. Otherwise print the output and return False. Change no other gate.
6. Do not touch `tests/`. Do not add dependencies.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `rm -rf /tmp/s-cli-40 && mkdir -p /tmp/s-cli-40/proj/src && printf 'x = 1  # TODO first\n' > /tmp/s-cli-40/proj/src/app.py && uv run mattstack audit /tmp/s-cli-40/proj --type quality --no-todo --json > /tmp/s-cli-40/before.json` | 0 | Creates `/tmp/s-cli-40/before.json` |
| A2 | repo root | `python3 -c "import json; f=json.load(open('/tmp/s-cli-40/before.json'))['findings']; print(len(f) >= 1)"` | 0 | Prints `True`. If `False`, the fixture is wrong: stop, do not edit it to pass |
| A3 | repo root | `uv run mattstack audit /tmp/s-cli-40/proj --type quality --no-todo --write-baseline /tmp/s-cli-40/baseline.json` | 0 | Creates `/tmp/s-cli-40/baseline.json` |
| A4 | repo root | `uv run mattstack audit /tmp/s-cli-40/proj --type quality --no-todo --baseline /tmp/s-cli-40/baseline.json --json > /tmp/s-cli-40/same.json && python3 -c "import json; b=json.load(open('/tmp/s-cli-40/same.json'))['baseline']; print(b['new'], b['fixed'])"` | 0 | Prints `0 0` (unchanged tree gives the same fingerprints) |
| A5 | repo root | `printf 'y = 2  # TODO second\n' >> /tmp/s-cli-40/proj/src/app.py && uv run mattstack audit /tmp/s-cli-40/proj --type quality --no-todo --baseline /tmp/s-cli-40/baseline.json --json > /tmp/s-cli-40/new.json` | 1 | Creates `/tmp/s-cli-40/new.json` (one new finding fails the run) |
| A6 | repo root | `python3 -c "import json; b=json.load(open('/tmp/s-cli-40/new.json'))['baseline']; print(b['new'], b['fixed'])"` | 0 | Prints `1 0` |
| A7 | repo root | `printf 'x = 1\n' > /tmp/s-cli-40/proj/src/app.py && uv run mattstack audit /tmp/s-cli-40/proj --type quality --no-todo --baseline /tmp/s-cli-40/baseline.json --json > /tmp/s-cli-40/fixed.json && python3 -c "import json; b=json.load(open('/tmp/s-cli-40/fixed.json'))['baseline']; print(b['new'], b['fixed'] >= 1)"` | 0 | Prints `0 True` (fixed findings do not fail the run) |
| A8 | repo root | `uv run mattstack audit /tmp/s-cli-40/proj --type quality --no-todo --baseline /tmp/s-cli-40/missing.json` | 2 | Output names `missing.json` |
| A9 | repo root | `uv run mattstack audit /tmp/s-cli-40/proj --type quality --no-todo --json > /tmp/s-cli-40/plain.json && python3 -c "import json; print('baseline' in json.load(open('/tmp/s-cli-40/plain.json')))"` | 0 | Prints `False` (no-flag output is unchanged) |
| A10 | repo root | `uv run python scripts/gauntlet.py --gate install` | 0 | Install gate passes, including the new `audit --help` check |

## Stop conditions and PR evidence

Stop on:
- A wrong citation, or a missing file.
- A needed change outside Files owned. In particular, do not change `base.py` or `endpoints.py`; the fingerprint must work from existing fields.
- A2 printing `False` (the fixture produced no findings).
- Two runs on an unchanged tree producing different fingerprints (A4 would fail).
- A new dependency.

PR evidence: the output of A1-A10, the `audit --help` text, and a note on the normalization limitation (edited TODO text counts as fixed plus new).
