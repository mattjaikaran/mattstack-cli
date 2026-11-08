# S-CLI-13: Add a --version flag to the root command

| Field | Value |
|---|---|
| Spec ID | S-CLI-13 |
| Backlog item | GitHub issue #49: `mattstack --version` errors with "No such option"; print the installed version and, when installed from git, the commit |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | 599d338 |
| Branch | agent/S-CLI-13 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `src/mattstack/cli.py`, `src/mattstack/commands/version.py`, `tests/test_commands/test_cli.py`, `tests/test_commands/test_version.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Max files | 4 |
| Max changed lines | 120 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_commands/test_cli.py tests/test_commands/test_version.py -q`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3 (table below) |

## Context and verified citations

Verified on `599d338` (2026-11-08).

- Issue #49 asks for `mattstack --version`: print the installed version, and the git commit when installed from git.
- `src/mattstack/cli.py:118-120` is the root `@app.callback()` (`def main(` with the `--verbose` option). It has no `--version` option.
- `src/mattstack/__init__.py:3` defines `__version__ = "0.9.1"`.
- `src/mattstack/commands/version.py:36` (`run_version`) prints the version, then checks PyPI over the network (`check_pypi_version`). The flag must not make a network call. `commands/version.py` imports `httpx` at module level (line 5), so `cli.py` must import it inside the callback to keep `mattstack --help` lazy (module docstring, `cli.py:1-6`).
- `tests/test_commands/test_cli.py:16` (`test_version_command`) is the CliRunner pattern to follow. `tests/test_commands/test_version.py:56` (`TestRunVersion`) shows how that file patches `check_pypi_version`.
- A pip or uv install from a git URL records the commit in the distribution's `direct_url.json` under `vcs_info.commit_id`; a PyPI install and an editable install have no `vcs_info`.

## Goal and non-goals

`mattstack --version` prints `mattstack <version>` and exits 0, with no subcommand and no network access. When the installed distribution came from a VCS URL, the line ends with ` (commit <first 7 characters of commit_id>)`. Non-goals: no change to the `version` subcommand output, no update check, no `-V` short flag.

## Implementation steps

1. In `src/mattstack/commands/version.py`, add `installed_commit() -> str | None`. It reads `direct_url.json` from `importlib.metadata.distribution("mattstack")`, returns `vcs_info.commit_id[:7]` when present, and returns None when the distribution, the file, valid JSON or `vcs_info` is missing. Add `version_line() -> str` that returns `mattstack <__version__>`, with the commit suffix when `installed_commit()` returns a value.
2. In `src/mattstack/cli.py`, add an eager `--version` option to `main` whose callback prints `version_line()` with `typer.echo` and raises `typer.Exit()`. Import `mattstack.commands.version` inside the callback.
3. Tests: in `tests/test_commands/test_version.py`, cover `installed_commit` for a VCS install, an editable install (`dir_info`), and a missing `direct_url.json` (monkeypatch `importlib.metadata.distribution`). In `tests/test_commands/test_cli.py`, run `--version` through the CliRunner with `check_pypi_version` patched to raise, and assert exit 0 and the output line.

Stage only the Files owned, with explicit paths. Commit subject: `feat(cli): Add a --version flag`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `uv run mattstack --version` | 0 | Output is exactly one line, `mattstack 0.9.1` for an editable checkout (no commit suffix) |
| A2 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_commands/test_cli.py -q` | 0 | The `--version` test passes with `check_pypi_version` patched to raise, so no network call is made |
| A3 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_commands/test_version.py -q` | 0 | A VCS `direct_url.json` with `commit_id` `0123456789abcdef` gives `0123456`; an editable or missing file gives None |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a
new dependency, or a check that fails outside your change. Commit nothing and
report the exact discrepancy. The PR body lists the spec ID, base and head SHA,
owned files with changed-line counts, and each criterion with its observed
result.
