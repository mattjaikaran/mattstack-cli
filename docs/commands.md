# mattstack CLI reference

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

For unattended use, provide a name and preset, or a YAML config file.
Do not combine `--config` with a name or preset. Dry runs do not change files,
including files in an existing project. Initialization failures return nonzero.
Generated projects persist nonsecret stack metadata in `mattstack.yml`.

### `mattstack add`

Add a component (frontend/backend/ios) to an existing project.

```bash
mattstack add frontend                              # Add React Vite frontend
mattstack add frontend -f react-rsbuild             # Specific framework
mattstack add backend                               # Add Django backend
mattstack add ios                                   # Add Swift iOS client
mattstack add frontend --path /path/to/project     # Specify project root
```

Use `--force` only when you intend to replace existing root configuration.
Without it, `add` preserves your files and stages alternatives as `.mattstack-new`.
Run `mattstack upgrade` to preview component changes. Use `--force` to apply them.
Upgrade checks every selected component before it writes files and rejects symlink paths.

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
mattstack generate crud Product -f "name:str price:decimal" -f active:bool --app core
```

Create models, request/response schemas, controllers, frontend clients, hooks, and
components in your existing installed app and frontend layout. Generated
controllers register with the detected API. Foreign keys use the target model's
primary-key type. Partial updates preserve omitted fields and reject explicit
nulls for non-nullable fields. Use `--force` to replace generated files.

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

Run pending Django migrations with `manage.py migrate`. Database commands support Django backends only.

### `mattstack db makemigrations`

Create new Django migrations. (Django only)

### `mattstack db seed`

Run your seed script. `--fresh` flushes data first; provide `--yes` for unattended use.
The command validates the seed file before it flushes data.

### `mattstack db reset`

Flush application data and run migrations. This does not drop the database.
Use `--yes` to authorize an unattended reset. Remote, production, or unverified
targets also require `--force`. Check the displayed database target before you confirm.

### `mattstack db shell`

Open a database shell.

### `mattstack db status`

Show migration status.

### `mattstack db dump`

Export database to a file.

### `mattstack db load`

Load a database dump.

Run database commands from the project root or a nested directory. Commands load
the root `.env`; exported shell variables take precedence. Failures preserve
stderr and return nonzero.

---

## Sync

Sync types between backend and frontend.

### `mattstack sync types`

Parse Pydantic schemas into TypeScript interfaces. Decimal types without a
known serializer accept numeric or string JSON representations.

```bash
mattstack sync types
mattstack sync types --output frontend/src/types/generated.ts
```

### `mattstack sync zod`

Parse Pydantic models → generate Zod schemas.

### `mattstack sync api-client`

Generate a typed TypeScript API client from the detected API routes and mount.
Reuse the shared Axios client when available; preserve its authentication.
The removed `--base-url` option did not configure runtime requests.

### `mattstack sync all`

Run all sync operations.

### `mattstack sync openapi`

Generate an SDK with a locally installed, pinned `@hey-api/openapi-ts`.
This command does not fetch a tool automatically.

```bash
mattstack sync openapi --schema openapi.json
mattstack sync openapi --schema openapi.json --check
```

Use `--check` to detect drift without replacing output. The ownership manifest
protects edited or unmanaged files. Use `--force` only for intentional replacement.
Keep output inside your frontend. See [optional tools](ecosystem.md).

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

Parallel lint includes format checks. Both runners return nonzero when any
selected job fails. Child output and labels render as literal text.

### `mattstack fmt`

Format all code (ruff + biome/prettier).

---

## Audit

Static analysis across six domains. Results are printed as a table and appended to `tasks/todo.md`.

```bash
mattstack audit                             # All domains
mattstack audit --type types              # Type drift (Pydantic ↔ TypeScript)
mattstack audit --type quality            # TODOs, stubs, hardcoded credentials
mattstack audit --type endpoints          # Unimplemented endpoints
mattstack audit --type tests              # Missing test coverage
mattstack audit --type dependencies       # Outdated packages
mattstack audit --type vulnerabilities    # CVE scan
mattstack audit --html                    # Export HTML dashboard
mattstack audit --json --no-todo > audit.json
```

Audit returns nonzero for error findings, even when a display filter hides them.
JSON commands write raw JSON to stdout and diagnostics to stderr.

---

## Dev

### `mattstack dev`

Use `--mode host` to run applications on your host and only infrastructure in
Compose. Use `--mode container` to run the selected application containers.
Use `--no-docker` when infrastructure is already available.
Commands use configured ports and supervise child process groups. Shutdown stops
the selected application processes or containers and leaves infrastructure intact.

For production Django deployments, load `.env.production` and set
`DJANGO_ENVIRONMENT=production`. Django Ninja also requires distinct
`SECRET_KEY`, `NINJA_JWT_SIGNING_KEY`, and `CENTRIFUGO_TOKEN_SECRET` values.
The generated production image selects the matching server and settings package.
Static collection uses transient build keys and fails visibly on errors.

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

Check only the services defined by your project, using its configured ports.

```bash
mattstack health                # Quick check
mattstack health --live --json   # Probe services and emit JSON
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

CI uses the detected component directories and committed lockfiles. Existing
workflow files remain unchanged unless you pass `--force`. The optional Gauntlet
job uses the current built-in audit; PR #1's separate migration is not included.

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

```bash
mattstack context full . --format json
mattstack context stack . --format claude
```

Use `full`, `stack`, `models`, `routes`, or `types`. Pass the project path as a
positional argument. Scope verification fails closed when Git discovery fails.

### `mattstack doctor`

Check the tools your project needs. Compose is optional when your project does
not define it. Use `--path` and `--json` for agent integration. Busy ports are
informational; a missing project directory is a failure.

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
type: fullstack                   # fullstack | backend-only | frontend-only
variant: starter                  # starter | b2b
backend:
  framework: django-ninja         # django-ninja | django-matt | fastapi | nestjs
  celery: true
  redis: true
frontend:
  framework: react-rsbuild-kibo    # See mattstack info
ios: false
deployment: docker
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
