## Historical gauntlet findings (2026-07-25)

The first run passed three of eight quick gates. The merged PR #14 and the
post-merge CLI fixes pass all eight. Use the
[merged main audit](#merged-main-audit-pr-14) for current findings and blockers.
Treat the older feature phases below as historical plans, not the current
issue-status list.

- [x] Resolve format, lint, typecheck, security, and file-length failures.
- [x] Preserve architecture and installation checks.
- [x] Re-enable CI for pushes and pull requests.

---

# mattstack TODO

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

---

## Phase 14: New Boilerplate Support

### Next.js (App Router) — DONE

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

---

## Phase 16: Generator Correctness + Real Pattern Alignment

Audit of real apps (music-django, lfts-django) revealed the current `generate` command produces code that doesn't match actual project conventions. These must be fixed before any new features ship.

### Reference Architecture (from music-django + lfts-django)

Both apps share these invariants — generated code must match:

**Stack:** `django-ninja` + `django-ninja-extra` + `django-ninja-jwt`. Controllers use `@api_controller`, `@http_get`, `@http_post`, `@http_put`, `@http_delete` from `ninja_extra`. NO `@router.get` / `@router.patch` patterns — those are vanilla django-ninja, not ninja-extra.

**Controller class pattern:**
```python
from ninja_extra import api_controller, http_get, http_post, http_put, http_delete
from core.controllers.base_controller import BaseController, handle_exceptions
from core.auth import JWTAuth, OptionalJWTAuth

@api_controller("/{snake}s", tags=["{Pascal}"])
class {Pascal}Controller(BaseController):
    @http_get("/", response=list[{Pascal}Schema])
    @handle_exceptions()
    def list_{snake}s(self, request, search: str | None = None, limit: int = 20, offset: int = 0):
        ...
    
    @http_get("/{{{snake}_id}}", response={200: {Pascal}Schema, 404: dict}, auth=OptionalJWTAuth())
    @handle_exceptions()
    def get_{snake}(self, request, {snake}_id: UUID):
        ...
    
    @http_post("/", response={201: {Pascal}Schema, 400: dict}, auth=JWTAuth())
    @handle_exceptions(success_status=201)
    def create_{snake}(self, request, payload: {Pascal}CreateSchema):
        obj = {Pascal}.objects.create(**payload.model_dump())  # NOT .dict()
        return obj
    
    @http_put("/{{{snake}_id}}", response={200: {Pascal}Schema, 403: dict}, auth=JWTAuth())
    @handle_exceptions()
    def update_{snake}(self, request, {snake}_id: UUID, payload: {Pascal}UpdateSchema):
        obj = get_object_or_404({Pascal}, id={snake}_id)
        for attr, value in payload.model_dump(exclude_unset=True).items():
            setattr(obj, attr, value)
        obj.save()
        return obj
    
    @http_delete("/{{{snake}_id}}", response={204: None}, auth=JWTAuth())
    @handle_exceptions()
    def delete_{snake}(self, request, {snake}_id: UUID):
        obj = get_object_or_404({Pascal}, id={snake}_id)
        obj.delete()
        return 204, None
```

**Admin structure:** `APP_NAME/admin/{model_name}_admin.py` (one file per model, NOT a single `admin.py`)
```python
# APP_NAME/admin/product_admin.py
from django.contrib import admin
from unfold.admin import ModelAdmin

@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ["name", "price", "created_at"]
    list_filter = ("created_at",)
    search_fields = ("name",)
    readonly_fields = ("id", "created_at", "updated_at")
```
Admin `__init__.py` imports all admin classes to register them.

**Schema naming (LFTS pattern — preferred):**
- `{Model}BaseSchema` — shared fields
- `{Model}CreateSchema(BaseSchema)` — create request
- `{Model}UpdateSchema(BaseSchema)` — update request (all fields optional)
- `{Model}ResponseSchema(BaseSchema)` — response (includes id, timestamps)

**Model base class:** Projects inherit from `AbstractBaseModel` in `core/models/base.py` which provides:
- `id = UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`
- `created_at = DateTimeField(auto_now_add=True)`
- `updated_at = DateTimeField(auto_now=True)`
- `created_by`, `updated_by` ForeignKeys to AUTH_USER_MODEL
- `is_active = BooleanField(default=True)`
- `soft_delete()` / `restore()` methods

Generated models should inherit from `AbstractBaseModel`, not `models.Model`.

**API registration:** `api.register_controllers(ProductController, ...)` in `api/urls.py` — NOT router-based.

**FK IDs in schemas:** FK relationships use `{related}_id: UUID` in schemas (not nested objects on create/update), nested response schemas only on read.

---

### 16A: Fix `generate model` — Critical Bugs

- [ ] Fix `payload.dict()` → `payload.model_dump()` in `_generate_api_router` (line 433, 441) — **Pydantic v2 breaking change, generates broken code today**
- [ ] Change generated model to inherit `AbstractBaseModel` from `core.models.base` instead of `models.Model`; remove manually added `created_at`/`updated_at` (they come from base)
- [ ] Validate FK targets: before generating, check `backend/apps/{app}/models/{target_snake}.py` exists; hard error if not
- [ ] Require at least one field or explicit `--empty` flag; error clearly if no `--fields` given
- [ ] Remove hardcoded `created_at`/`updated_at` from generated model body (AbstractBaseModel provides them)
- [ ] Change `@router.put` → `@http_put` and all other decorators to ninja-extra style
- [ ] Change controller from function-based Router to class-based `@api_controller` + `BaseController`
- [ ] Replace `list pagination` with `limit: int = 20, offset: int = 0` params on list endpoint
- [ ] Fix list response to slice queryset: `return qs[offset:offset + limit]`

### 16B: Fix `generate model` — Auto-Wiring (file updates after generation)

Generated files are useless if they aren't wired in. After creating model/schema/controller files:

- [ ] Update `backend/apps/{app}/models/__init__.py` — add `from .{snake} import {Pascal}` (create file if missing)
- [ ] Create `backend/apps/{app}/admin/{snake}_admin.py` — per-model admin file with `@admin.register({Pascal})` + `ModelAdmin` (unfold style)
- [ ] Update `backend/apps/{app}/admin/__init__.py` — add `from .{snake}_admin import {Pascal}Admin` (create if missing)
- [ ] Update `api/urls.py` — append `{Pascal}Controller` to `api.register_controllers(...)` call if it exists; otherwise print reminder
- [ ] Print post-generation checklist: what was created, what to run next (`makemigrations`, `migrate`), what was wired, what needs manual attention

### 16C: Fix `generate endpoint` — Produce Usable Output

Currently generates a stub returning `{"message": "Not implemented"}`. Must generate ninja-extra style:

- [ ] Generate `@http_{method.lower()}` decorator (not `@router.{method}`)
- [ ] If creating a new file, generate full controller class with `@api_controller` header
- [ ] If appending to existing controller file, append the method inside the class body (detect class boundary)
- [ ] Add proper response type hint from existing schemas if detectable
- [ ] Add `auth=JWTAuth()` when `--auth` flag passed

### 16D: Fix `generate schema` — Match Real Schema Patterns

- [ ] Generate `{Pascal}BaseSchema(Schema)` with shared fields
- [ ] Generate `{Pascal}CreateSchema({Pascal}BaseSchema)` — create request
- [ ] Generate `{Pascal}UpdateSchema({Pascal}BaseSchema)` — all fields Optional with None defaults
- [ ] Generate `{Pascal}ResponseSchema({Pascal}BaseSchema)` — adds `id: UUID`, `created_at: datetime`, `updated_at: datetime`
- [ ] Use `from ninja import Schema` not `from pydantic import BaseModel` (ninja-extra projects use ninja Schema)
- [ ] Add `model_config = ConfigDict(from_attributes=True)` on ResponseSchema

### 16E: Tests for All 16A–16D Fixes

- [ ] Test generated model inherits AbstractBaseModel, no manual timestamp fields
- [ ] Test generated controller uses `@http_get`/`@http_post`/`@http_put`/`@http_delete` (not `@router.*`)
- [ ] Test `payload.model_dump()` (not `.dict()`) appears in generated controller
- [ ] Test `generate model` with no fields raises error without `--empty`
- [ ] Test FK validation error when target model file doesn't exist
- [ ] Test `models/__init__.py` updated after `generate model`
- [ ] Test `admin/{snake}_admin.py` created after `generate model`
- [ ] Test `admin/__init__.py` updated after `generate model`
- [ ] Test generated schemas follow BaseSchema/CreateSchema/UpdateSchema/ResponseSchema pattern

---

## Phase 17: `generate crud` — Full-Stack Feature Command

Single command that scaffolds a complete vertical slice of a feature. The killer demo for the public repo.

```bash
mattstack generate crud Product --fields "name:str price:decimal category:fk:Category" --with-tests
```

### Backend outputs:
- `backend/apps/{app}/models/{snake}.py` — model inheriting AbstractBaseModel
- `backend/apps/{app}/schemas/{snake}_schema.py` — Base/Create/Update/Response schemas
- `backend/apps/{app}/controllers/{snake}_controller.py` — `@api_controller` class with full CRUD + list pagination
- `backend/apps/{app}/admin/{snake}_admin.py` — unfold ModelAdmin
- Auto-wire: `models/__init__.py`, `admin/__init__.py`, `api/urls.py` register_controllers

### Frontend outputs (framework-aware):
- `frontend/src/api/{snake}.ts` — typed API client functions (list, get, create, update, delete) using fetch
- `frontend/src/hooks/use{Pascal}s.ts` — TanStack Query hooks: `use{Pascal}List`, `use{Pascal}`, `useCreate{Pascal}`, `useUpdate{Pascal}`, `useDelete{Pascal}`
- `frontend/src/components/{Pascal}List/index.tsx` — list component with loading/error/empty states
- `frontend/src/routes/{snake}s.tsx` or `app/{snake}s/page.tsx` — route/page (framework-detected)

### With `--with-tests`:
- `backend/apps/{app}/tests/test_{snake}_api.py` — pytest tests for list/get/create/update/delete
- `frontend/src/components/{Pascal}List/{Pascal}List.test.tsx` — Vitest component test

### Post-generation output:
```
Generated CRUD feature: Product
  Backend:
    ✓ models/product.py
    ✓ schemas/product_schema.py
    ✓ controllers/product_controller.py
    ✓ admin/product_admin.py
    ✓ models/__init__.py updated
    ✓ admin/__init__.py updated
    ⚠ api/urls.py — register ProductController manually
  Frontend:
    ✓ src/api/product.ts
    ✓ src/hooks/useProducts.ts
    ✓ src/components/ProductList/index.tsx
    ✓ src/routes/products.tsx

  Next steps:
    cd backend && uv run python manage.py makemigrations
    cd backend && uv run python manage.py migrate
```

### Implementation tasks:
- [ ] Add `generate crud` subcommand to `generate_app` Typer group
- [ ] Reuse and extend existing `_generate_django_model`, `_generate_pydantic_schema`, `_generate_api_router` (post Phase 16 fixes)
- [ ] New: `_generate_controller_class` — ninja-extra `@api_controller` class with all 5 CRUD methods
- [ ] New: `_generate_admin_file` — unfold-style per-model admin
- [ ] New: `_generate_ts_api_client` — typed fetch functions for each endpoint
- [ ] New: `_generate_tanstack_hooks` — `useQuery`/`useMutation` wrappers (list, get, create, update, delete)
- [ ] New: `_generate_react_list_component` — loading/error/empty states, maps data to list items
- [ ] New: `_generate_pytest_api_tests` — tests for each CRUD endpoint using pytest + django test client
- [ ] New: `_generate_vitest_component_test` — renders component, checks list renders
- [ ] Detect framework for page/route output (TanStack vs Next.js)
- [ ] Tests for `generate crud` output completeness

---

## Phase 18: AI Agent Context Superpowers

Enhance `mattstack context` to be genuinely useful as input to an AI coding agent.

### 18A: Subcommands

```bash
mattstack context models    # All Django models with field types as structured JSON
mattstack context routes    # All API routes with methods, paths, controller, schemas
mattstack context types     # All TypeScript interfaces and Zod schemas
mattstack context stack     # Tech stack summary (current behavior)
mattstack context full      # All of the above combined
```

Tasks:
- [ ] Refactor `context` into a subcommand group (Typer sub-app)
- [ ] `context stack` — current `run_context` behavior as default
- [ ] `context models` — parse `backend/apps/*/models/*.py`, extract class names + fields + types, output structured JSON
- [ ] `context routes` — parse `backend/apps/*/controllers/*.py`, extract `@api_controller` prefix + `@http_*` decorators + method names + response types
- [ ] `context types` — parse `frontend/src/**/*.ts`, extract TypeScript interfaces and Zod schemas
- [ ] `context full` — combine all above into single payload

### 18B: Output Formats

```bash
mattstack context full --format claude     # Claude XML <context> block
mattstack context full --format json       # Machine-readable JSON (current partial)
mattstack context full --format markdown   # Human-readable (current default)
```

Tasks:
- [ ] Add `--format` flag accepting `claude`, `json`, `markdown`
- [ ] Claude format: wraps output in `<context>` with `<models>`, `<routes>`, `<types>` sub-blocks
- [ ] Add token count estimate at bottom: `# Estimated tokens: ~4,200`
- [ ] Add `--max-tokens N` flag to truncate/summarize when context is large

### 18C: Model Catalog Output

```json
{
  "models": [
    {
      "name": "Product",
      "app": "catalog",
      "file": "backend/apps/catalog/models/product.py",
      "inherits": "AbstractBaseModel",
      "fields": [
        {"name": "name", "type": "CharField", "max_length": 255},
        {"name": "price", "type": "DecimalField"},
        {"name": "category", "type": "ForeignKey", "to": "Category", "on_delete": "CASCADE"}
      ]
    }
  ]
}
```

Tasks:
- [ ] Write `parsers/django_models.py` — regex-based parser for model field definitions
- [ ] Detect `AbstractBaseModel` inheritance vs plain `models.Model`
- [ ] Extract field types, kwargs (max_length, null, blank, default, on_delete)
- [ ] Handle models split across `models/` folder (glob all `.py` files)

### 18D: Route Catalog Output

```json
{
  "routes": [
    {
      "controller": "ProductController",
      "prefix": "/products",
      "tag": "Products",
      "endpoints": [
        {"method": "GET", "path": "/", "handler": "list_products", "response": "list[ProductSchema]", "auth": false},
        {"method": "POST", "path": "/", "handler": "create_product", "response": "201: ProductSchema", "auth": true}
      ]
    }
  ]
}
```

Tasks:
- [ ] Extend `parsers/django_routes.py` to detect `@api_controller` + `@http_*` decorator patterns
- [ ] Extract controller prefix, tags, auth at class level
- [ ] Extract per-method: HTTP method, path, handler name, response type annotation, auth override

### 18E: Watch Mode

- [ ] Add `--watch` flag using `watchfiles` (already a common dep)
- [ ] Re-emit context on any change in `backend/apps/*/` or `frontend/src/`
- [ ] Clear terminal between emissions, show timestamp

### 18F: Tests

- [ ] Tests for `context models` against fixture project
- [ ] Tests for `context routes` against fixture project with controllers
- [ ] Tests for `--format claude` output structure
- [ ] Tests for token estimate (rough sanity check)

---

## Phase 19: `sync api-client` Mutations + Pagination (completed)

- `useMutation` hooks for POST/PUT/DELETE/PATCH with `useQueryClient` + `onSuccess` invalidation
- Infer request body types from `{Model}CreateSchema` / `{Model}UpdateSchema` naming convention
- `invalidateQueries({ queryKey: ['{snake}s'] })` in mutation `onSuccess`
- Paginated list variant: `use{Pascal}List(page, pageSize)` with `keepPreviousData`
- `ApiError` interface exported in generated file
- `--base-url` flag override (defaults to `http://localhost:8000`)
- Dynamic TanStack Query imports (useQueryClient, keepPreviousData) only when needed
- 25 tests (691 total)

---

## Phase 20: Fix Parallel Execution in `lint` and `test`

The `--parallel` flag is accepted but runs subprocess calls sequentially. Fix it properly.

- [ ] Replace sequential `subprocess.run()` chains with `concurrent.futures.ThreadPoolExecutor`
- [ ] Use `subprocess.Popen` with streaming so output appears in real time
- [ ] Prefix each output line with `[backend]` / `[frontend]` label
- [ ] Return non-zero exit code if any subprocess fails (currently may swallow failures)
- [ ] Tests that parallel mode actually spawns concurrent processes

---

## Phase 21: Test Coverage Gaps

- [ ] Add tests for `commands/workflow.py` (currently 0 tests)
- [ ] Add tests for `commands/hooks.py` (currently 0 tests)
- [ ] Add integration test: `generate crud Product --fields "name:str"` → verify all files exist and are syntactically valid Python/TypeScript
- [ ] Add E2E test: `generate model` → check `admin/{model}_admin.py` exists + `models/__init__.py` updated
- [ ] Add regression test: generated controller uses `.model_dump()` not `.dict()`
- [ ] Bring total test count to 700+

---

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

---

## Phase 15: django-matt + Mateus First-Class Support

First-class support for [django-matt](https://github.com/mattjaikaran/django-matt) (meta-framework replacing django-ninja/extra/jwt) and [mateus](https://github.com/mattjaikaran/mateus) (Rust JS/TS runtime replacing bun/vite/node). Goal: `mattstack init my-app --preset matt-fullstack` scaffolds a production dockerized app with django-matt backend + React SSR via mateus.

### Phase 15A: django-matt Backend Support (unblocked — django-matt v0.9.0 on PyPI)

- Add `BackendFramework` enum to `config.py` (`DJANGO_NINJA`, `DJANGO_MATT`)
- Add `backend_framework` field to `ProjectConfig` (default `DJANGO_NINJA` for backward compat)
- Create `django-matt-boilerplate` repo — django-matt, Postgres, Celery/native tasks, MattAPI + controllers
- Add `"django-matt"` key to `REPO_URLS`
- Add presets: `matt-api` (backend-only), `matt-fullstack` (django-matt + React Vite), `matt-b2b-fullstack` (django-matt + B2B)
- Add django-matt to interactive wizard backend choices
- Update `parsers/django_routes.py` — detect django-matt controller decorators (`@get`, `@post` on `APIController` subclasses)
- Update `generators/backend_only.py` — route to django-matt boilerplate when `backend_framework == DJANGO_MATT`
- Update `generators/fullstack.py` — support django-matt backend option
- Update `commands/generate.py` — `generate model` outputs django-matt controller + `CRUDService` instead of ninja router
- Update `commands/generate.py` — `generate endpoint` outputs django-matt decorator style
- Update type sync — delegate to `django-matt sync_types` CLI when django-matt backend detected, or wrap its output
- Update templates: docker-compose (django-matt deps), Makefile (django-matt CLI commands), README, CLAUDE.md
- Update auditors: endpoint auditor recognizes django-matt route patterns
- Tests for all django-matt parser, generator, and preset paths

### Phase 15B: Mateus Frontend Support (blocked — mateus not yet published)

- Add `FrontendFramework.REACT_MATEUS` enum value
- Add `"react-mateus"` key to `REPO_URLS`
- Create `react-mateus-boilerplate` repo — React 19 + mateus dev/build/test, TanStack Router, SSR
- Add presets: `mateus-fullstack` (django-ninja + mateus), `mateus-frontend` (standalone)
- Add mateus to interactive wizard frontend choices
- Update `utils/package_manager.py` — detect mateus via `mateus.lock` or `mateus.toml`
- Update `commands/client.py` — mateus as package manager option (`mateus install`, `mateus add`, `mateus run`)
- Update `commands/dev.py` — `mateus dev` instead of `bun run dev` / `vite`
- Update `commands/test.py` — `mateus test` instead of `bun run test` / `vitest`
- Update `commands/lint.py` — `mateus lint` + `mateus fmt` instead of eslint/prettier
- Update templates: docker-compose (mateus build stage), Makefile (mateus commands), README
- Update post-processors: mateus monorepo proxy config (if different from vite)
- Tests for mateus detection, commands, and preset paths

### Phase 15C: matt-fullstack Preset (blocked — both 15A and 15B)

- Add preset: `matt-fullstack` (django-matt + React mateus SSR)
- Add preset: `matt-b2b-fullstack` (django-matt B2B + React mateus SSR)
- docker-compose.yml template: django-matt backend + mateus SSR frontend + Postgres + Redis + Celery worker
- docker-compose.prod.yml: multi-stage builds, mateus compile for frontend, gunicorn for backend
- E2E test: `mattstack init test-app --preset matt-fullstack` produces working dockerized app
- Type sync integration: django-matt `sync_types` → mateus frontend consumes generated types
- Update `mattstack audit` — verify cross-stack type safety for django-matt ↔ mateus React
- Update `mattstack context` — include django-matt + mateus in AI context dump
- Update `mattstack rules` — CLAUDE.md template for matt-fullstack projects
- Documentation: README section, preset table update, example workflow


---

## Open work (2026-09-12)

State: `main` has the scaffold fixes and the frontend diagnosis. PR #1
(`feat/gauntlet-audit-delegation`) is a draft, blocked until the Gauntlet binary ships.

### Blocked on Gauntlet

- [ ] PR #1: audit delegates to `gauntlet check --json`. Verified against a fake binary
      only. Mark ready once the real binary exists and `mattstack audit` runs on a
      generated project.

### Ready now, no dependency

- [ ] **Frontend runtime.** See `tasks/prompt-frontend-runtime.md`. Work is not started.
      Not mergeable until a route resolves, not just the dev server responding.
- [ ] **Split `commands/sync.py`.** It is 763 lines against the 400-line FILELENGTH gate,
      so gate 6 fails on it. Extract the pure mapping layer (`PYTHON_TO_TS`,
      `PYTHON_TO_ZOD`, `CONSTRAINT_TO_ZOD`, `_resolve_ts_type`, `_resolve_zod_type`,
      `_split_top_level_union`) into its own module. This debt lives on `main`, not on the
      Gauntlet branch.
- [ ] **`make gauntlet` writes `tasks/todo.md`.** The generated targets run
      `mattstack audit --fail-if-absent` without `--no-todo`, so a gate mutates the working
      tree. Needs `--no-todo`, which lands with PR #1's flag work.

### Pre-existing gate failures on main

Not introduced by recent work; listed so the inventory is honest.

| Gate | Status |
|---|---|
| FORMAT | pass (183 files formatted) |
| LINT | pass |
| TYPECHECK | pass (mypy strict, 107 files) |
| ARCHITECTURE | pass |
| TEST | pass (921) |
| FILELENGTH | **fail** — cli.py 590, context.py 575, generate.py 1870, rules.py 621, sync.py 763 |
| SECURITY | warnings — bandit findings, mostly low severity |
| CI | failing since 2026-08-12 on FILELENGTH and bandit |

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
- [ ] [Deployment contracts (#9)](https://github.com/mattjaikaran/mattstack-cli/issues/9):
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

### Remaining deployment prerequisites

- [ ] [Live deployments (#9)](https://github.com/mattjaikaran/mattstack-cli/issues/9):
  retain the verified local provider inventory, schema, image, and TLS proof.
  Publish Ninja's production public-health exemption in `b95a40b`.
  The actual production Gunicorn process returns 200 for health/liveness,
  503 for readiness with unavailable local dependencies, 301 for protected
  HTTP paths, 400 for an invalid Host, and HSTS on forwarded HTTPS.
  These checks do not prove live provider access, Flycast/IAM, public realtime
  routing, production secrets, or S3 provisioning. No billable deployment runs.
  Keep this issue open until you supply and authorize those prerequisites.

Close #11, #12, #17, #18, #19, #20, and #21 only with published commit and
verification evidence. Keep #9 open; do not equate a local smoke with deployment.

### Final CLI verification

- Run `make gauntlet-quick` after the source cutover and final formatting:
  all eight gates pass, zero fail. Keep all-severity Bandit blocking.
- The focused dependency, package-manager, user-config, runtime-profile, and
  template suite passes 450 tests with two upstream Typer/Click warnings.
- Stop owned browser/API proof services and remove temporary clones, launchers,
  and mutation artifacts. Preserve the user's README edits, source working-tree
  changes, stash `320b7c21af0fe5ffa7cc675bcdacf0bb186557f2`, and starter backup.

### Existing support boundaries

`generate endpoint` deliberately emits a documented 501 response until you
supply business logic. Linear, Jira, and Hermes board adapters remain explicit
stubs; use Axis or the disabled `none` backend. Do not call these existing
boundaries complete endpoint behavior or working third-party integrations.

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

---

## 2026 environment hardening (planned)

Rules: no GitHub Actions budget, so all gates run locally. Do not generate
bulk tests. `AGENTS.md` and `DESIGN.md` live in the backend and frontend
components; the CLI does not invent a second copy.

### Local gates, no CI

- [x] Stop generating GitHub/GitLab workflows by default. Make
  `mattstack workflow` opt-in (`--ci github|gitlab`) and print a warning that
  it costs minutes.
- [ ] Replace the earlier "Re-enable CI" item: remove `.github/workflows` from
  this repo and run `make gauntlet-quick` from a `pre-push` hook
  (`mattstack hooks install`). Done: CI removed, pre-push hook configured.
  Open: `hooks install` refuses because git `core.hooksPath` is set.
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
- [ ] Add `--ai pgvector|qdrant` and `--graph age|neo4j` options and map
  them to the backend compose profiles. Done: `--ai pgvector|qdrant`,
  `--graph cte|neo4j`. Open: `--graph age` exits 2 (apache/age image has no
  pgvector); generated CI still uses plain `postgres:N` for AI projects.
- [x] Add `mattstack upgrade`: show and apply boilerplate changes to an
  existing project (three-way against the recorded commit in `mattstack.yml`).
- [x] Extend `mattstack doctor`: uv, bun, Docker, `just`, pre-push hook
  installed, MCP servers reachable.
- [ ] Frontend repos: oxlint/oxfmt is handled in another session. After it
  lands, update generated pre-commit, `frontend-*` Makefile targets and
  `ci_toolchain.py` to call `bun run lint|fmt` only.

### Gauntlet integration (Rust verifier at ~/dev/gauntlet)

Decision: mattstack stays Python. No second Rust CLI. No scaffolding inside
Gauntlet, which is a language-agnostic verifier (agent never grades itself).
Reconsider Rust only if startup latency or single-binary distribution
becomes a real problem.

- [x] Generate a `gauntlet.toml` into scaffolded projects that wraps the
  existing local gates: backend `just gauntlet-quick`, frontend
  `bun run gauntlet`, and `mattstack sync check`.
- [ ] Propose a generic Gauntlet check "generated files match source":
  run a command into a temp dir, diff against committed output. mattstack
  uses it for OpenAPI, Zod and SDK drift. Field-level Pydantic/Zod parity
  stays in mattstack and runs as a custom check.
- [x] Cut import time: lazy-import Typer subcommands, Rich and questionary.
  Measure `mattstack --help` before and after: 237 ms → 140 ms (hyperfine,
  20 runs). Subcommand groups load lazily; questionary already loads only in
  `init`; Rich stays because Typer renders help with it.
- [ ] When Gauntlet is released, replace `scripts/gauntlet.py` in the
  backend and the gate table in `CLAUDE.md` with thin wrappers, then delete
  the duplicate gate runners.

### Done check

- [ ] Smoke: `mattstack init -p starter-fullstack`, then `make setup`,
  `make gauntlet`, `mattstack sync check`, and change one Pydantic field to
  confirm `sync check` fails before `sync openapi` and passes after.

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
