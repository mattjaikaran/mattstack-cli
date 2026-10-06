# mattstack

CLI to scaffold fullstack monorepos, generate components, sync the OpenAPI client, and audit for quality.

## Stack
- Python 3.12+, uv (never pip), ruff, hatchling, Apache-2.0
- Inspect commands with `uv run mattstack --help`; inspect presets and source mappings with `uv run mattstack info`.

## Dev
```bash
uv sync --extra dev            # Install
uv run pytest -x -q            # Run the current test suite
uv run ruff check src/ tests/  # Lint
```

## Commands
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

## Presets
Run `uv run mattstack info` for the current Django Ninja, Django Matt, FastAPI, NestJS, and frontend-only presets.

## Frontend frameworks
`react-vite` | `react-vite-starter` | `react-rsbuild` | `react-rsbuild-kibo` | `nextjs`

## Rules
- `uv` only (never pip/poetry), `bun` for JS (never npm/yarn)
- Type hints on every function, no new dependencies
- Auditors produce `AuditFinding` objects
- Tests in `tests/` mirroring `src/` structure

## Architecture
See [docs/architecture.md](docs/architecture.md) for file map, patterns, and extension workflows.

## Gauntlet Gates

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
| 10 | INSTALL | pip install -e . | yes | — |

```bash
make gauntlet-quick      # quick gates (skip mutation + audit)
make gauntlet            # full gauntlet (all 10 gates)
make gauntlet-gate GATE=lint  # single gate
```
