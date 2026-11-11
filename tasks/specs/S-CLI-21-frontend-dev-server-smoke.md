# S-CLI-21: Add a smoke script that boots the dev server of every frontend preset

| Field | Value |
|---|---|
| Spec ID | S-CLI-21 |
| Backlog item | `tasks/prompt-frontend-runtime.md:176-191` (verify a route and the API proxy on a real scaffold, not only a vite boot) and `tasks/todo.md:42-45` (no record shows a route resolving on a real scaffold); the dev-server half, with no Docker |
| Role | coding |
| Status | READY |
| Assigned executor | unattended executor (agent-run) |
| Base commit | f4c5525 |
| Branch | agent/S-CLI-21 |
| Depends on | none |
| Conflicts with | S-CLI-17 |
| Files owned | `scripts/smoke_frontend_dev.py` (new), `tests/test_smoke_frontend_dev_script.py` (new), `Makefile` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | M |
| Max files | 15 |
| Max changed lines | 800 |
| Verification commands | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_smoke_frontend_dev_script.py -q`; `make -n smoke-frontend-dev`; `make smoke-frontend-dev ARGS="--preset starter-fullstack"`; `uv run ruff format --check src/ tests/`; `uv run ruff check src/ tests/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest -x -q --tb=short` |
| Acceptance criteria | A1; A2; A3; A4; A5 (table below) |

## Context and verified citations

Verified on `f4c5525` (2026-11-11).

- `tasks/prompt-frontend-runtime.md:176-190` warns that "vite started" and "HTTP 200" are not proof: a route must resolve without `Error transforming route file` in the dev log (line 185), and a request through the proxy must not be answered by the SPA shell (lines 182-184); step 6 (lines 189-190) repeats the check on other presets. `tasks/todo.md:42-45` records that nothing shows this on a real scaffold. Nothing in the repository automates it: `scripts/` holds `check_agent_docs.py`, `check_architecture.py`, `check_file_length.py`, `gauntlet.py` and `smoke_scaffold.py` (`just ci` only, no dev server).
- `src/mattstack/presets.py:66` (`starter-fullstack`, react-vite), `:98` (`simple-frontend`, React Router, frontend only), `:106` (`rsbuild-fullstack`), `:121` (`kibo-fullstack`) and `:136` (`nextjs-fullstack`) are the keys; `scripts/smoke_scaffold.py` is the pattern for scaffolding (`python -m mattstack init NAME -p PRESET -o DIR` with `GIT_CONFIG_GLOBAL=/dev/null` and `GIT_CONFIG_COUNT=0` in the environment) and for `PASS`/`FAIL` output.
- `src/mattstack/post_processors/frontend_config.py:174` (`_patch_dev_server`) sets port 3000 and the `/api` proxy on the Vite and Rsbuild configs.
- Measured on `f4c5525` (each scaffold: `init` about 4 s, `bun install --frozen-lockfile` a few seconds, `bun run dev` ready in under 9 s; backend not running): `starter-fullstack` serves 200 on `/` and `/dashboard`, `GET /api/health/` returns 500 with an empty body (vite proxy error, `ECONNREFUSED`), log has no `Error transforming route file`. `rsbuild-fullstack` and `kibo-fullstack` return 200 on `/` and `/dashboard` and 504 `Error occurred while trying to proxy` on `/api/health/`. `simple-frontend` returns 200 on `/`, `/dashboard` and, having no backend, the HTML shell on `/api/health/`. `nextjs-fullstack` returns 200 on `/` and `/dashboard`, and `/api/health/` returns `{"status":"ok",...}` from Next.js's own route, so it says nothing about the proxy. All five bind port 3000.

## Goal and non-goals

`make smoke-frontend-dev` scaffolds the frontend presets, installs their dependencies from the lockfile, starts the real dev server, and fails when the shell does not load, a route does not resolve, the log shows a router transform error, or (where a backend is scaffolded and the framework proxies `/api`) the proxy path is answered with the SPA's HTML. Non-goals: no Docker (`frontend-dev` container, `--frozen-lockfile` inside the image) and no running backend; no `make setup`; no gauntlet gate (needs network and `bun`, so it stays out of `make gauntlet-quick`); no change to generated files or generator code.

## Implementation steps

1. Create `scripts/smoke_frontend_dev.py` with `main(argv: list[str] | None = None, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run, server: Callable[..., ContextManager[DevServer]] = dev_server) -> int`. The two arguments are the seams: tests pass fakes, the command line uses the defaults. `DevServer` is a small protocol or dataclass with `get(path: str) -> tuple[int, str]` (status and body, no redirect following, short timeout) and `log() -> str` (output so far).
2. Preset table, a module constant mapping preset to whether `/api` must be proxied: `starter-fullstack` yes, `rsbuild-fullstack` yes, `kibo-fullstack` yes, `simple-frontend` no, `nextjs-fullstack` no. Arguments: `--preset NAME` (repeatable; default every key of the table), `--keep` (keep the temporary directory and print its path), `--timeout SECONDS` (per `init` or install step; default 600), `--ready-timeout SECONDS` (wait for `/`; default 60).
3. Validate before running anything: an unknown preset prints the valid names to stderr and returns 2; `bun` not on `PATH` returns 2 with a one-line hint; port 3000 already bound (`socket.connect_ex(("127.0.0.1", 3000)) == 0`) returns 2 with the message that the dev server needs port 3000.
4. For each preset in a fresh temporary directory: `[sys.executable, "-m", "mattstack", "init", f"smoke-{preset}", "-p", preset, "-o", <tmp>]`, then `["bun", "install", "--frozen-lockfile"]` with `cwd=<tmp>/smoke-<preset>/frontend`; the first non-zero exit is `FAIL <preset>: <step> exited <code>` with the last 20 output lines indented, and the server is not started. Run both with the smoke_scaffold environment (`GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_COUNT=0`).
5. Start `["bun", "run", "dev"]` in the frontend directory with `start_new_session=True`, stdout and stderr merged into a log, and always kill the whole process group (`os.killpg`) when the check ends, also on failure or timeout. Poll `GET /` until it returns 200 or `--ready-timeout` passes (`FAIL <preset>: dev server not ready after <n>s` plus the last 20 log lines).
6. Checks after the shell loads, each reported by name on failure: `/` is 200 and its body contains `<html` (case-insensitive); `/dashboard` is 200; after both requests and a 2 s settle, the log does not contain `Error transforming route file`; when the table says proxy, `GET /api/health/` returns a body that does not contain `<html` (a proxy error status such as 500 or 504, or a real API response, both pass; the SPA shell fails). Print `PASS <preset> (<seconds>s)` when all pass. A failure in one preset does not stop the others. Return 0 when all passed, 1 otherwise.
7. In `Makefile`, add `smoke-frontend-dev` to `.PHONY` and a target `smoke-frontend-dev: ## Boot each frontend preset's dev server and check the shell, a route and the API proxy (needs network and bun; usage: make smoke-frontend-dev ARGS="--preset starter-fullstack")` that runs `uv run python scripts/smoke_frontend_dev.py $(ARGS)`. Do not add it to `gauntlet`, `gauntlet-quick` or `scripts/gauntlet.py`.
8. Create `tests/test_smoke_frontend_dev_script.py` with a recording fake runner and a fake `server` (no network, no `bun`, no socket; patch the port and `bun` checks as the script exposes them). Load the script with `importlib.util.spec_from_file_location` like `tests/test_gauntlet_script.py:14-28`. Cover: all checks pass gives exit 0 and `PASS`; a log containing `Error transforming route file` fails; a proxy path answered with an HTML body fails for a proxied preset and is not requested for `simple-frontend` and `nextjs-fullstack`; a failing install skips the server and the other presets still run; an unknown preset returns 2 and runs nothing; the server handle is always closed when a check fails.

Stage only the Files owned, with explicit paths. Commit subject: `feat(scripts): Add a frontend dev server smoke script`.

## Machine-checkable acceptance

| ID | Cwd | Exact command or journey step | Expected exit/status | Exact output or JSON assertion |
|---|---|---|---|---|
| A1 | repo root | `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0 uv run pytest tests/test_smoke_frontend_dev_script.py -q` | 0 | All tests pass with fakes; no network call |
| A2 | repo root | `make -n smoke-frontend-dev` | 0 | Prints `uv run python scripts/smoke_frontend_dev.py` |
| A3 | repo root | `make smoke-frontend-dev ARGS="--preset starter-fullstack --preset simple-frontend"` | 0 | Output contains `PASS starter-fullstack` and `PASS simple-frontend`; afterwards no process listens on port 3000 |
| A4 | repo root | `uv run python scripts/smoke_frontend_dev.py --preset nope` | 2 | stderr lists the valid preset names; nothing is scaffolded |
| A5 | repo root | `grep -c smoke_frontend_dev scripts/gauntlet.py` | 1 | Prints `0`: the gauntlet does not run the smoke script |

## Stop conditions and PR evidence

Stop on a wrong citation, a missing file, a needed file outside Files owned, a new dependency, or a check that fails outside your change. If A3 fails because a generated frontend fails its own check (for example a transform error or a missing proxy), report the preset, the failing check and the last log lines; do not edit generator code or templates to make it pass. If port 3000 is in use on the host, report it and stop. The PR body lists the spec ID, base and head SHA, owned files with changed-line counts, and each criterion with its observed result.
