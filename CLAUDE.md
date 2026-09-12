# mattstack

CLI to scaffold fullstack monorepos, generate components, sync types, and run the Gauntlet gate.

## Stack
- Python 3.12+, uv (never pip), ruff, hatchling, Apache-2.0
- 26 commands, 7 subgroups, 12 presets, 7 source repos

## Dev
```bash
uv sync --extra dev            # Install
uv run pytest -x -q            # 783 tests
uv run ruff check src/ tests/  # Lint
```

## Commands
```bash
mattstack init my-app -p starter-fullstack   # Scaffold project
mattstack add frontend -f react-rsbuild-kibo # Add component
mattstack generate model Product --fields "title:str price:decimal"
mattstack generate component ProductCard --with-test
mattstack db migrate | seed | reset          # Database ops
mattstack sync types | zod | api-client      # Pydantic → TS/Zod
mattstack dev                                # Start all services
mattstack test --parallel                    # Run tests
mattstack lint --parallel --fix              # Lint + fix
mattstack fmt                                # Format all
mattstack audit --tier full      # Run Gauntlet, format findings
mattstack audit --json           # Machine-readable findings
mattstack gauntlet check --tier fast   # Call Gauntlet directly
mattstack deps check | update | audit        # Dependencies
mattstack health --live                      # Service health
mattstack hooks install                      # Git hooks
mattstack workflow                           # Generate CI/CD
mattstack info                               # Show presets/repos
```

## Presets
starter-fullstack, b2b-fullstack, starter-api, b2b-api, starter-frontend, simple-frontend, rsbuild-fullstack, rsbuild-frontend, kibo-fullstack, kibo-frontend, nextjs-fullstack, nextjs-frontend

## Frameworks
`react-vite` | `react-vite-starter` | `react-rsbuild` | `react-rsbuild-kibo` | `nextjs`

## Rules
- `uv` only (never pip/poetry), `bun` for JS (never npm/yarn)
- Type hints on every function, no new dependencies
- Verification is Gauntlet's job: `audit` shells out to `gauntlet check --json` and only
  formats the result. Never add a check to this repo; add it to Gauntlet
- Parsers use regex (not AST); `parsers/` stays, `auditors/` is deleted
- Tests in `tests/` mirroring `src/` structure

## Architecture
See [docs/architecture.md](docs/architecture.md) for file map, patterns, and extension workflows.


## Two things named gauntlet

| Name | What it is | Where |
|------|------------|-------|
| **Gauntlet** (the engine) | The Rust verification CLI that `mattstack audit` calls | `~/dev/gauntlet`, github.com/mattjaikaran/gauntlet |
| **`make gauntlet`** | This repo's local 10-gate quality script | `scripts/gauntlet.py` |

They are different tools. `mattstack audit` runs the engine. `make gauntlet` runs this
repo's own gates. See [docs/gauntlet.md](docs/gauntlet.md) for the integration and
`gauntlet.toml` options.

## Local gates (make gauntlet)


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
