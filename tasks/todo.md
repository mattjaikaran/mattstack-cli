## Gauntlet Constraint Violations (2026-07-25)

> Detected by 10-gate gauntlet (`make gauntlet`). 3 of 8 gates passed on first run.

### Failing Gates
- [ ] **FORMAT** — pre-existing ruff formatting violations. Run `make format` then `make gauntlet-gate GATE=format`
- [ ] **LINT** — pre-existing ruff lint violations. Run `make lint-fix`
- [ ] **TYPECHECK** — pre-existing mypy errors. Fix type annotations
- [ ] **SECURITY** — bandit flagged issues. Run `make security-scan`
- [ ] **FILELENGTH** — 5 files exceed 400-line limit. Split large files

### Passing Gates
- [x] ARCHITECTURE — no layer violations found
- [x] Install check — package installs clean
- [x] CI re-enabled — workflow now runs on push/PR


### Gate status update (2026-09-12)

Measured after Phase 23. Tests: 783 passing.

| Gate | Status | Evidence |
|---|---|---|
| LINT | pass | `ruff check src/ tests/ scripts/` clean |
| TYPECHECK | pass | `mypy src/` — no issues in 99 files |
| ARCHITECTURE | pass | `scripts/check_architecture.py` clean |
| TEST | pass | 783 passed |
| FORMAT | fail | 10 files need formatting (pre-existing, none from Phase 23) |
| FILELENGTH | fail | 5 files over 400 lines: cli.py 605, context.py 575, generate.py 1870, rules.py 623, sync.py 621 |
| SECURITY | warnings | bandit: 92 findings, all low severity except 2 medium (B310 urllib) |

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

## Phase 23: Gauntlet Audit Delegation (audit feature)

MattStack delegated every check to Gauntlet. MattStack scaffolds and manages the project;
Gauntlet verifies it. The audit command is now a formatter and a subprocess call.

Gauntlet lives at `~/dev/gauntlet` and will be public at
https://github.com/mattjaikaran/gauntlet.

### Completed

- [x] Add `src/mattstack/gauntlet/models.py` — typed models for the Gauntlet JSON contract
      (`Finding`, `CheckSummary`, `RunResult`, `Severity`, `CheckStatus`, `ENGINES`) with
      `schema_version` validation
- [x] Add `src/mattstack/gauntlet/client.py` — subprocess boundary: `check()` runs
      `gauntlet check --tier=<tier> --json --target=<dir>` and parses stdout
- [x] Add `src/mattstack/gauntlet/init.py` — generates `gauntlet.toml` for the detected stack;
      never overwrites an existing file
- [x] Add `src/mattstack/gauntlet/report.py` — Rich table, JSON, and the idempotent
      `tasks/todo.md` writer; `html_report.py` holds the HTML dashboard
- [x] Rewrite `commands/audit.py` as a formatter over Gauntlet findings
- [x] Add `commands/gauntlet.py` — `mattstack gauntlet check|run` pass-through that forwards
      undeclared options and preserves the Gauntlet exit code
- [x] Wire `gauntlet.toml` generation into `commands/init.py`, guarded for `--dry-run`
- [x] Delete `src/mattstack/auditors/` (11 modules, 1,805 lines) and the six auditors
- [x] Delete `tests/test_auditors/` (102 tests) and the auditor tests in `test_django_matt.py`
- [x] Delete the three parser modules only the auditors used —
      `parsers/dependencies.py`, `parsers/test_files.py`, `parsers/nextjs_routes.py` — and
      their tests (31 tests)
- [x] Add `tests/test_gauntlet/` (client, models, config generator) and rewrite
      `tests/test_commands/test_audit.py` against a fake Gauntlet binary
- [x] Mark a skipped run in the JSON envelope (`skipped`, `skip_reason`) so an empty finding
      list never reads as a clean pass
- [x] Update README, CLAUDE.md, docs/architecture.md, docs/commands.md, docs/ecosystem.md
- [x] Add `docs/gauntlet.md`; delete the obsolete `docs/plugin-guide.md`
- [x] Read `[integrations]` from `gauntlet.toml` for `binary_path`, `skip_if_absent`,
      and `default_target`
- [x] Detect Gauntlet at runtime: skip with one line when the project opted in, fail when it
      did not (mirrors the Rivet precedent in Gauntlet's `docs/INTEGRATIONS.md`)
- [x] Update the scaffold templates that described the deleted auditors
      (`templates/root_claude_md.py`, `templates/gsd_project.py`)
- [x] Verify: 783 tests pass, mypy strict clean, architecture gate clean, smoke test over a
      real subprocess for table/JSON/HTML/todo/exit-code/skip/pass-through paths

### Remaining

- [ ] Install Gauntlet on this machine and run `mattstack audit` on a real generated project
      (the engine has no binary yet — the integration is verified against a fake)
- [ ] Remove `--live`, `--base-url`, and `--fix` from `mattstack audit` once Gauntlet is
      installed everywhere. They are deprecated and warn today
- [ ] Raise the tier default from `full` if the review board needs an LLM; `full` requires
      Ollama running locally
- [ ] Add a `--tier fast` pre-commit example to `commands/hooks.py` so the scaffolded hook
      runs the same gate
- [ ] Replace the local audit of this repo (`make gauntlet`, `scripts/gauntlet.py`) with the
      Gauntlet binary once it ships. Two tools share the name today; see CLAUDE.md
- [ ] Report two Gauntlet spec defects upstream:
      1. `docs/spec/init.md` writes `[checks.sentinel:coverage]` without quotes. Bare TOML
         keys cannot contain `:`, so `gauntlet init` emits a file its own parser rejects.
      2. The per-check key form is documented two ways: `[checks.coverage]` in
         `docs/spec/gauntlet-toml.md` and `[checks.sentinel:coverage]` in
         `docs/spec/init.md`. An unrecognized key is a hard config error, so this must be
         settled before any consumer writes per-check tables. MattStack omits them and
         relies on Gauntlet's documented defaults
- [ ] Track the Gauntlet TypeScript adapter. Until it ships, a MattStack frontend is outside
      the gate. The generated config records this

### Deferred

- Plan conformance for scaffolded projects. `[conformance.plan]` needs a roadmap file; the
  generated config leaves it commented out
- Ticket conformance. The generated config sets `[conformance.tickets] source = "none"`
- Per-project check thresholds. Users edit `gauntlet.toml`; MattStack does not prompt
- Mapping mattstack's `--type` values (`types`, `tests`, `endpoints`, `dependencies`,
  `vulnerabilities`) to Gauntlet engines. Those domains have no Gauntlet equivalent yet;
  `--type` selects an engine instead
- `detected.py` does not detect Rust. `init` passes `has_rust=False`; a Rust backend preset
  would need this
- Re-add per-check tuning to the generated config once Gauntlet settles the key form.
  Coverage, CRAP, and TDD currently rely on Gauntlet's defaults, which match what
  `gauntlet init` writes

---

## Gauntlet gate wiring (done on this branch)

`mattstack init` writes `skip_if_absent = true`, so a bare `mattstack audit` exits 0 without
checking anything. Two callers were exposed:

- The Makefile `gauntlet` target, added by the scaffold branch.
- The generated CI `gauntlet` job, which is the required status check in
  `DEFAULT_STATUS_CHECKS`. A skipped run would have gone green while verifying nothing, on
  the one check that blocks a merge.

Both now pass `--fail-if-absent`, so a missing binary fails the local gate and CI alike.
The CI job's docstring no longer claims a fallback to built-in auditors, which this branch
deletes.

Still to do: add a `gauntlet-quick` target that runs `--tier fast`, for a pre-commit hook.

Also: `src/mattstack/commands/sync.py` grew past 700 lines while fixing the type mappings,
so it is further over the 400-line FILELENGTH gate than the 621 the table above records.
Extract the pure mapping layer (`PYTHON_TO_TS`, `PYTHON_TO_ZOD`, `CONSTRAINT_TO_ZOD`,
`_resolve_ts_type`, `_resolve_zod_type`, `_split_top_level_union`) into its own module.
