# S-CLI-17: Add a scaffold smoke script that runs `just ci` in generated projects

| Field | Value |
|---|---|
| Spec ID | S-CLI-17 |
| Backlog item | `tasks/todo.md:46-49` (done check on a real scaffold) and `tasks/prompt-frontend-runtime.md:176-191` (verify every frontend preset on a real scaffold); GitHub issue #52 (scaffold smoke job: `mattstack init` for each preset, then `just ci`), local part only |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | e9b6016 |
| Branch | agent/S-CLI-17 |
| Depends on | none |
| Conflicts with | none |
| Files owned | `scripts/smoke_scaffold.py` (new), `tests/test_smoke_scaffold_script.py` (new), `Makefile` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 15 |
| Max changed lines | 800 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_smoke_scaffold_script.py -q`; `make -n smoke-scaffold`; `make smoke-scaffold ARGS="--preset starter-frontend"`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3; A4; A5 (table below) |

## Context and verified citations

Verified on `e9b6016` (2026-11-10).

- `tasks/todo.md:46-49` lists the done check (`init`, setup, gauntlet, `sync check`) with no record that anyone ran it. `tasks/prompt-frontend-runtime.md:181-188` repeats the check per frontend preset. Nothing in the repository automates it: `scripts/` holds `check_architecture.py`, `check_file_length.py` and `gauntlet.py` only.
- `src/mattstack/templates/root_justfile.py:178-212` (`_ci_recipe`) generates a `ci` recipe that needs no `.env`, database or Docker; `root_justfile.py:45` emits it for every project type.
- `src/mattstack/presets.py:65` defines `PRESETS`, a dict keyed by preset name; `starter-fullstack`, `starter-api` and `starter-frontend` are keys (lines 66, 79, 91). `src/mattstack/cli_scaffold.py:11` is `init`, with `--preset/-p` and `--output/-o`. `src/mattstack/__main__.py` makes `python -m mattstack` work.
- Measured on this base: `mattstack init smokeapp -p starter-fullstack -o <dir>` exits 0 in about 2 s and `just ci` in the result exits 0 in about 55 s; `starter-frontend` and `starter-api` each pass `just ci` in under 10 s. A bare `init` fails inside the agent environment because its global Git config sets `core.hooksPath` (`tasks/specs/README.md:55-58`); the same call with `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0` succeeds.
- `Makefile:1` is the `.PHONY` line; `Makefile:33` is the `gauntlet-gate` target, the pattern for a target that forwards an argument.
- `tests/test_gauntlet_script.py:14-28` shows how tests load a script with `importlib.util.spec_from_file_location`; follow it.

## Goal and non-goals

`make smoke-scaffold` scaffolds real projects from presets into a temporary directory, runs `just ci` in each, and reports pass or fail per preset, so the done check no longer depends on someone remembering it. Non-goals: no gauntlet gate (the script needs network, `just`, `uv` and `bun`, so it stays out of `make gauntlet-quick`); no Docker, `make setup`, `sync check` or live-server steps; no hosted CI workflow; no change to any generated file.

## Implementation steps

1. Create `scripts/smoke_scaffold.py` with `main(argv: list[str] | None = None, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> int`. The `runner` argument is the one seam: tests pass a fake, the command line uses the default.
2. Arguments: `--preset NAME` (repeatable; default `starter-fullstack`, `starter-api`, `starter-frontend`), `--all` (every key of `mattstack.presets.PRESETS`), `--keep` (keep the temporary directory and print its path), `--timeout SECONDS` (per step; default 900).
3. Validate before running anything: an unknown preset name prints the valid names to stderr and returns 2; a missing `just` on `PATH` (`shutil.which`) prints a one-line install hint and returns 2.
4. For each preset, in a fresh `tempfile.TemporaryDirectory`: run `[sys.executable, "-m", "mattstack", "init", f"smoke-{preset}", "-p", preset, "-o", <tmp>]`, then, only if init exited 0, run `["just", "ci"]` with `cwd=<tmp>/smoke-<preset>`. Both steps get `text=True`, `capture_output=True`, the timeout, and an environment copied from `os.environ` with `GIT_CONFIG_GLOBAL=/dev/null` and `GIT_CONFIG_COUNT=0` so a global `core.hooksPath` cannot break `git init`. A `subprocess.TimeoutExpired` counts as a failure of that step.
5. Print one line per preset: `PASS <preset> (<seconds>s)` or `FAIL <preset>: <step> exited <code>` followed by the last 20 lines of that step's combined output, indented. A failure in one preset does not stop the others. Return 0 when every preset passed, 1 otherwise.
6. In `Makefile`, add `smoke-scaffold` to `.PHONY` and a target `smoke-scaffold: ## Scaffold presets and run just ci in each (needs network, just, uv, bun; usage: make smoke-scaffold ARGS="--preset starter-api")` that runs `uv run python scripts/smoke_scaffold.py $(ARGS)`. Do not add it to `gauntlet`, `gauntlet-quick` or `scripts/gauntlet.py`.
7. Create `tests/test_smoke_scaffold_script.py` with a recording fake runner (no network, no real `just`). Cover: the default run issues init then `just ci` per default preset, `just ci` in `smoke-<preset>` under the init output directory, and the environment carries the two Git variables; a failing `just ci` yields exit 1 and the remaining presets still run; a failing init skips `just ci` for that preset; an unknown preset returns 2 and runs nothing; `--all` covers every key of `PRESETS`; a missing `just` returns 2.

Stage only the Files owned, with explicit paths. Commit subject: `feat(scripts): Add a scaffold smoke script`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_smoke_scaffold_script.py -q` | 0 | All tests pass with a fake runner; no network call |
| A2 | repo root | `make -n smoke-scaffold` | 0 | Prints `uv run python scripts/smoke_scaffold.py` |
| A3 | repo root | `make smoke-scaffold ARGS="--preset starter-frontend"` | 0 | Output contains `PASS starter-frontend` |
| A4 | repo root | `uv run python scripts/smoke_scaffold.py --preset nope` | 2 | stderr lists the valid preset names; nothing is scaffolded |
| A5 | repo root | `grep -c smoke scripts/gauntlet.py` | 1 | Prints `0`: the gauntlet does not run the smoke script |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a new dependency, or a check that fails outside your change. If A3 fails because the generated project's own `just ci` fails, report the preset, the failing step and the last output lines; do not edit generator code or templates to make it pass. Commit nothing and report the exact discrepancy. The PR body lists the spec ID, base and head SHA, owned files with changed-line counts, and each criterion with its observed result.
