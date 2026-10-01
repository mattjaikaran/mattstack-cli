# mattstack architecture

## File Map

```
src/mattstack/
├── cli.py              # Root Typer app and subgroup registration
├── cli_scaffold.py     # Scaffold command registration
├── cli_project.py      # Project command registration
├── config.py           # Framework enums, ProjectConfig, upstream repo URLs
├── project.py          # Root, environment, ports, API mount, resolved configuration
├── config_file.py      # Persist nonsecret metadata and preserve control-plane settings
├── stack.py            # Shared command-facing stack resolution
├── stack_detection.py  # Framework and component detection
├── presets.py          # Named stack configurations
│
├── commands/
│   ├── init.py         # 3 modes: config-file → preset → interactive wizard
│   ├── add.py          # Add frontend/backend/ios, validates --framework
│   ├── upgrade.py      # Diff-based updates, detects nextjs/rsbuild/kibo/vite
│   ├── generate.py     # Subgroup: model, endpoint, component, page, hook, schema
│   ├── db.py           # Subgroup: migrate, makemigrations, status, seed, reset, shell, dump, load
│   ├── sync.py         # types, zod, api-client, all
│   ├── openapi.py      # Local OpenAPI SDK generation, ownership, drift checks
│   ├── deps.py         # Subgroup: check, update, audit
│   ├── health.py       # Docker, DB, Redis, backend, frontend port/HTTP checks
│   ├── hooks.py        # Subgroup: install, status, run (pre-commit)
│   ├── workflow.py     # GitHub Actions / GitLab CI generation
│   ├── audit.py        # 6 auditor classes + plugin loader
│   ├── dev.py          # Start services with port conflict detection
│   ├── test.py         # Unified pytest + vitest, --parallel, timing
│   ├── lint.py         # Unified ruff + eslint, --parallel, timing
│   ├── env.py          # check/sync/show .env files
│   ├── rules.py        # Generate CLAUDE.md, .cursorrules, GSD files
│   ├── context.py      # Dump project context as markdown/JSON
│   ├── context_builders.py # Collect context without terminal formatting
│   ├── context_format.py   # Markdown, Claude, and raw JSON output
│   ├── client.py       # Subgroup: add/remove/install/run/dev/build/exec/which
│   ├── doctor.py       # Environment checks
│   ├── info.py         # Presets, repos, examples tables
│   ├── version.py      # Version + update check
│   └── completions.py  # Shell completions
│
├── generators/         # BaseGenerator ABC → Fullstack/BackendOnly/FrontendOnly + iOS
├── auditors/           # BaseAuditor ABC → types, quality, endpoints, tests, dependencies, vulnerabilities
├── codegen/            # Django/Matt layouts, model PKs, schemas, CRUD, TS transport/hooks/Zod
├── parsers/            # Regex schema, route, enum, dependency, and frontend-layout parsers
├── post_processors/    # Customization, active bundler config, TanStack version alignment
├── templates/          # Root Makefile, Compose, runtime env, agent rules, Dockerfiles
└── utils/              # Console, Git, Docker, process supervision, jobs, package managers
```

## Backend Frameworks

| Key | Enum | Language | Package Manager | Port (monorepo) |
|-----|------|----------|-----------------|-----------------|
| `django-ninja` | `BackendFramework.DJANGO_NINJA` | Python | `uv` | 8000 |
| `django-matt` | `BackendFramework.DJANGO_MATT` | Python | `uv` | 8000 |
| `fastapi` | `BackendFramework.FASTAPI` | Python | `uv` | 8000 |
| `nestjs` | `BackendFramework.NESTJS` | TypeScript/Node.js | `bun` | 4000 |

NestJS uses Bull (Redis-based) for queues — `use_celery` is always `False` for NestJS projects. FastAPI uses Celery + Redis (same as Django backends).

## Frontend Frameworks

| Key | Enum | Bundler | Dev Port |
|-----|------|---------|----------|
| `react-vite` | `REACT_VITE` | Vite | 3000 |
| `react-vite-starter` | `REACT_VITE_STARTER` | Vite | 3000 |
| `react-rsbuild` | `REACT_RSBUILD` | Rsbuild | 3000 |
| `react-rsbuild-kibo` | `REACT_RSBUILD_KIBO` | Rsbuild | 3000 |
| `nextjs` | `NEXTJS` | Next.js | 3000 |

## Monorepo Port Assignment

To avoid dev-server conflicts in fullstack projects:

| Backend | Frontend | API Port | Frontend Port |
|---------|----------|----------|---------------|
| Django | Vite | 8000 | 3000 |
| Django | Rsbuild | 8000 | 3000 |
| Django | Next.js | 8000 | 3000 |
| FastAPI | Vite | 8000 | 3000 |
| FastAPI | Rsbuild | 8000 | 3000 |
| FastAPI | Next.js | 8000 | 3000 |
| NestJS | Vite | 4000 | 3000 |
| NestJS | Rsbuild | 4000 | 3000 |
| NestJS | Next.js | 4000 | 3000 |

These are defaults. `resolve_project()` applies root environment values and
persisted port metadata. Use the resolved project in commands rather than a
second detection path. Host mode runs applications locally; container mode
supervises Compose applications.

## Key Patterns

1. **Templates = Python functions** returning f-strings (not Jinja2)
2. **Generators inherit BaseGenerator**. Each defines `steps` property; base runs them in sequence
3. **ProjectConfig** is the single config object. Key properties:
   - `has_backend`, `has_frontend`, `is_fullstack`, `is_b2b`
   - `is_nextjs`, `is_django_matt`, `is_fastapi_backend`, `is_nestjs_backend`, `is_django_backend`
   - `backend_api_port` — dynamically set based on framework
4. **BackendFramework** enum: `django-ninja`, `django-matt`, `fastapi`, `nestjs`
5. **FrontendFramework** enum: `react-vite`, `react-vite-starter`, `react-rsbuild`, `react-rsbuild-kibo`, `nextjs`
6. **Parsers are pure functions** — regex-based, no AST, no deps. Return dataclasses
7. **Auditors inherit BaseAuditor**. `run() → list[AuditFinding]`
8. **Subgroups** use Typer apps registered by `cli.py`.
9. **Command registration** is split across `cli_scaffold.py` and `cli_project.py`.

## Common Workflows

### Add a new backend framework
1. Add to `BackendFramework` enum in `config.py`
2. Add repo URL to `REPO_URLS` in `config.py`
3. Add `is_<name>_backend` property to `ProjectConfig` if needed
4. Update `backend_api_port` property if non-standard port
5. Add presets in `presets.py`
6. Add wizard choice in `commands/init.py`
7. Add customizer branch in `post_processors/customizer.py`
8. Update Makefile template in `templates/root_makefile.py`
9. Update docker-compose template in `templates/docker_compose.py`
10. Update env template in `templates/root_env.py`
11. Update test in `tests/test_presets.py`

### Add a new frontend framework
1. Add to `FrontendFramework` enum in `config.py`
2. Add repo URL to `REPO_URLS` in `config.py`
3. Add presets in `presets.py`
4. Add wizard choice in `commands/init.py`
5. Add upgrade detection in `commands/upgrade.py`
6. Add monorepo proxy in `post_processors/frontend_config.py`
7. Update templates: `root_readme.py`, `root_claude_md.py`
8. Update CLI help in `cli.py`
9. Update test in `tests/test_presets.py`

### Add a new audit domain
1. Create `parsers/new_parser.py`
2. Create `auditors/new_auditor.py` inheriting `BaseAuditor`
3. Add to `AUDITOR_CLASSES` in `commands/audit.py`
4. Add to `AuditType` enum in `auditors/base.py`

### Add a new command subgroup
1. Create `commands/new_cmd.py` with `new_app = typer.Typer(...)` + subcommands
2. Register the subgroup in `cli.py`.
