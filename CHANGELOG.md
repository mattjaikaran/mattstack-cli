# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Persist nonsecret project metadata and resolve nested commands consistently.
- Add local OpenAPI SDK generation with ownership protection and read-only drift checks.
- Add project-aware JSON diagnostics and optional, privacy-aware frontend tool guidance.

### Changed

- Separate host and container development modes; supervise process groups and application containers.
- Keep parallel lint and test failure behavior consistent, including format checks.
- Preserve existing add, upgrade, and workflow files unless replacement is explicit.
- Keep regression coverage focused on safety and API contracts; remove redundant test additions.

### Fixed

- Prevent dry-run writes and cleanup of directories the generator does not own.
- Return failure exits for failed commands, audit errors, and unverifiable Git scope.
- Load root environment values without overriding exported shell values.
- Require explicit authorization for destructive database operations.
- Align Compose credentials, ports, readiness, and volume-preserving cleanup.
- Align generated controllers, primary keys, request aliases, pagination, and TypeScript clients.
- Validate model storage limits before writes; return not-found errors for missing foreign keys.
- Serialize generated Decimal responses consistently and reject invalid explicit null updates.
- Configure active frontend plugins and aliases; use a published, compatible TanStack devtools package.
- Use the reachable Django Matt starter and migrate its imports to `DjangoMattAPI`.
- Detect Django Matt's settings package and use its installed Granian server in production.
- Install Git for Git-based backend dependencies and fail builds when static collection fails.
- Select production Django settings explicitly and require separate Ninja signing secrets.

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
