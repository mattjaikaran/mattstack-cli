# mattstack architecture

This page explains how the mattstack CLI turns your choices into one
generated project, and how later commands change that project safely. For
flags and examples, see the [CLI reference](commands.md). For production
targets, see the [deployment guide](deployment-guide.md). For custom
boilerplate repos, presets, and optional tools, see the
[ecosystem guide](ecosystem.md). For custom auditors, see the
[plugin guide](plugin-guide.md).

## Two views: the CLI and the generated project

Keep these two views separate:

- **The CLI (this repository)** knows every supported backend and frontend.
  It holds their enums, source repo URLs, presets, templates, and code
  generators.
- **A generated project** contains only the components you selected: at most
  one backend in `backend/`, at most one frontend in `frontend/`, and an
  optional iOS client in `ios/`. The CLI does not install the other
  frameworks.

| Role | Supported choices in the CLI | Selected in one project |
|------|------------------------------|-------------------------|
| Project type | `fullstack`, `backend-only`, `frontend-only` | Exactly one |
| Backend | `django-ninja`, `django-matt`, `fastapi`, `nestjs` | One, or none for `frontend-only` |
| Frontend | `react-vite`, `react-vite-starter`, `react-rsbuild`, `react-rsbuild-kibo`, `nextjs` | One, or none for `backend-only` |
| iOS client | `swift-ios` | Optional, `fullstack` only |
| Task backend | `celery`, `huey`, `django_q`, `django_rq`, `dramatiq`, `none` | One that the backend supports; see [Task backend selection](#task-backend-selection) |
| Realtime | Centrifugo | Optional, `django-ninja` only |
| Media storage | `local`, `s3` | One; `s3` needs `django-ninja` |
| Deployment target | `docker`, `railway`, `render`, `fly-io`, `cloudflare`, `digital-ocean`, `aws`, `gcp`, `hetzner`, `self-hosted` | One; `init` refuses unsupported combinations |

## Init pipeline

`mattstack init` resolves your choices into one `ProjectConfig`, then runs
one generator. Each step returns success or failure. A failure removes the
project directory that this run created.

```mermaid
flowchart TD
    start["mattstack init"] --> mode{"Entry mode"}
    mode -->|"--config file.yml"| file["load_config_file()"]
    mode -->|"name + --preset"| preset["Preset.to_config()"]
    mode -->|"terminal, no preset"| wizard["Wizard: type, variant,<br/>one backend, one frontend,<br/>iOS, task backend, realtime"]
    file --> flags["Apply --task-backend, --realtime,<br/>--media-storage flags"]
    preset --> flags
    wizard --> config
    flags --> config["ProjectConfig.__post_init__<br/>normalize and validate runtime"]
    config --> guard{"_generate() checks"}
    guard -->|"directory exists or<br/>unsupported deployment"| refuse["Exit; nothing written"]
    guard -->|"ok"| pick{"project_type"}
    pick -->|"fullstack"| full["FullstackGenerator"]
    pick -->|"backend-only"| back["BackendOnlyGenerator"]
    pick -->|"frontend-only"| front["FrontendOnlyGenerator"]
    full --> steps["Run steps in order"]
    back --> steps
    front --> steps
    steps -->|"a step fails"| cleanup["cleanup(): remove the<br/>root this run created"]
    steps -->|"all pass"| done["Print next steps"]
```

### How init resolves choices

1. `run_init()` selects one entry mode. `--config` cannot combine with a
   name or `--preset`. Without a terminal, you must pass `--preset` with a
   name, or `--config`.
2. Runtime flags override the config file or preset. The wizard asks only
   for the runtime choices that flags did not set, and it lists only the
   task backends that the selected backend supports.
3. `ProjectConfig.__post_init__` normalizes the choice set:
   - `frontend-only` sets the task backend to `none` and turns off Redis,
     iOS, realtime, and S3 media.
   - `nestjs` maps the legacy Celery default to `none` and keeps Redis on,
     because Bull runs inside the NestJS API.
   - `django-ninja` always uses Redis. Any task backend other than `none`
     also turns on Redis.
   - An unsupported task backend, realtime, or media choice raises
     `ValueError`. `init` prints the valid choices and exits before it
     creates any file.
4. `_generate()` refuses an existing directory and a deployment target that
   cannot run the stack, for example Next.js on Cloudflare.

### What each generator writes

The generator clones only the selected source repos. `clone_and_strip()`
shallow-clones the default branch of the URL in `REPO_URLS`, or your
override from `~/.mattstack/config.yaml`. It then removes the `.git`
history. A fresh `init` therefore uses the published boilerplates, not
unpublished local changes.

| Step | Fullstack | Backend-only | Frontend-only |
|------|:---------:|:------------:|:-------------:|
| Create the project directory | yes | yes | yes |
| Clone the selected backend into `backend/` | yes | yes | no |
| Clone the selected frontend into `frontend/` | yes | no | yes |
| Clone the iOS starter into `ios/` | if `--ios` | no | no |
| Consolidate component root files | yes | yes | no |
| Check task and realtime prerequisites | yes | yes | no |
| Write root files (Makefile, README, `.cursorrules`, `.gitignore`, deployment files) | yes | yes | yes |
| Write Compose files, `.env*`, `CLAUDE.md`, and Dockerfiles | yes | yes | no |
| Write the root `.pre-commit-config.yaml` | yes | yes | yes |
| Customize cloned components (names; frontend bundler config and API proxy) | yes | backend only | frontend only |
| Write `mattstack.yml` and `.dockerignore` | yes | yes | yes |
| Initialize Git with a first commit | yes | yes | yes |

Frontend-only provider recipes can add image files separately. Fly emits a
frontend Dockerfile; Render and DigitalOcean emit one for Next.js. Static-site
recipes do not need those containers.

`--dry-run` runs the same steps but prints each action instead of writing.

## Generated project runtime

A generated project runs only its selected components. The diagram shows a
fullstack project. A backend-only project has no frontend node. A
frontend-only project has only the frontend.

```mermaid
flowchart TD
    browser["Browser"] --> fe["One selected frontend"]
    fe -->|"dev proxy or Next.js rewrite<br/>of the API prefix"| api["One selected backend"]
    api --> db[("PostgreSQL :5432")]
    api -.->|"optional: Redis enabled"| redis[("Redis :6379")]
    worker["Optional task worker<br/>Compose profile per task backend"] -.-> redis
    api -.->|"optional: --realtime,<br/>django-ninja only"| cent["Centrifugo :8800"]
    browser -.->|"optional: authenticated WebSocket"| cent
```

- Dashed edges are optional. Task workers and Centrifugo start only with
  their Compose profile, so `docker compose up` alone starts the same core
  services.
- `mattstack dev` runs in host mode by default: Compose starts only the
  database and Redis, and the app servers run on your machine. Container
  mode runs the `api-dev` and `frontend-dev` Compose services instead.
- The production Compose file and deployment recipes follow the same
  selection. See the [deployment guide](deployment-guide.md) for the
  production prerequisites and the verification boundary.

### Default ports

| Service | Default | Override |
|---------|---------|----------|
| Backend API | 8000 for Python backends, 4000 for NestJS | `API_PORT` |
| Frontend dev server | 3000 for every frontend | `FRONTEND_PORT` |
| PostgreSQL | 5432 | `DB_PORT` |
| Redis | 6379 | `REDIS_PORT` |

`resolve_project()` reads each port from the root `.env` first, then from
`project.ports` in `mattstack.yml`, then from these defaults. Commands use
the resolved project. Do not add a second detection path.

## Project metadata and secret environment

Generated projects keep stack facts and secrets in different files:

| File | Content | In Git |
|------|---------|--------|
| `mattstack.yml` | Control-plane settings (`deps`, `scope`, `board`, `notify`) and the `project:` stack metadata | Yes |
| `.env.example`, `.env.production.example` | Variable names with placeholder values | Yes |
| `.env` | Local values. Realtime projects get random Centrifugo secrets. | No |
| `.env.production` | A copy of the production example. Replace every placeholder before you deploy. | No |

`save_project_config()` writes only nonsecret choices under `project:`:
name, type, variant, iOS, deployment target, execution mode, the backend
framework, directory, Redis, API prefix, task backend, realtime, media
storage, and settings module, the frontend framework and directory, and
ports. It overwrites scaffold choices, keeps user-tuned values such as
ports, and keeps every other key and comment. Configuration that needs a
credential names an environment variable, for example
`board.api_key_env`, instead of the value.

When a command reads an existing project, persisted metadata wins over
filesystem detection. Detection in `stack_detection.py` returns `None` for
a framework it does not recognize, and callers refuse rather than guess.

## Task backend selection

`ProjectConfig.task_backend` is the single runtime selection. `use_celery`
is a derived property, not a constructor argument.

| Backend | Supported task backends | Worker processes |
|---------|-------------------------|------------------|
| `django-ninja` | `celery`, `huey`, `django_q`, `django_rq`, `dramatiq`, `none` | Celery worker and beat, or one worker for the other backends |
| `django-matt`, `fastapi` | `celery`, `none` | Celery worker and beat |
| `nestjs` | `none` | None; Bull queues run inside the API |
| Frontend-only | `none` | None |

For `django-ninja`, the generator writes `TASK_BACKEND` to the environment
files. Before it writes root files, `prepare_runtime()` checks the cloned
backend:

- It adds the disabled `none` backend to `api/tasks/loader.py` when the
  clone does not have it. With `none`, `.delay()` raises
  `TaskDispatchDisabled` instead of queueing a job that no worker reads.
- It fails when the loader does not list the selected backend, when
  `pyproject.toml` lacks the backend's optional extra, or when realtime
  files are missing.

For an existing project, `runtime_kwargs()` resolves the task backend in
this order: `project.backend.task_backend`, then `TASK_BACKEND` in `.env`
for `django-ninja`, then the legacy `celery` flag, then a `celery`
dependency in the backend manifest.

## Code generation: plan, validate, then write

`mattstack generate` commands collect every create and update in one
`FilePlan` in memory. All validation runs before the first write. A
`GenerateError` at any point means that nothing was written.

```mermaid
flowchart TD
    cmd["mattstack generate model, crud,<br/>endpoint, schema, page, component, hook"] --> resolve["resolve_project()<br/>root, backend/, frontend/"]
    resolve --> layout["Detect layout<br/>backend_layout.py, frontend_layout.py"]
    layout --> policy["Validate inputs<br/>fields, policy, router shape"]
    policy -->|"GenerateError"| stop["Exit 1; nothing written"]
    policy --> plan["Plan backend and frontend<br/>writes into one FilePlan"]
    plan -->|"GenerateError"| stop
    plan --> conflicts{"finish(): new files<br/>already exist?"}
    conflicts -->|"yes, without --force"| stop
    conflicts -->|"no, or --force"| apply["FilePlan.apply(dry_run)"]
    apply -->|"--dry-run"| preview["Print planned paths only"]
    apply -->|"normal run"| write["Create planned files,<br/>then update existing files"]
```

- `generate crud` plans the backend and the frontend in the same plan, so
  a refused frontend route also stops the backend files.
- `FilePlan.text()` returns the planned content of a file, so later
  planners build on earlier planned edits, not stale disk content.
- `FilePlan.apply()` writes files one at a time and has no rollback. The
  guarantee covers validation and conflict errors, not an operating system
  error during the write.
- Backend generation needs a Django backend with a `NinjaExtraAPI` or
  django-matt API instance. It refuses plain `NinjaAPI`. It does not
  generate FastAPI or NestJS code.

### Router detection

`detect_frontend_layout()` reads `frontend/package.json` and selects one
router. Page and CRUD generation then use that router's own conventions.

| Dependency found | Router | Where pages go |
|------------------|--------|----------------|
| `next` | `nextjs` | App Router directory (`app/` or `src/app/`) |
| `@tanstack/react-router` | `tanstack` | Routes directory from the TanStack config (`parsers/tanstack_config.py`) |
| `react-router-dom` or `react-router` | `react-router` | `src/pages/`, registered in the route declaration |
| None of these | `unknown` | Page generation refuses |

For React Router, the generator edits one of two declaration styles: a
module that renders `<Routes>` with literal `<Route>` elements, or exactly
one `createBrowserRouter`, `createHashRouter`, `createMemoryRouter`, or
`useRoutes` call with a literal or named `const` route array. It refuses
computed, spread, or mapped routes, and `createRoutesFromElements`. Then
you register the page by hand.

A browser guard (`--guard`, or the React Router `protected` group) is a
client-side redirect. It is not authorization, and audits never report it
as a backend control.

### Resource policy: global and owned

`generate model` and `generate crud` take a resource policy.
`resource_policy.py` checks the policy against the backend before it plans
any file.

| Scope | Reads | Writes | Requirements |
|-------|-------|--------|--------------|
| `global` (default) | Every caller reads every row | Need a valid JWT when the backend has JWT auth; open to every caller when it does not | None |
| `owned` | Each caller sees only their rows; another user's row answers 404 | Every route needs a valid JWT; create sets the owner from the request user | `--owner-field` names a `name:fk:User` field, and the backend depends on `django-ninja-jwt` or `django-matt[auth]` |

- A user foreign key does not grant access by itself. Only
  `--scope owned --owner-field <field>` binds rows to a user.
- The generated module states its policy and lifecycle in its docstring.
- In a `global` resource, the list query line carries
  `# global policy; noqa: UNSCOPED_QUERY` for the backend convention gate.
  The generator does not change the route-auth contract. When the backend
  has `core/tests/test_route_auth.py`, the CLI prints a security review
  warning. Review the anonymous GET operations, and then add them to
  `PUBLIC_OPERATIONS` yourself.
- `--lifecycle soft-delete` requires a base model whose default manager
  hides inactive rows. The check refuses a base model that does not.

## Component guidance and quality gates

Consolidation removes each cloned component's standalone root files,
because the generated project has one root. Agent guidance follows one
rule: canonical sources stay, and harness adapters go.

- **Kept in the component:** `AGENTS.md`, `SKILLS.md`, `.agents/skills/`,
  `.omp/`, and `.context/`.
- **Removed from the component:** `CLAUDE.md`, `.cursorrules`, `.claude/`,
  `.cursor/`, `.windsurf/`, `.kiro/`, and `.continue/`. The root
  `CLAUDE.md` and `.cursorrules` replace them.
- The root `CLAUDE.md` lists each component's guidance files that exist,
  and its quick gate: `cd backend && just gauntlet-quick` when the
  component has that `justfile` recipe, or its `gauntlet:quick` package
  script.
- The root `.pre-commit-config.yaml` runs each tool inside its component.
  For `django-ninja`, it runs the backend's locked ruff on commit and
  `just gauntlet-quick` on push. Other Python backends use the ruff
  pre-commit mirror, NestJS uses its `lint` script, and frontends use
  their own prettier.

Keep this guidance and these gate scripts during consolidation. Do not
replace the generated hooks with the open PR #1 implementation.

## CLI source map

```text
src/mattstack/
├── cli.py              # Root Typer app; registers the subgroups
├── cli_scaffold.py     # init, add, upgrade, doctor, info, presets, audit, config
├── cli_project.py      # dev, test, lint, fmt, env, health, workflow, protect, notify, verify, ...
├── config.py           # Enums, ProjectConfig, supported_task_backends, REPO_URLS
├── presets.py          # Built-in presets and user presets from ~/.mattstack/config.yaml
├── user_config.py      # User config: repo overrides, presets, defaults
├── project.py          # resolve_project(), save_project_config(), .env parsing
├── config_file.py      # mattstack.yml control plane and the project: section
├── stack.py            # Resolved stack for add, upgrade, rules, and workflow
├── stack_detection.py  # Conservative backend and frontend detection
├── runtime_profiles.py # Task workers, realtime, and runtime prerequisites
├── notify.py           # Deploy notification backends
├── commands/
│   ├── init.py, init_runtime.py   # Entry modes, wizard, runtime flags
│   ├── generate.py, generate_crud.py  # generate subgroup
│   ├── codegen/        # FilePlan, layouts, resource policy, router planners, TS/Zod
│   ├── add.py, upgrade.py  # Add a component; preview boilerplate updates
│   ├── db.py, db_target.py  # Database subgroup and target detection
│   ├── sync.py, openapi.py  # Types, Zod, API client, OpenAPI SDK
│   ├── dev.py, test.py, lint.py, health.py, env.py
│   ├── deps.py, hooks.py, workflow.py  # Dependencies, Git hooks, GitHub Actions
│   ├── audit.py        # AUDITOR_CLASSES and plugin loading
│   ├── rules.py, context*.py  # Agent config files and context dumps
│   ├── board.py, todo.py, protect.py, verify.py, notify.py  # Control plane
│   └── client.py, doctor.py, info.py, version.py, completions.py
├── generators/         # BaseGenerator and the fullstack, backend-only, frontend-only, iOS generators
├── post_processors/    # Consolidation, customization, bundler config, task runtime, TLS health
├── templates/          # Python functions that return file content (no Jinja2)
├── parsers/            # Regex parsers that return dataclasses
├── auditors/           # BaseAuditor subclasses that return AuditFinding objects
├── boards/             # Board backends (axis, none; Hermes, Jira, Linear are stubs)
└── utils/              # Console, Git, Docker, processes, jobs, package managers
```

`scripts/check_architecture.py` enforces the layers: `commands/` can import
core modules, and core modules cannot import from `commands/`.

## Key patterns

1. Templates are Python functions that return strings.
2. Each generator defines `steps`. `BaseGenerator.run()` runs them in order
   and calls `cleanup()` on failure.
3. `ProjectConfig` is the single scaffold configuration. Commands that act
   on an existing project use `resolve_project()` or `stack.py`.
4. Parsers use regex, not AST, and have no extra dependencies.
5. Auditors subclass `BaseAuditor` and return `list[AuditFinding]`.
6. Code generators plan into a `FilePlan` and write only through
   `finish()`.

## Development tools and security gate

Run `uv sync --locked --extra dev` to install the development tools,
including mypy, Bandit, and PyYAML stubs. CI selects each matrix
interpreter explicitly and uses the committed lockfile.

Keep the Bandit gate blocking at every severity. Do not add global rule
skips, a blanket baseline, or a lower severity threshold. Add an exact
rule-ID annotation with a reason only after you review its trust boundary.

The existing scoped waivers cover trusted project and tool execution, XML
serialization without parsing, public token-storage names, explicit
environment examples, an internal process-pipe invariant, and
container-internal listeners. Run project scripts, dependencies, hooks,
and tools only when you trust the project, your `PATH`, and your
environment. An argv list does not make an untrusted project safe.
Review a waiver again when you change its command or data flow.

Generated development Compose services publish ports on loopback. Replace
production placeholders with real secrets; the examples do not prove secret
strength.

## Extension workflows

### Add a backend framework

1. In `config.py`, add the `BackendFramework` member, its `REPO_URLS`
   entry, an `is_<name>_backend` property if needed, and its rules in
   `supported_task_backends()` and `backend_api_port`.
2. Add detection in `stack_detection.py`. Update the default API port in
   `project.py` if it is not 8000.
3. Add presets in `presets.py`, the wizard choice in `commands/init.py`,
   and the `add --framework` help in `cli_scaffold.py`.
4. Add a branch in `post_processors/customizer.py` and, if needed,
   `post_processors/consolidate.py`.
5. Update the templates that branch on the backend: `root_makefile.py`,
   `docker_compose.py`, `compose_env.py`, `dockerfiles.py`,
   `backend_entrypoint.py`, `root_env.py`, `pre_commit_config.py`, the
   `deploy_*.py` recipes, `root_readme.py`, and `root_claude_md.py`.
6. Update `runtime_profiles.py` if the backend runs task workers.
7. Add tests in `tests/test_presets.py` and the generator and template
   tests.

### Add a frontend framework

1. Add the `FrontendFramework` member and its `REPO_URLS` entry in
   `config.py`.
2. Add detection in `stack_detection.py`. `add` and `upgrade` use it.
3. Add presets in `presets.py`, the wizard choice in `commands/init.py`,
   and the `add --framework` help in `cli_scaffold.py`.
4. Update `templates/frontend_runtime.py` (bundler groups, browser env
   variable, proxy) and `post_processors/frontend_config.py` (bundler
   config patch).
5. Update `frontend_commands.py`, `dockerfiles.py`, `root_readme.py`,
   `root_claude_md.py`, and `gsd_project.py`.
6. If the framework uses a new bundler or router, update
   `parsers/frontend_layout.py` and add a page planner in
   `commands/codegen/`.
7. Add tests in `tests/test_presets.py`, `tests/test_project.py`, and
   `tests/test_templates/test_frontend_commands.py`.

### Add an audit domain

1. Create the parser in `parsers/`.
2. Create the auditor in `auditors/`, subclassing `BaseAuditor`.
3. Add the domain to `AuditType` in `auditors/base.py`.
4. Add the auditor to `AUDITOR_CLASSES` in `commands/audit.py`.

For a project-specific check, write a plugin in `mattstack-plugins/`
instead. See the [plugin guide](plugin-guide.md).

### Add a command or subgroup

1. For a subgroup, create `commands/<name>.py` with a `typer.Typer` app
   and register it in `_register_subgroups()` in `cli.py`.
2. For a root command, add the function and register it in
   `register_scaffold_commands()` in `cli_scaffold.py` or
   `register_project_commands()` in `cli_project.py`.
3. Document the command in the [CLI reference](commands.md).

## CLI full-gate tooling

Run `uv sync --extra dev`, then `make gauntlet-quick` for blocking quick gates.
Run `make gauntlet-gate GATE=audit` or `GATE=mutation` for full-gate tools.
The runner provisions pinned `pip-audit==2.10.1` and `mutmut==3.8.0` with
`uv run --with`; it does not add runtime or development dependencies to the
project manifest. Provisioning needs network access or a populated uv cache.

The audit receives the selected project interpreter's `purelib` path.
The mutation runner overlays that project's environment so baseline tests
can import its dependencies. Mutation uses two children and a 600-second
deadline. A timeout is a failed, incomplete gate, not a mutation score.
Keep surviving mutants, partial results, and tool warnings visible.
