# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Audit delegates to Gauntlet** — `mattstack audit` now runs
  `gauntlet check --tier=<tier> --json` and formats the findings. All six auditor classes
  and the plugin loader are removed. MattStack keeps no check logic.
- Audit output groups findings by Gauntlet check and reports the tier, the Gauntlet
  version, and the blocking count. `--type` now selects a Gauntlet engine
  (`sentinel`, `conformance`, `review`, `quality`) instead of a `types`/`quality`/... domain.
- `tasks/todo.md` entries carry the stable Gauntlet finding id, so a finding is traceable
  to the vault.
- `mattstack gauntlet check` and `mattstack gauntlet run` forward options they do not
  declare, so `--offline`, `--privacy=local`, and `--staged` reach Gauntlet.
- A skipped audit declares itself. The JSON envelope carries `skipped` and `skip_reason`,
  so a consumer never reads a run that did not happen as a clean pass.

### Added

- **`mattstack gauntlet`** — `check` and `run` subcommands that call Gauntlet with the
  project's `gauntlet.toml`. The exit code passes through unchanged.
- **`gauntlet.toml` generation** — `mattstack init` writes a config for the detected stack.
- **`--tier` and `--skip-if-absent`** options on `mattstack audit`.
- `mattstack/gauntlet/` — wire models for the Gauntlet JSON contract, the subprocess
  client, the config generator, and the formatter.
- [docs/gauntlet.md](docs/gauntlet.md) — how MattStack and Gauntlet divide the work.

### Removed

- `mattstack/auditors/` — six auditors, the HTML report, the report writer, and the plugin
  loader.
- Three parser modules that only the auditors used: `parsers/dependencies.py`,
  `parsers/test_files.py`, and `parsers/nextjs_routes.py`, with their tests.
- `mattstack-plugins/` auditor plugins. Add a check to Gauntlet instead. Gauntlet records
  every run in its vault, which a Python plugin could not do.
- `docs/plugin-guide.md`.

### Deprecated

- `mattstack audit --live` and `--base-url`. Gauntlet does not probe live endpoints.
- `mattstack audit --fix`. Gauntlet does not auto-fix. Use `mattstack lint --fix`.

## [0.7.0] - 2026-08-12

### Added

- **Consolidated monorepo generation** — `init` now produces a single root `Makefile`, `.env` family, and `docker-compose` pair with no standalone-project files left inside `backend/`/`frontend/`.
- **Relocated Dockerfiles** — framework-aware `docker/backend/Dockerfile` and `docker/frontend/Dockerfile` (+ `.dev` variant) generated from templates with repo-root build context.
- **Multi-environment config** — `.env.production.example` alongside `.env.example`; `make up-prod` loads `.env.production`.
- **Docker profiles** — `make up-celery` starts Celery worker/beat via the `celery` profile.
- **FastAPI backend support** — 5 presets with SQLAlchemy (async), Alembic, Celery, Redis.
- **NestJS backend support** — 4 presets with Fastify, Drizzle ORM, JWT/OAuth.
- **django-matt backend** — first-class MattAPI controller + CRUDService support.
- **New presets** — `matt-blog`, `matt-portfolio`, `matt-ecommerce`.
- **`generate crud`** — scaffold a full-stack CRUD feature in one command.
- **`sync`** — API client with mutations, pagination, `ApiError`, and `--base-url`.
- **`context`** — AI agent context generation.
- **Parallel execution** — streaming parallel `lint` and `test`.
- **Gauntlet** — 10-gate quality pipeline (`make gauntlet`): format, lint, typecheck, security, architecture, file-length, tests, mutation, audit, install.
- **Control plane** — `mattstack.yml` (emitted by `mattstack init`) drives strictness, branch protection, pluggable board/notify backends, and scope enforcement.
- **`protect`** — enable `no-commit-to-branch`, write `CODEOWNERS`, and apply a GitHub branch-protection ruleset (required PR, reviews, `gauntlet`+`test` status checks, linear history) when `protect_main: true`.
- **`board`** — pluggable kanban (`create`/`list`/`claim`/`transition`/`link-pr`/`sync`) with an Axis HTTP backend, a no-op backend, and Linear/Jira/Hermes stubs.
- **`todo`** — task SSOT: `todo move` archives a checked item from `tasks/todo.md` to `tasks/completed.md` with date + commit SHA.
- **`notify`** — pluggable deploy notifications (hermes, telegram, webhook, none) POSTing the deploy envelope.
- **`verify --scope`** — fail when changed files fall outside the declared plan scope.
- **`rules sync`** — regenerate per-harness adapters (`.claude/`, `.cursor/`, `.windsurf/`, `.kiro/`, `.continue/`, `.agents/`) from canonical `.omp/` + `.context/`.

### Changed

- License switched from MIT to Apache-2.0.
- CI re-enabled on push/PR with mypy (strict), bandit, architecture, and file-length gates.
- Preset descriptions shortened and the preset registry repaired.

### Fixed

- Repaired a broken `PRESETS` dict where `matt-*` presets landed outside the closing brace.
- Corrected `api-dev` `environment` to emit `KEY: value` mapping form (previously invalid `KEY=value`).

## [0.6.0] - 2026-04-05

Initial tagged release.
