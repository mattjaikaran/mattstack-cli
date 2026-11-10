# mattstack

CLI to scaffold fullstack monorepos, generate components, sync the OpenAPI client, and audit for quality.

## Project overview

mattstack scaffolds fullstack monorepos, adds components, generates models and
components, syncs the OpenAPI client, and audits projects for quality.

- Python 3.12+, uv (never pip), ruff, hatchling, Apache-2.0
- Inspect commands with `uv run mattstack --help`; inspect presets and source
  mappings with `uv run mattstack info`.

## Commands

```bash
uv sync --extra dev              # Install
uv run pytest -x -q              # Run the current test suite
uv run ruff check src/ tests/    # Lint
uv run ruff format src/ tests/   # Format
```

### CLI commands

```bash
mattstack init my-app -p starter-fullstack   # Scaffold project
mattstack add frontend -f react-rsbuild-kibo # Add component
mattstack generate model Product --fields "title:str price:decimal"
mattstack generate component ProductCard --with-test
mattstack db migrate | seed | reset          # Database ops
mattstack sync openapi | check               # OpenAPI → types, SDK, Zod, TanStack Query
mattstack dev                                # Start applications and infrastructure
mattstack test --parallel                    # Run tests
mattstack lint --parallel --fix              # Lint + fix
mattstack fmt                                # Format all
mattstack audit --html | --versions          # Static analysis; version drift
mattstack deps check | update | audit        # Dependencies
mattstack health --live                      # Service health
mattstack hooks install                      # Git hooks
mattstack workflow --ci github | gitlab      # Opt-in hosted CI (gates run locally)
mattstack env secrets                        # Create missing .env files with secrets
mattstack upgrade --force                    # Three-way merge boilerplate changes
mattstack doctor                             # Check tools, hooks, MCP servers
mattstack info                               # Show presets/repos
```

### Presets

Run `uv run mattstack info` for the current Django Ninja, Django Matt, FastAPI,
NestJS, and frontend-only presets.

### Frontend frameworks

`react-vite` | `react-vite-starter` | `react-rsbuild` | `react-rsbuild-kibo` | `nextjs`

### Gauntlet gates

| # | Gate | Tool | Quick | Command |
|---|------|------|-------|---------|
| 1 | FORMAT | ruff format --check | yes | `make format` |
| 2 | LINT | ruff check (50+ rules) | yes | `make lint` |
| 3 | TYPECHECK | mypy | yes | `make typecheck` |
| 4 | SECURITY | bandit | yes | — |
| 5 | ARCH | scripts/check_architecture.py | yes | `make arch-check` |
| 6 | FILELENGTH | scripts/check_file_length.py (400 lines) | yes | `make filelength-check` |
| 7 | TEST | pytest + coverage | yes | `make test` |
| 8 | MUTATION | mutmut | no | — |
| 9 | AUDIT | pip-audit | no | — |
| 10 | INSTALL | wheel build from sdist + venv help smoke test | yes | — |

```bash
make gauntlet-quick      # quick gates (skip mutation + audit)
make gauntlet            # full gauntlet (all 10 gates)
make gauntlet-gate GATE=lint  # single gate
```

## Code standards

- `uv` only (never pip/poetry), `bun` for JS (never npm/yarn)
- Type hints on every function, no new dependencies
- Auditors produce `AuditFinding` objects
- No file under `src/` exceeds 400 lines;
  [scripts/check_file_length.py](scripts/check_file_length.py) enforces it.
- Layers: `commands/` may import the core modules (generators, auditors,
  parsers, post_processors, templates, utils); core modules never import
  `commands/`; no cycles between core modules.
  [scripts/check_architecture.py](scripts/check_architecture.py) enforces it.
- File map, patterns, and extension workflows:
  [docs/architecture.md](docs/architecture.md)

## Testing policy

- Tests exist only for a consumer-visible contract; do not generate bulk tests.
  See [tasks/todo.md](tasks/todo.md).
- Tests in `tests/` mirror the `src/` structure.

## Git and commits

- Conventional Commits: `<type>(<scope>): <Capitalized imperative summary>`,
  subject at most 50 characters, body wrapped at 72.
- Stage explicit paths. Leave `git status` clean.
- Prefix test commands with `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_COUNT=0`
  so the agent environment's global `core.hooksPath` and
  `GIT_CONFIG_KEY_0` cannot install hooks that make `git init` fail inside
  tests that build temporary repositories.

## Spec workflow

- agent-run claims READY specs from [tasks/specs/README.md](tasks/specs/README.md),
  works on branch `agent/<Spec ID>`, and changes only the spec's Files owned.
- Run the spec's verification commands, which are the quick gauntlet gates.
- Releases: [docs/release.md](docs/release.md)

## Security

- Never commit secrets or `.env` files.
- Subprocess calls take an argv list, never `shell=True`.
- The bandit gate stays blocking.
- `uv` and `bun` only.
