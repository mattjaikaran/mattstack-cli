# mattstack TODO

This file lists open work only. Finished work is in `tasks/completed.md`.

Rules: no GitHub Actions budget, so all gates run locally. Do not generate
bulk tests. `AGENTS.md` and `DESIGN.md` live in the backend and frontend
components; the CLI does not invent a second copy.

## Next session: release process

- [ ] Make gate 10 (INSTALL) catch dependency breaks: build the sdist, build
  the wheel from it, install the wheel in a fresh venv without `uv.lock`,
  then run `mattstack --help`, one lazy group (`mattstack sync --help`), and
  a mistyped group that must print "Did you mean". The current check passed
  with the missing `click` dependency.
- [ ] Remove the `typer<0.26` cap: make `LazyTyperGroup` in
  `src/mattstack/cli.py` work without importing standalone `click`
  (`click.Context`, `click.Group`, `click.UsageError`). Do not import the
  private `typer._click`. Verify with the fresh-install check above on typer
  0.24.x and 0.27.x.
- [ ] Write the manual release steps in `docs/` (or a `make release`
  target): gates, sdist and wheel build from the tag, fresh-install smoke,
  `gh release create` with both files. No workflow publishes releases, so
  0.9.0 was tagged without one.

## Open bugs and gaps

- [ ] `mattstack hooks install` fails when Git `core.hooksPath` is set,
  because it runs `pre-commit install` without handling it
  (`commands/hooks.py`). `hooks status` also reads `.git/hooks` directly
  instead of the configured hooks directory.
- [ ] `init --graph age` exits 2 because the `apache/age` image has no
  pgvector (`commands/init_runtime.py`).
- [ ] Generated GitHub and GitLab CI use `postgres:N` for AI projects. Use the
  same `pgvector/pgvector:pgN` image as Compose (`commands/workflow.py`).
- [ ] Route parser: read class-level `auth=` on `@api_controller`; it now
  reads only per-endpoint auth (`parsers/django_routes.py`).
- [ ] `context full --watch` does not clear the terminal between emissions.
- [ ] Decide whether the generated Ninja controller should inherit
  `BaseController` and use `@handle_exceptions`, as music-django and
  lfts-django do. It now uses a plain `@api_controller` class.
- [ ] Frontend runtime (`tasks/prompt-frontend-runtime.md`): the proxy and
  TanStack Router fixes landed, but no record shows a route resolving on a
  real scaffold with the `frontend-dev` container running. Update the
  prompt's "not started" note.
- [ ] Done check: run `mattstack init -p starter-fullstack`, then
  `make setup`, `make gauntlet`, and `mattstack sync check`. Change one
  Pydantic field and confirm `sync check` fails before `sync openapi` and
  passes after.

### Test gaps

Check each item against the testing policy before you add it. Add a test
only for a consumer-visible contract.

- [ ] `generate model` without `--fields` or `--empty` fails.
- [ ] `generate model` creates `admin/{snake}_admin.py` and updates
  `models/__init__.py` and `admin/__init__.py`.
- [ ] Generated models inherit the base class and add no timestamp fields.
- [ ] Generated controllers use `@http_*` decorators.
- [ ] Generated `Update` and `Response` schemas follow the schema pattern.
- [ ] `generate crud` creates the hooks, list component, admin, `__init__`
  exports, and `--with-tests` files, and the Python output compiles.

## Blocked

- [ ] [Live deployments (#9)](https://github.com/mattjaikaran/mattstack-cli/issues/9):
  local provider inventory, schema, image, TLS, and production health checks
  pass. Live provider access, Flycast/IAM, public realtime routing,
  production secrets, and S3 provisioning are unverified. Keep the issue open
  until you supply and authorize those prerequisites. No billable deployment
  runs.
- [ ] PR #1, audit delegates to `gauntlet check --json`: draft, blocked until
  the Gauntlet binary ships. It deletes `auditors/`, but `main` has since
  added `auditors/types_parity.py` and `auditors/versions.py`; expect
  conflicts.
- [ ] When Gauntlet is released, replace `scripts/gauntlet.py` and the gate
  table in `CLAUDE.md` with thin wrappers, then delete the duplicate gate
  runners.
- [ ] Propose a generic Gauntlet check "generated files match source": run a
  command into a temporary directory and compare it with the committed
  output. mattstack would use it for OpenAPI, Zod, and SDK drift.
- [ ] Mateus frontend (Phase 15B) and the mateus-based `matt-fullstack` and
  `matt-b2b-fullstack` presets (Phase 15C): blocked until mateus is
  published. The current `matt-*` presets use `react-vite`.

## Known support boundaries

`generate endpoint` deliberately emits a documented 501 response until you
supply business logic. Linear, Jira, and Hermes board adapters remain explicit
stubs; use Axis or the disabled `none` backend. Do not call these existing
boundaries complete endpoint behavior or working third-party integrations.

## Backlog: new boilerplates (Phase 14)

None of these exist in `src/` (checked 2026-10-06).

### C# / ASP.NET

- Create `aspnet-boilerplate` repo — .NET 8, minimal API or controllers, EF Core, Identity
- Add preset: `starter-aspnet-api`
- Add preset: `starter-aspnet-fullstack` (with React frontend)
- Create `parsers/csharp_schemas.py` — parse C# classes with `[Required]`, `[StringLength]`, property types
- Extend type auditor for C# ↔ TypeScript cross-language checks
- Add `ProjectType.ASPNET_BACKEND` or handle via `backend_repo_key` routing
- Add deploy support: Docker, Azure App Service, AWS ECS

### Kotlin Android

- Create `kotlin-android-starter` repo — Jetpack Compose, MVVM, Retrofit, Room
- Add preset: `starter-android` (add to fullstack like iOS)
- Create `parsers/kotlin_schemas.py` — parse data classes with `@Serializable` annotation
- Extend type auditor for Kotlin ↔ Python/TS cross-language checks
- Add `config.include_android` flag (mirrors `include_ios` pattern)
- Wire into generators (similar to iOS flow)
- CI template for Android builds (GitHub Actions)

### React Native

- Create `react-native-starter` repo — Expo, TypeScript, React Navigation
- Add preset: `starter-mobile` (add to fullstack like iOS)
- Reuse existing TS parser (React Native is TypeScript)
- Existing TS/Zod auditor applies — no new parser needed
- Add `config.include_mobile` flag
- Add deploy support: EAS Build (Expo)
- Wire into generators (similar to iOS flow)

### Svelte / SvelteKit

- Create `sveltekit-boilerplate` repo — SvelteKit, TypeScript, form actions, load functions
- Add preset: `starter-sveltekit-fullstack` (SvelteKit + Django API)
- Add preset: `starter-sveltekit` (SvelteKit standalone)
- Create `parsers/svelte_schemas.py` — extract TS from `<script lang="ts">` blocks, Zod schemas
- Extend auditor for SvelteKit routes (`+page.server.ts`, `+server.ts`)
- Add `FrontendFramework.SVELTEKIT` enum value
- Add deploy support: Cloudflare, Docker, DigitalOcean

### Vue / Nuxt

- Create `nuxt-boilerplate` repo — Nuxt 3, TypeScript, auto-imports, composables
- Add preset: `starter-nuxt-fullstack`, `starter-nuxt`
- Create `parsers/vue_schemas.py` — extract TS from `<script setup lang="ts">` blocks
- Extend auditor for Nuxt routes (`server/api/**/*.ts`)
- Add `FrontendFramework.NUXT` enum value
- Add deploy support: Cloudflare, Docker, DigitalOcean

### Cross-cutting concerns for all new boilerplates

- Each new boilerplate needs a generator class (inherit BaseGenerator)
- Each needs Makefile targets added to `root_makefile.py`
- Each needs docker-compose service definitions where applicable
- Each needs README template additions
- Each needs CLAUDE.md template additions
- Type auditor `TYPE_COMPATIBILITY` dict needs language pair entries
- `NAME_CONVERTERS` dict needs language pair entries
- Tests for each new parser, generator, and preset
