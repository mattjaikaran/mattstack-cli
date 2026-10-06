# Completed work

This file holds finished work moved from `tasks/todo.md`. Open work stays in
`tasks/todo.md`.

## Verified on 2026-10-06 (formerly unchecked)

A code review on 2026-10-06 found these old unchecked items done on `main`,
or replaced by a later design. The original specifications are in the Git
history of `tasks/todo.md`.

### Phase 15A: django-matt backend support

- [x] `BackendFramework.DJANGO_MATT`, the `django-matt` source, the `matt-api`,
  `matt-fullstack`, and `matt-b2b-fullstack` presets, wizard choice, route
  parser, endpoint auditor, and codegen (`codegen/django_matt_api.py`).
- Obsolete: delegate to django-matt `sync_types`. `sync openapi` is
  backend-agnostic.

### Phase 16: generator correctness

- [x] Generated models inherit the policy base class (`AbstractBaseModel`,
  `TimestampedModel`, or soft-delete) and add timestamps only without a base
  (`codegen/django_models.py`).
- [x] FK targets must exist (`codegen/model_pk.py`); `model` needs `--fields`
  or `--empty`.
- [x] Controllers use `@api_controller` and `@http_*`. Writes use
  `model_fields` with `CamelCaseSchema` aliases on Ninja and `model_dump()` on
  django-matt; no `.dict()` remains.
- [x] Auto-wiring: `models/__init__.py`, per-model `admin/{snake}_admin.py`
  (Unfold when installed), `admin/__init__.py`, `api.register_controllers`,
  and a post-generation summary with next steps.
- [x] `generate endpoint` emits `@http_{method}`, creates or appends to the
  controller that serves the prefix, and adds `auth=JWTAuth()` with `--auth`.
  It returns a documented 501 until you add logic.
- [x] Schemas: `Base`, `Create`, `Update`, and `Response` with
  `from_attributes=True`. `Update` fields are omittable but reject null.
- Obsolete: `limit`/`offset` pagination (replaced by
  `@paginate(PageNumberPaginationExtra)`), endpoint response-type detection
  (the endpoint returns 501), and a `.model_dump()` regression test.

### Phase 17: `generate crud`

- [x] `generate crud` plans the backend model, schemas, controller, admin, and
  tests, and the frontend API client, TanStack Query hooks, list component,
  router-specific page (TanStack, React Router, or Next.js), and Vitest test
  (`codegen/crud_backend.py`, `codegen/crud_frontend.py`).

### Phase 18: AI agent context

- [x] `context` sub-app with `stack`, `models`, `routes`, `types`, and `full`;
  `--format claude|json|markdown`; token estimate; `--max-tokens`.
- [x] Model and route parsers: `parsers/django_models.py` and
  `@api_controller`/`@http_*` support in `parsers/django_routes.py`.
- [x] `context full --watch` re-emits on changes with a timestamp. It polls
  file mtimes instead of using `watchfiles`, so it adds no dependency.
- [x] Tests for `context models`, `context routes`, the Claude format, and the
  token estimate.

### Phase 20: parallel `lint` and `test`

- [x] `utils/jobs.py` runs labeled jobs with `ThreadPoolExecutor` and streamed
  `Popen` output, and returns failure when any job fails. Tests cover
  concurrency and exit codes.

### Phase 21: test coverage

- [x] Tests exist for `commands/workflow.py` and `commands/hooks.py`.
- [x] The suite exceeds 700 tests.

### Open work (2026-09-12)

- Obsolete: split `commands/sync.py`. The file is 46 lines after the
  OpenAPI cutover.
- [x] Generated `make gauntlet` runs `mattstack audit --no-todo`
  (`templates/root_gauntlet.py`).
- Obsolete: the "pre-existing gate failures" table. All files are under the
  400-line limit, the quick gauntlet passes eight gates, and hosted CI is gone.

## Historical gauntlet findings (2026-07-25)

The first run passed three of eight quick gates. The merged PR #14 and the
post-merge CLI fixes pass all eight. Use the
[merged main audit](#merged-main-audit-pr-14) for current findings and blockers.
Treat the older feature phases below as historical plans, not the current
issue-status list.

- [x] Resolve format, lint, typecheck, security, and file-length failures.
- [x] Preserve architecture and installation checks.
- [x] Re-enable CI for pushes and pull requests.

## Phase 1: Foundation

- pyproject.toml, .gitignore, CLAUDE.md, Makefile, LICENSE
- config.py — enums, ProjectConfig, REPO_URLS
- presets.py — preset definitions
- utils/console.py — Rich helpers
- utils/git.py — clone, init, commit
- utils/docker.py — detection helpers
- utils/process.py — subprocess runner
- **init**.py, **main**.py

## Phase 2: Templates

- templates/root_makefile.py
- templates/docker_compose.py
- templates/docker_compose_prod.py
- templates/root_env.py
- templates/root_readme.py
- templates/root_gitignore.py
- templates/root_claude_md.py

## Phase 3: Generators

- generators/base.py
- generators/backend_only.py
- generators/frontend_only.py
- generators/fullstack.py
- generators/ios.py

## Phase 4: Post-Processors

- post_processors/customizer.py
- post_processors/frontend_config.py
- post_processors/b2b.py

## Phase 5: Commands + CLI

- commands/doctor.py
- commands/info.py
- commands/init.py
- cli.py
- utils/yaml_config.py

## Phase 6: Polish

- README.md
- Tests (22 passing)
- E2E verification (all 4 preset types)
- Lint clean (ruff)

## Phase 7: Audit Command

- parsers/ — 5 regex-based parser modules
- auditors/base.py — data model (AuditFinding, AuditConfig, BaseAuditor)
- auditors/quality.py — TODOs, stubs, debug, credentials
- auditors/types.py — Pydantic ↔ TS/Zod comparison
- auditors/endpoints.py — route analysis + live probing
- auditors/tests.py — coverage gaps + feature mapping
- auditors/report.py — Rich tables + idempotent todo.md writer
- commands/audit.py — orchestrator
- cli.py — audit command wired
- Tests (48 passing — 26 new)
- E2E: audit on starter-fullstack produces 476 findings across all 4 domains
- E2E: idempotent todo.md re-write verified
- E2E: JSON output validated
- README.md — full rewrite with audit docs
- CLAUDE.md — expanded with file map, patterns, workflows

## Phase 8: Codebase Improvements (completed)

- Fix STUB_RE duplicate regex, doctor exit code, _validate_clone return value
- Refactor generators to ABC base class with shared run() loop
- Add --severity/-s filter to audit command
- Make extract_block string-aware for TS/Zod parsing
- Document DeploymentTarget enum as partially implemented
- Add --quiet/-q flag for CI-friendly output
- Add 25 tests for post-processors, iOS, docker utils, yaml edge cases (227 total)

## Phase 9: Tier 1 — Game-Changers (completed)

- `mattstack add` — expand existing projects in-place (add frontend/backend/ios)
- `mattstack upgrade` — pull latest boilerplate changes into existing project
- Deployment target scaffolding (Railway, Render, Cloudflare, DigitalOcean configs)

## Phase 10: Tier 2 — High-Value Polish (completed)

- Conditional template cleanup — templates 100% conditional on feature flags
- Dependency/version compatibility auditor (pyproject.toml + package.json)
- Pre-commit hooks auto-setup (.pre-commit-config.yaml with ruff + prettier)

## Phase 11: Tier 3 — Differentiators (completed)

- Audit HTML dashboard export (`--html` flag, browsable report, inline CSS/JS)
- Plugin system for custom auditors (load from ./mattstack-plugins/)
- docker-compose.override.yml template for per-developer customization
- iOS generator customization (rename MyApp references)
- YAML config mode E2E test (8 tests covering all config paths)

## Phase 12: Client Command & Agent DX (completed)

- `utils/package_manager.py` — detect PM from lockfiles, abstract bun/npm/yarn/pnpm
- `commands/client.py` — `mattstack client add/remove/install/run/dev/build/exec/which`
- `commands/context.py` — dump project context as markdown/JSON for AI agents
- Wire `client` subcommand group + `context` command into `cli.py`
- `user_config.py` — support `package_manager` preference (bun/npm/yarn/pnpm)
- Tests: 51 new tests (package_manager util, client command, context command)

## Phase 13: Tooling & DX Enhancements (completed)

- `commands/dev.py` — unified `mattstack dev` (docker + backend + frontend)
- `commands/test.py` — unified `mattstack test` (pytest + vitest, parallel mode)
- `commands/lint.py` — unified `mattstack lint` (ruff + eslint, --fix, --format-check)
- `commands/env.py` — `mattstack env check/sync/show` (.env management)
- `commands/version.py` — version display + PyPI update check
- `commands/completions.py` — shell completion installer (bash/zsh/fish)
- README.md — document all new commands, client, context, --quiet, --html, vulnerabilities
- CLAUDE.md — updated file map and CLI reference
- Tests: 81 new tests (586 total)

## Phase 14: Next.js (App Router)

- Create `nextjs-starter` repo (in progress externally)
- Add `FrontendFramework.NEXTJS` enum + `is_nextjs` property
- Add `nextjs` to `REPO_URLS`
- Add presets: `nextjs-fullstack` (Next.js + Django API), `nextjs-frontend` (standalone)
- Add Next.js to interactive wizard choices
- Create `parsers/nextjs_routes.py` — parse App Router routes (`page.tsx`, `route.ts`)
- Extend endpoint auditor for Next.js API routes
- Next.js-aware templates: Makefile, docker-compose, env, readme, claude_md
- Next.js monorepo post-processor (next.config.monorepo.ts, .env.local)
- Removed Vercel, added Cloudflare + DigitalOcean deploy targets
- Upgrade command detects Next.js frontend (via next.config markers)
- docker-compose.override template uses correct env var prefix
- Doctor command uses generic "Frontend dev server" label
- 45 new tests (454 total)

## Phase 19: `sync api-client` Mutations + Pagination (completed)

- `useMutation` hooks for POST/PUT/DELETE/PATCH with `useQueryClient` + `onSuccess` invalidation
- Infer request body types from `{Model}CreateSchema` / `{Model}UpdateSchema` naming convention
- `invalidateQueries({ queryKey: ['{snake}s'] })` in mutation `onSuccess`
- Paginated list variant: `use{Pascal}List(page, pageSize)` with `keepPreviousData`
- `ApiError` interface exported in generated file
- `--base-url` flag override (defaults to `http://localhost:8000`)
- Dynamic TanStack Query imports (useQueryClient, keepPreviousData) only when needed
- 25 tests (691 total)

## Phase 22: README + Public Impression (completed)

The README didn't show what the tool actually produces. Fixed.

- [x] Add "What gets generated" section with full example output of `generate crud Product --fields "name:str price:decimal"` — show the actual files + content
- [x] Animated terminal demo deferred (SVG/asciicast requires external tooling)
- [x] `upgrade` and `health` were already in the commands table
- [x] Add "AI Agent Integration" section explaining `mattstack context --format claude` and how to pipe into Claude Code
- [x] Add comparison table: vs cookiecutter-django, vs django-startproject, vs manual setup
- [x] Add badges: Python 3.12+, license, test count
- [x] Add "why this?" one-paragraph summary at top
- [x] Document `generate crud` as the headline command with a full example

## CLI remediation (2026-09-30)

Fix command and generated-project behavior before adding verification tools.
Keep the standalone Gauntlet migration in PR #1 separate.

- [x] Incorporate and verify PR #4's dry-run guards, then close the superseded PR.
- [x] Return nonzero for failed initialization, audit errors, missing environment variables, and failed upgrades.
- [x] Fail scope verification when Git discovery fails; handle renamed and unusual paths.
- [x] Emit raw structured output; keep diagnostics on stderr and escape dynamic terminal text.
- [x] Preserve stack metadata in `mattstack.yml`; resolve the same project from nested directories.
- [x] Load root environment values for host commands; preserve explicit shell overrides.
- [x] Authorize database destruction explicitly and validate seed inputs before a flush.
- [x] Supervise development processes; separate host and container execution modes.
- [x] Resolve health checks from actual services and configured ports.
- [x] Align Compose credentials, readiness, API prefixes, and image ports.
- [x] Preserve database volumes in routine cleanup.
- [x] Preserve existing project files during add/upgrade unless replacement is explicit.
- [x] Compile generated CRUD and sync artifacts; align controllers, schemas, routes, aliases, and mutation payloads.
- [x] Configure the active frontend bundler without removing router plugins or aliases.
- [x] Honor noninteractive command requirements, parallel formatting checks, and documented field syntax.
- [x] Evaluate optional React Doctor, API-contract, frontend-analysis, and Django-development tools.
- [x] Exercise real CLI commands, generated TypeScript, rendered routes, and Docker/Postgres integration.
- [x] Update command documentation and the changelog with verified behavior.

Verification: the reduced pytest suite passes. Ruff, mypy, architecture, file
length, and editable installation checks pass. The quick gauntlet still fails
its Bandit gate; the existing security-gate debt remains above.

Runtime proof: scaffold and install Django Ninja/Kibo, standalone Vite, and
Django Matt projects. Run Django checks and Postgres migrations. Exercise the
generated SDK's create/read/update/delete calls, Decimal wire format, integer
foreign keys, null rejection, and storage-limit errors. Observe rendered
Rsbuild/Vite routes. Generate and compile a real OpenAPI SDK and check drift.
React Doctor completes without skipped checks: no errors and nine warnings.

Keep only essential safety and data-contract regressions. Remove redundant
diagnostic, forwarding, framework-matrix, source-wording, and optional skipped
tests. Do not add a per-field generated test matrix. Keep PR #1 unchanged;
PR #4 is closed. Preserve the user's existing README edits.

Public-release review caught and fixed the Django Matt production image's
missing Git executable, wrong server, and wrong settings package. Select
production Django settings explicitly; require distinct runtime signing secrets.
Do not hide static collection errors. Both Django production images build and
serve their API surfaces; verify Django Ninja uses production settings with
`DEBUG=False`. Push grouped commits to a feature branch and PR, not directly
to main, as selected by the user.

## Merge readiness and boilerplate contracts (2026-10-01)

- [x] Scan the local Vite/TanStack, Rsbuild/Kibo, React Router starter/b2b, and
      Django Ninja source contracts with scoped subagents.
- [x] Declare mypy as a development tool and use locked, explicit CI interpreters.
- [x] Implement TanStack route inventory and shared route IDs, React Router
      page/CRUD registration, and dependency-gated Next.js API discovery.
- [x] Implement Ninja camelCase schemas, field-name ORM writes, package exports,
      required cache services, and production environment modes.
- [x] Preserve optional Django apps during cleanup and accept documented audit filters.
- [x] Record follow-up issues instead of inferring app authorization or adding
      unrelated service and deployment capabilities.

Keep the security gate blocking at every severity. The user selects exact,
documented waivers for reviewed findings; do not lower thresholds or add global
rule skips. Bind development host ports to loopback. Trust project scripts,
dependencies, hooks, PATH, and environment before executing them.

Verification: run all eight quick gauntlet gates with the strict security policy.
Install locked development tools in clean Python 3.12 and 3.13 environments.
Build and observe generated TanStack/Vite, React Router/Vite, and Kibo pages;
check signed-out protected-route redirects. Build generated Ninja CRUD and
exercise camelCase Decimal/FK writes, partial updates, null rejection, package
imports, Postgres migrations, and Redis cache access. Keep Next.js page generation.
Build and serve the Ninja production image with `DEBUG=False` and both production
mode variables. Exclude dotenv secrets and the host virtual environment from its
Docker context; verify their absence in the image. Serve `/api/docs` successfully.
CI exposes a machine-dependent doctor test that assumes all tools exist. Replace
that assumption with an isolated missing-tool regression. Run the actual CLI with
an empty tool PATH: return failure for required Bun and keep Docker optional for
a frontend-only project.

### Next work

- [x] [Resource ownership, service layers, and model lifecycle (#6)](https://github.com/mattjaikaran/mattstack-cli/issues/6):
      real two-user JWT/HTTP proof covers owner binding, cross-user 404, Decimal writes,
      global reads/writes, timestamp updates, and soft-delete retention/deleted_by.
- [x] [Task backends (#7)](https://github.com/mattjaikaran/mattstack-cli/issues/7):
      all five workers consume real queued jobs; none rejects dispatch without enqueueing.
- [x] [Realtime profile (#8)](https://github.com/mattjaikaran/mattstack-cli/issues/8):
      authenticated websocket subscribe/publish/history works; forged and cross-user tokens fail.
- Open, tracked in `tasks/todo.md`: [Deployment contracts (#9)](https://github.com/mattjaikaran/mattstack-cli/issues/9):
      local production TLS/startup/admin/static and provider schema checks pass.
      Keep open: live provider deployment/Flycast/IAM checks need authorized accounts.
- [x] [Advanced routing (#10)](https://github.com/mattjaikaran/mattstack-cli/issues/10):
      custom TanStack tokens/groups/dynamic routes, guards/pending/errors, React Router
      data/lazy transitions, and grouped Next.js CRUD build and navigate.
- [x] [Frontend source drift (#11)](https://github.com/mattjaikaran/mattstack-cli/issues/11):
      publish the reviewed source fixes and verify fresh-clone typechecks,
      builds, and browser pages. Keep unrelated source edits and the backup.
- [x] [Backend quality tooling (#12)](https://github.com/mattjaikaran/mattstack-cli/issues/12):
      publish canonical gate fixes and verify fresh-clone root hooks and
      `cd backend && just gauntlet-quick`. Report warnings separately.
      Leave Ninja PR #1 untouched.
- [x] [OpenAPI and optional S3 setup (#13)](https://github.com/mattjaikaran/mattstack-cli/issues/13):
      real schema export generates a compiling local Hey API client; actual Django S3
      storage uploads and independent reads succeed through production Compose.

### Published source checks

- React Vite's source convention check reports zero findings. Its fresh-clone
  typecheck and build pass; all four settings tabs load in Chromium.
- Kibo uses real Ninja login, registration, refresh, and logout. Its fresh-clone
  strict lint, typecheck, and build pass. Real HTTP/browser proof covers an
  authenticated account, reload, a 401 followed by refresh and retry, rejected
  credentials, and logout that revokes refresh and clears shared token storage.
- React Vite Starter's published source contains neither `src/routeTree.gen.ts`
  nor `.tanstack`. Its typecheck/build pass; home and login pages load.
- B2B's `/organizations?create=1` opens its registered create form.
  Next.js's production `/todos` redirects signed-out users to `/login` without
  a prerender exception. Both fresh-clone typechecks/builds pass.
- Ninja's explicit sibling-frontend scan reports 62 existing parity/naming/rule
  findings without a path traceback or dependency-tree scan. Keep them visible;
  a successful blocking-gate run is not an all-clear cross-stack result.
- Preserve the user's stale starter route-tree backup at
  `~/dev/mattstack-source-backups/issue-11/react-vite-starter/src/routeTree.gen.ts`.
- Review intentionally global public GETs in Ninja's `PUBLIC_OPERATIONS` before
  pushing. Generation prints exact paths and the security-test file; it never
  adds an automatic security waiver.

### Earlier follow-up checks

- CLI `make gauntlet-quick`: all eight gates pass, including strict mypy,
  all-severity Bandit, architecture, the 400-line limit, tests, and installation.
- Generated backend quality hook: all blocking gates pass after normal migration
  formatting and explicit review of the fixture's global public reads.
- Preserve backend-only/fullstack success and dry-run regression coverage.
  Apply the TLS health patch only to targets that require TLS; a missing
  production settings file on an HTTPS target fails with its exact path.
- Local verification commands include provider-controlled TLS mode. The real
  container preflight rejects missing TLS mode and accepts the corrected override.
- Kibo's pinned React Doctor runs under supported Node 22 without telemetry or
  supply-chain checks: zero errors and 25 warnings. Keep those warnings visible.
- Backend `check --deploy` uses the proof's test settings and prints five security
  warnings. Do not treat this gate as production security approval. The separate
  production-image smoke verifies TLS redirects, host checks, HSTS, and health.
- Publish only reviewed owning-source paths. The publication evidence below
  replaces the earlier fixture-only proof; preserve unrelated source changes.

### Documentation review for PR #14

- [x] Separate the CLI's init/generation flow from a selected project's runtime.
- [x] Replace the all-framework architecture diagram with one selected API and UI.
- [x] Explain task backends, access policies, routing, deployment prerequisites,
  source provenance, lock updates, and trusted plugin behavior.
- [x] Render seven Mermaid diagrams in Chromium and check local Markdown links.
- [x] Exercise scaffold and model dry-runs, inspect actual CLI help, and run the
  documented plugin against an isolated source fixture.
- Keep the user's existing README source-link edits outside the documentation
  commit. Preserve their bytes in the working tree.

## Merged main audit (PR #14)

### Scope and verified state

- Pull main at merged commit `a03fc4bd4b39006c2615d9e09595615f4a34c270`.
  Its GitHub CI run `36939023792` succeeds. The user authorizes the audit fixes
  directly on main; do not create another pull request.
- Run the final `make gauntlet-quick`: eight gates pass, zero fail. Keep Bandit
  blocking at every severity. The focused dependency/package-manager suite
  passes 59 tests. Two upstream Typer/Click deprecation warnings remain visible.
- Exercise all 79 registered CLI help surfaces after the lock refresh: zero
  command failures. Run actual dependency commands, not mocked success reports.
- Scaffold `starter-api` from the published GitHub source with disabled tasks,
  realtime, and S3. Development Compose resolves API, Centrifugo, PostgreSQL,
  and Redis, with no worker/beat. Keep Centrifugo's configuration after cleanup.
  Metadata contains the selected profile, not its runtime secrets.
- Production Compose refuses empty required realtime credentials with the exact
  `CENTRIFUGO_API_KEY` name. Do not treat a missing-secret refusal as a live
  provider deployment or S3 upload proof.
- Exercise escape/colliding Next.js routes and an owned model without an owner
  field. Each command refuses the request without writing files.
- Reuse the merged PR's real two-user HTTP, five-worker, authenticated websocket,
  route/browser, OpenAPI, and production S3 proof. Keep their source-fixture
  limits explicit. Read-only review agents could not start because their model
  service returned HTTP 429; this audit uses inline review, not a peer-review claim.

### Fixed during this audit

- [x] [FastAPI broker divergence (#15)](https://github.com/mattjaikaran/mattstack-cli/issues/15):
  use broker database 1 and result database 2 in both environment-file and
  Compose modes. A real isolated Redis/Kombu producer and host consumer exchange
  and acknowledge the marker; a result round-trip succeeds. Django keeps database 0.
- [x] [Incomplete dependency reports (#16)](https://github.com/mattjaikaran/mattstack-cli/issues/16):
  return failure for missing tools, failed scans, malformed/skipped dependency
  records, and vulnerabilities. Do not let a clean frontend hide backend failure.
  Select the backend interpreter, not a global auditor executable. A reproduced
  external auditor scanned 164 packages for an empty backend; the corrected
  command refuses its missing local module. Audit without syncing: a real Huey
  extra stays importable and its lockfile remains byte-identical.
- [x] [Locked Python advisories (#22)](https://github.com/mattjaikaran/mattstack-cli/issues/22):
  refresh existing Click to 8.5.0, Pygments to 2.21.0, and pytest to 9.1.1; add no
  dependencies. The prior service response contains three distinct advisories
  across three packages, with duplicate records. The actual CLI environment
  now audits 35 packages with exit 0 and zero findings. Skip only the editable
  application package; this scan does not establish exploitability or approve
  unscanned owning-source JavaScript dependencies.
- Correct the README's `dev --mode container` example and remove stale command,
  preset, repository, and test totals from developer guidance. Preserve the
  user's separate README source-link rows outside the commit.

### Completed follow-up audit (2026-10-02)

- [x] [Selected extras (#17)](https://github.com/mattjaikaran/mattstack-cli/issues/17):
  resolve declared runtime and development extras/groups before syncing.
  A real isolated dependency update preserves the selected Huey and quality
  imports and removes an unselected obsolete extra. Reject undeclared selections
  before changing the lockfile. Use the same resolution in generated setup.
- [x] [NestJS dependencies (#18)](https://github.com/mattjaikaran/mattstack-cli/issues/18):
  dispatch backend checks, updates, and audits through its JavaScript manager.
  Actual Bun operations pass for the isolated NestJS manifest. Preserve
  component-only selection and labels; a passing frontend cannot hide API failure.
- [x] [Scaffold defaults (#19)](https://github.com/mattjaikaran/mattstack-cli/issues/19):
  remove unsupported scaffold settings from the public user-config template.
  Keep only the package-manager default. Init retains its preset, YAML, and
  explicit-flag behavior. Isolated-HOME command proof verifies invalid selected
  defaults fail while explicit choices and detected lockfiles retain precedence.
- [x] [Full-gate tooling (#21)](https://github.com/mattjaikaran/mattstack-cli/issues/21):
  provision pinned tools using the selected project interpreter and its installed
  packages, without adding runtime dependencies. The actual audit gate exits 0.
  Mutation starts with project development tools but exceeds the 600-second
  deadline: exit 124, no completed mutation score and no pass claim.
  A real one-second process-tree timeout returns 124 and cleans up its children.
- [x] [Source publication (#11)](https://github.com/mattjaikaran/mattstack-cli/issues/11):
  publish React Vite `32b1b52`, B2B `408efb6`, Next.js `9a0f2a0`, and Kibo
  `e141d9c` plus runtime guidance `ae9f401`. Starter already publishes the clean
  source at `ca2226767d0b21623b766319174659e0903d426a`.
  Run frozen installs, each source typecheck/build, and actual browser navigation.
  Vite/B2B routing fixtures do not claim backend authentication.
- [x] [Kibo authentication (#20)](https://github.com/mattjaikaran/mattstack-cli/issues/20):
  publish the real Ninja contract in Kibo `e141d9c`; remove mock credentials and
  credential logging. Verify the published source against an actual newly
  generated Ninja API, including account creation, login, reload, refresh, and
  logout with rejected replay of the revoked refresh token.
- [x] [Canonical quality gates (#12)](https://github.com/mattjaikaran/mattstack-cli/issues/12):
  publish Ninja `35e8629`, `b487220`, `c1158fd`, and `b95a40b`.
  Scaffold again from GitHub after publication, run `make setup`, install root
  hooks through the CLI, and invoke the actual pre-push entry with a real ref
  range: exit 0. Run `cd backend && just gauntlet-quick`: 241 tests pass;
  cross-stack and development deployment checks remain explicit warnings.
  Retain canonical rule/skill sources and remove duplicate harness adapters.
  Remove the obsolete Compose source-text test in its owning source and delete
  the CLI's test-rewriting workaround. Do not merge or change Ninja PR #1.

## Final CLI verification (2026-10-02)

- Run `make gauntlet-quick` after the source cutover and final formatting:
  all eight gates pass, zero fail. Keep all-severity Bandit blocking.
- The focused dependency, package-manager, user-config, runtime-profile, and
  template suite passes 450 tests with two upstream Typer/Click warnings.
- Stop owned browser/API proof services and remove temporary clones, launchers,
  and mutation artifacts. Preserve the user's README edits, source working-tree
  changes, stash `320b7c21af0fe5ffa7cc675bcdacf0bb186557f2`, and starter backup.

## Release v0.8.0 (2026-10-02)

- Set package, module, and lockfile versions to `0.8.0`; retain dependency pins.
- Move Unreleased entries into the dated release and remove the obsolete
  consolidation-test workaround entry. Keep deployment and mutation limits.
- Build the sdist and wheel from a clean staged snapshot. Use the committed
  README in both artifacts; exclude the user's uncommitted source-link edits.
- Install the wheel in an isolated environment. Verify package/module version
  `0.8.0`, root help, preset info, a no-write dry-run, and a real `starter-api`
  scaffold from the published source with its emitted backend Dockerfile.
- Run the release quick gauntlet: eight gates pass, zero fail.
- Publish the annotated tag and GitHub release with both artifacts only after
  the release commit passes CI. Do not claim a PyPI publication.

## 2026 environment hardening (completed items)

### Local gates, no CI

- [x] Stop generating GitHub/GitLab workflows by default. Make
  `mattstack workflow` opt-in (`--ci github|gitlab`) and print a warning that
  it costs minutes.
- [x] Remove `.github/workflows` from this repo and configure a `pre-push`
  hook that runs `make gauntlet-quick` (`d2207c9`). The open
  `core.hooksPath` problem stays in `tasks/todo.md`.
- [x] Generate a root `make gauntlet` that calls the backend `just gauntlet`
  and the frontend `bun run gauntlet`, then `mattstack sync check`.

### Agent files (no new duplication)

- [x] Emit a root `AGENTS.md` that only points to `backend/AGENTS.md` and
  `frontend/AGENTS.md` and lists cross-stack rules (types flow
  backend → frontend; run `sync` after any schema change). Make `CLAUDE.md`
  a one-line pointer to it. Keep `.cursorrules` as an adapter only.
- [x] Stop deleting component `.claude/` skills in
  `post_processors/consolidate.py` if they are the committed copy; only drop
  files that duplicate `AGENTS.md`.
- [x] Emit `.mcp.json` with servers that exist in both components, and a
  `.claude/settings.json` that blocks `git push` and `rm -rf`. Never emit
  `settings.local.json`.
- [x] Add the testing policy line to the root `AGENTS.md`: tests only for bug
  fixes, changed contracts and permission or boundary rules.
- [x] Fix hardcoded "React 18" and "PostgreSQL 17"/"Redis 7" strings in
  `templates/root_claude_md.py` (now `root_agents_md.py`): read versions from
  the cloned lockfiles. `root_readme.py`, `gsd_project.py`, and
  `stack_facts.py` still carry them.

### Two-language type safety

Goal: Pydantic and Zod schemas cannot drift.

- [x] Make OpenAPI the contract: `sync openapi` is the default path.
  Flow: backend export → `@hey-api/openapi-ts` (types, SDK, Zod plugin,
  TanStack Query plugin) → commit generated files.
- [x] Demote the regex path (`sync types|zod|api-client`) to a deprecated
  alias that calls `sync openapi`; delete the regex generators and
  `parsers/python_schemas.py` after the cutover. Remove the "no AST" rule
  from `CLAUDE.md` in the same change.
- [x] Add `mattstack sync check`: regenerate to a temp dir and fail on diff
  with the committed files (`--check` mode already exists for `sync
  openapi`; extend it to Zod and SDK output).
- [x] Add a parity audit (`auditors/types`): compare each OpenAPI schema with
  the generated Zod schema for fields, required-ness, nullability, enums,
  `min`/`max`/`pattern`. Fail on mismatch with an `AuditFinding`.
- [x] Pin `@hey-api/openapi-ts` and plugins to exact versions in the
  frontend `package.json`; stop `bun add -D` on demand in Makefiles.
  Done CLI-side: `init` pins 0.99.0 and `sync openapi|check` reject a range.
  Frontend boilerplate Makefiles are edited in the frontend repos.
- [x] Add a round-trip test fixture: one backend schema using alias,
  `Optional`, enum, `Literal`, nested model, `Decimal`, `datetime`, and
  constraints; assert the generated Zod matches. This is the one permanent
  test for this feature.
- [x] Document the known gaps (Decimal as string, datetime format, int64) and
  the chosen mapping in `docs/architecture.md`.

### Version drift

- [x] Single source of versions: read from backend `pyproject.toml`/`uv.lock`
  and frontend `package.json`. Generated pre-commit uses `repo: local` hooks
  that run the project's own tools, so ruff v0.8.6-style pins disappear.
- [x] Add `mattstack audit --versions`: ruff, mypy, python, bun, node,
  postgres, valkey/redis, React, Tailwind, Zod across components; report
  mismatches.
- [x] Update `dockerfiles.py`: pin uv through `COPY --from=ghcr.io/astral-sh/uv`,
  non-root user and healthcheck on the frontend image, drop `bun:latest`.
- [x] Replace the mailhog image with a maintained one (`axllent/mailpit`).
- [x] Switch the DB service to `pgvector/pgvector:pg17` when the AI add-on is
  selected.

### Preset and scaffold changes

- [x] API-only backend: drop SPA-serving config and `npm` targets from the
  generated Makefile (`bun` only). Frontend runs as its own service.
- [x] Add `--ai pgvector|qdrant` and `--graph cte|neo4j`, mapped to the
  backend Compose profiles. The open `--graph age` and CI image items stay
  in `tasks/todo.md`.
- [x] Add `mattstack upgrade`: show and apply boilerplate changes to an
  existing project (three-way against the recorded commit in `mattstack.yml`).
- [x] Extend `mattstack doctor`: uv, bun, Docker, `just`, pre-push hook
  installed, MCP servers reachable.
- [x] After Oxlint/Oxfmt landed, generated pre-commit, `frontend-*` Makefile
  targets, and CI call `bun run lint` and `bun run format[:check]` through
  `templates/frontend_commands.py` (verified 2026-10-06).

### Gauntlet integration

Decision: mattstack stays Python. No second Rust CLI. No scaffolding inside
Gauntlet, which is a language-agnostic verifier (agent never grades itself).
Reconsider Rust only if startup latency or single-binary distribution
becomes a real problem.

- [x] Generate a `gauntlet.toml` into scaffolded projects that wraps the
  existing local gates: backend `just gauntlet-quick`, frontend
  `bun run gauntlet`, and `mattstack sync check`.
- [x] Cut import time: lazy-import Typer subcommands, Rich and questionary.
  Measure `mattstack --help` before and after: 237 ms → 140 ms (hyperfine,
  20 runs). Subcommand groups load lazily; questionary already loads only in
  `init`; Rich stays because Typer renders help with it.

## Release v0.9.0 (2026-10-06)

- Set package, module, and lockfile versions to `0.9.0`; `uv lock --check`
  passes.
- Rebase onto upstream `31e9b2d` (React tooling) and fold its changelog
  entries into 0.9.0; reformat `tests/test_commands/test_lint.py`.
- Move Unreleased entries into the dated release; keep the Breaking entries
  for `workflow --ci`, the OpenAPI-only `sync`, and the `AGENTS.md` import.
- Full gauntlet: nine gates pass; mutation exceeds its 600 s gate timeout
  (35,355 mutants, about 13,000 run). Quick gauntlet after the rebase:
  eight gates pass.
- Push and tag only after the django-ninja-boilerplate `v1.13.0` tag exists
  and a `starter-fullstack` init from GitHub sources passes. No PyPI release.
- No GitHub release for `v0.9.0`: fresh installs fail. See v0.9.1.

## Release v0.9.1 (2026-10-06)

- Fix: `cli.py` imports `click`, but only `typer` installed it. Typer 0.26
  vendors Click (`typer._click`) and drops the dependency, so fresh 0.9.0
  installs crashed with `ModuleNotFoundError: No module named 'click'`.
  The lock pins typer 0.24.1, so the gates did not catch it.
- Declare `click>=8.0.0`; cap `typer>=0.12.0,<0.26` (0.25.x still needs
  Click).
- Smoke: a fresh, unlocked wheel install (typer 0.25.1, click 8.5.0) passes
  help, `info`, `sync --help`, the lazy-group typo suggestion, and a no-write
  `init -p starter-api --dry-run`. Quick gauntlet: eight gates pass.
- Published the GitHub release with the wheel and sdist. No PyPI release.
