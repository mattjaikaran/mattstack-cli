# mattstack CLI Reference

## Scaffold

### `mattstack init`

Scaffold a new fullstack monorepo interactively, from a preset, or from a YAML config file.

```bash
mattstack init                              # Interactive wizard
mattstack init my-app                       # Pre-fill project name
mattstack init my-app -p nestjs-fullstack   # Use a preset
mattstack init my-app -p starter-fullstack --ios   # Add iOS client
mattstack init -c project.yaml             # From config file
mattstack init my-app --dry-run            # Preview without writing
```

**Options:**
| Flag | Description |
|------|-------------|
| `-p, --preset` | Named preset (see `mattstack info`) |
| `-c, --config` | Path to YAML config file |
| `--ios` | Include iOS client |
| `--dry-run` | Preview without writing files |

### `mattstack add`

Add a component (frontend/backend/ios) to an existing project.

```bash
mattstack add frontend                              # Add React Vite frontend
mattstack add frontend -f react-rsbuild             # Specific framework
mattstack add backend                               # Add Django backend
mattstack add ios                                   # Add Swift iOS client
mattstack add frontend --path /path/to/project     # Specify project root
```

---

## Generate

Generate code artifacts — all files are created in the correct location based on project structure.

### `mattstack generate model`

```bash
mattstack generate model Product --fields "name:str price:decimal active:bool"
```

Creates: Django model + Pydantic schemas + admin registration.

### `mattstack generate crud`

```bash
mattstack generate crud Product --fields "name:str price:decimal"
```

Creates a complete vertical slice:
- `backend/apps/products/models/product.py`
- `backend/apps/products/schemas/product.py`
- `backend/apps/products/api/product.py`
- `backend/apps/products/admin/product_admin.py`
- `frontend/src/api/product.ts`
- `frontend/src/hooks/useProducts.ts`
- `frontend/src/components/ProductList/index.tsx`

### `mattstack generate endpoint`

```bash
mattstack generate endpoint products --model Product
```

### `mattstack generate component`

```bash
mattstack generate component ProductCard --with-test
```

### `mattstack generate page`

```bash
mattstack generate page Products
```

### `mattstack generate hook`

```bash
mattstack generate hook useProducts --model Product
```

---

## Database

### `mattstack db migrate`

Run pending migrations (Django: `manage.py migrate`, NestJS: `bun run db:migrate`).

### `mattstack db makemigrations`

Create new Django migrations. (Django only)

### `mattstack db seed`

Seed the database with development data.

### `mattstack db reset`

Drop and recreate the database (destructive).

### `mattstack db shell`

Open a database shell.

### `mattstack db status`

Show migration status.

### `mattstack db dump`

Export database to a file.

### `mattstack db load`

Load a database dump.

---

## Sync

Sync types between backend and frontend.

### `mattstack sync types`

Parse Pydantic models → generate TypeScript interfaces.

```bash
mattstack sync types                        # Stdout
mattstack sync types --output frontend/src/types
```

### `mattstack sync zod`

Parse Pydantic models → generate Zod schemas.

### `mattstack sync api-client`

Generate a typed TypeScript API client from Django routes.

### `mattstack sync all`

Run all sync operations.

---

## Test & Lint

### `mattstack test`

Run all tests across the monorepo.

```bash
mattstack test                  # Sequential
mattstack test --parallel       # Parallel (backend + frontend simultaneously)
mattstack test --backend-only
mattstack test --frontend-only
```

### `mattstack lint`

Lint all code.

```bash
mattstack lint                  # Sequential
mattstack lint --parallel       # Parallel
mattstack lint --fix            # Auto-fix where possible
```

### `mattstack fmt`

Format all code (ruff + biome/prettier).

---

## Audit

Run Gauntlet, the verification engine, and format the findings. MattStack implements no
checks. See [the Gauntlet guide](gauntlet.md).

```bash
mattstack audit                             # Full tier
mattstack audit --tier standard             # Deterministic checks + conformance
mattstack audit --type sentinel             # Deterministic engine only
mattstack audit --type review               # AI review board only
mattstack audit --severity error            # Errors only
mattstack audit --json                      # Machine-readable output
mattstack audit --html                      # Export HTML dashboard
mattstack audit --no-todo                   # Skip the tasks/todo.md update
```

| Flag | Description |
|------|-------------|
| `--tier` | Gauntlet tier: `fast`, `standard`, `full`, `release`. Default `full` |
| `--type, -t` | Limit to a Gauntlet engine: `sentinel`, `conformance`, `review`, `quality` |
| `--severity, -s` | Minimum severity: `error`, `warning`, `info` |
| `--json` | Write the run as JSON |
| `--html` | Write `audit-report.html` |
| `--no-todo` | Skip the `tasks/todo.md` update |
| `--skip-if-absent` | Skip the run when Gauntlet is not installed |
| `--fail-if-absent` | Fail when Gauntlet is not installed |

### `mattstack gauntlet`

Call Gauntlet with the project's configuration. The exit code passes through unchanged.

```bash
mattstack gauntlet check --tier fast
mattstack gauntlet check --tier full -- --offline
mattstack gauntlet run vault show GAUNTLET-SENTINEL-SECRET-001
```

---

## Dev

### `mattstack dev`

Start all services (backend + frontend + Docker) with port-conflict detection.

---

## Dependencies

### `mattstack deps check`

Check for outdated dependencies across both stacks.

### `mattstack deps update`

Update dependencies interactively.

### `mattstack deps audit`

Security audit (pip-audit + bun audit).

---

## Health

### `mattstack health`

Check service health: Docker, Postgres, Redis, backend API, frontend.

```bash
mattstack health                # Quick check
mattstack health --live         # Poll until all services are up
```

---

## Hooks & Workflow

### `mattstack hooks install`

Install pre-commit hooks (ruff + biome/prettier).

### `mattstack hooks status`

Show hook status.

### `mattstack workflow`

Generate CI/CD configuration.

```bash
mattstack workflow                          # GitHub Actions
mattstack workflow --provider gitlab        # GitLab CI
```

---

## Project Info & Utilities

### `mattstack info`

Display available presets, source repos, and frameworks.

### `mattstack env check`

Validate `.env` files against `.env.example`.

### `mattstack env sync`

Sync `.env` with new variables from `.env.example`.

### `mattstack rules`

Generate AI assistant context files.

```bash
mattstack rules claude       # Generate CLAUDE.md
mattstack rules cursor       # Generate .cursorrules
mattstack rules gsd          # Generate GSD project files
```

### `mattstack context`

Dump project context as markdown or JSON (useful for AI prompts).

### `mattstack doctor`

Check development environment (Python, Node.js, Docker, bun, uv, etc.).

### `mattstack version`

Show version and check for updates.

### `mattstack completions`

Generate shell completions.

```bash
mattstack completions bash >> ~/.bashrc
mattstack completions zsh  >> ~/.zshrc
```

---

## Config File Format

Use `mattstack init -c project.yaml` to scaffold from a file:

```yaml
name: my-app
project_type: fullstack           # fullstack | backend-only | frontend-only
variant: starter                  # starter | b2b
backend_framework: fastapi        # django-ninja | django-matt | fastapi | nestjs
frontend_framework: react-vite    # react-vite | react-vite-starter | react-rsbuild | react-rsbuild-kibo | nextjs
include_ios: false
use_celery: true                  # Django + FastAPI support Celery; NestJS uses Bull automatically
deployment: docker                # docker | railway | render | fly-io | cloudflare | digital-ocean | aws | gcp | hetzner | self-hosted
```

---

## Preset Reference

Run `mattstack info` or see [presets below](#presets).

### Django presets

| Preset | Backend | Frontend | Celery |
|--------|---------|----------|--------|
| `starter-fullstack` | django-ninja | react-vite | yes |
| `b2b-fullstack` | django-ninja | react-vite | yes |
| `starter-api` | django-ninja | — | yes |
| `b2b-api` | django-ninja | — | yes |
| `rsbuild-fullstack` | django-ninja | react-rsbuild | yes |
| `kibo-fullstack` | django-ninja | react-rsbuild-kibo | yes |
| `nextjs-fullstack` | django-ninja | nextjs | yes |
| `matt-api` | django-matt | — | yes |
| `matt-fullstack` | django-matt | react-vite | yes |
| `matt-b2b-fullstack` | django-matt | react-vite | yes |

### FastAPI presets

| Preset | Backend | Frontend | Celery |
|--------|---------|----------|--------|
| `fastapi-api` | fastapi | — | yes |
| `fastapi-fullstack` | fastapi | react-vite | yes |
| `fastapi-b2b-fullstack` | fastapi | react-vite | yes |
| `fastapi-rsbuild-fullstack` | fastapi | react-rsbuild | yes |
| `fastapi-nextjs-fullstack` | fastapi | nextjs | yes |

### Frontend-only presets

| Preset | Framework |
|--------|-----------|
| `starter-frontend` | react-vite |
| `simple-frontend` | react-vite-starter |
| `rsbuild-frontend` | react-rsbuild |
| `kibo-frontend` | react-rsbuild-kibo |
| `nextjs-frontend` | nextjs |

### NestJS presets

| Preset | Backend | Frontend | Notes |
|--------|---------|----------|-------|
| `nestjs-api` | nestjs | — | API only, port 4000 |
| `nestjs-fullstack` | nestjs | react-vite | Monorepo |
| `nestjs-rsbuild-fullstack` | nestjs | react-rsbuild | Monorepo |
| `nestjs-nextjs-fullstack` | nestjs | nextjs | Monorepo |
