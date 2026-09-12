# mattstack Architecture

## File Map

```
src/mattstack/
├── cli.py              # Typer app — 26 commands, 7 subgroups
├── config.py           # ProjectType, Variant, BackendFramework (3), FrontendFramework (5),
│                       # DeploymentTarget enums; ProjectConfig dataclass; REPO_URLS (10 repos)
├── presets.py          # 19 presets (starter/b2b × fullstack/api/frontend, rsbuild, kibo,
│                       #             nextjs, django-matt, nestjs)
│
├── commands/
│   ├── init.py         # 3 modes: config-file → preset → interactive wizard
│   ├── add.py          # Add frontend/backend/ios, validates --framework
│   ├── upgrade.py      # Diff-based updates, detects nextjs/rsbuild/kibo/vite
│   ├── generate.py     # Subgroup: model, endpoint, component, page, hook, schema
│   ├── db.py           # Subgroup: migrate, makemigrations, status, seed, reset, shell, dump, load
│   ├── sync.py         # Subgroup: types, zod, api-client, all (uses existing parsers)
│   ├── deps.py         # Subgroup: check, update, audit
│   ├── health.py       # Docker, DB, Redis, backend, frontend port/HTTP checks
│   ├── hooks.py        # Subgroup: install, status, run (pre-commit)
│   ├── workflow.py     # GitHub Actions / GitLab CI generation
│   ├── audit.py        # Runs Gauntlet, formats findings (no checks)
│   ├── gauntlet.py     # Subgroup: check, run (pass-through to the Gauntlet binary)
│   ├── dev.py          # Start services with port conflict detection
│   ├── test.py         # Unified pytest + vitest, --parallel, timing
│   ├── lint.py         # Unified ruff + eslint, --parallel, timing
│   ├── env.py          # check/sync/show .env files
│   ├── rules.py        # Generate CLAUDE.md, .cursorrules, GSD files
│   ├── context.py      # Dump project context as markdown/JSON
│   ├── client.py       # Subgroup: add/remove/install/run/dev/build/exec/which
│   ├── doctor.py       # Environment checks
│   ├── info.py         # Presets, repos, examples tables
│   ├── version.py      # Version + update check
│   └── completions.py  # Shell completions
│
├── generators/         # BaseGenerator ABC → Fullstack/BackendOnly/FrontendOnly + iOS
├── gauntlet/           # Gauntlet integration: wire models, client, config generator, formatter
├── parsers/            # Pure regex parsers: pydantic, typescript, zod, django_routes, django_models
├── post_processors/    # customizer (Django + NestJS rename), frontend_config (dynamic port proxy), b2b
├── templates/          # f-string template functions (makefile, docker_compose, env, readme, etc.)
└── utils/              # console, git, docker, process, yaml_config, package_manager
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
| `react-vite` | `REACT_VITE` | Vite | 5173 |
| `react-vite-starter` | `REACT_VITE_STARTER` | Vite | 5173 |
| `react-rsbuild` | `REACT_RSBUILD` | Rsbuild | 3000 |
| `react-rsbuild-kibo` | `REACT_RSBUILD_KIBO` | Rsbuild | 3000 |
| `nextjs` | `NEXTJS` | Next.js | 3000 |

## Monorepo Port Assignment

To avoid dev-server conflicts in fullstack projects:

| Backend | Frontend | API Port | Frontend Port |
|---------|----------|----------|---------------|
| Django | Vite | 8000 | 5173 |
| Django | Rsbuild | 8000 | 3000 |
| Django | Next.js | 8000 | 3000 |
| FastAPI | Vite | 8000 | 5173 |
| FastAPI | Rsbuild | 8000 | 3000 |
| FastAPI | Next.js | 8000 | 3000 |
| NestJS | Vite | 4000 | 5173 |
| NestJS | Rsbuild | 4000 | 3000 |
| NestJS | Next.js | 4000 | 3000 |

`config.backend_api_port` encodes this: `4000` for NestJS, `8000` for Django and FastAPI.

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
7. **Verification is external**. `mattstack audit` shells out to `gauntlet check --json`.
   `gauntlet/` holds the wire models, the subprocess client, the `gauntlet.toml`
   generator, and the formatter. No check logic lives in this repo.
8. **Subgroups** use Typer pattern: `new_app = typer.Typer()`, registered in `_register_subgroups()`
9. **Lazy imports** in cli.py — each command imports its module only when invoked

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

### Add a verification check
1. Add the check to Gauntlet (`.gauntlet/checks/` or the Gauntlet catalog)
2. Do not add it to MattStack. MattStack only formats Gauntlet findings

### Add a field to the audit output
1. Extend the model in `gauntlet/models.py` and its `to_dict`
2. Add the presentation in `gauntlet/report.py`
3. Update `tests/test_gauntlet/test_models.py`

### Add a new command subgroup
1. Create `commands/new_cmd.py` with `new_app = typer.Typer(...)` + subcommands
2. Register in `cli.py` `_register_subgroups()`
