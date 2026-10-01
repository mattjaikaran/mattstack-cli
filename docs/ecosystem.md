# mattstack Ecosystem Guide

mattstack is designed to be extensible. You can bring your own boilerplate repos, define custom presets, and write audit plugins.

## Custom Boilerplate Repos

Override or add new source repositories in `~/.mattstack/config.yaml`:

```yaml
repos:
  # Override the default Django boilerplate
  django-ninja: https://github.com/myorg/django-boilerplate.git

  # Add new repositories
  nextjs: https://github.com/myorg/nextjs-boilerplate.git
  fastapi: https://github.com/myorg/fastapi-starter.git
```

User repos are merged with built-in repos. User entries take precedence (override by key).

### Using Custom Repos in Presets

Reference your custom repo keys in preset definitions:

```yaml
presets:
  my-fullstack:
    description: "Our team's fullstack setup"
    project_type: fullstack
    variant: starter
    frontend_framework: react-vite
```

## Custom Presets

Define presets in `~/.mattstack/config.yaml`:

```yaml
presets:
  my-api:
    description: "Internal API template"
    project_type: backend-only
    variant: starter
    use_celery: false

  my-fullstack:
    description: "Our standard fullstack"
    project_type: fullstack
    variant: b2b
    frontend_framework: react-vite
    include_ios: true
    use_celery: true
```

### Preset Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | string | auto | Human-readable description |
| `project_type` | string | fullstack | `fullstack`, `backend-only`, `frontend-only` |
| `variant` | string | starter | `starter`, `b2b` |
| `frontend_framework` | string | react-vite | `react-vite`, `react-vite-starter` |
| `include_ios` | bool | false | Include iOS client |
| `use_celery` | bool | true | Include Celery background tasks |

## Default Settings

Set project defaults so you don't have to specify them every time:

```yaml
defaults:
  deployment: railway
  use_celery: true
  use_redis: true
  init_git: true
```

## Config Commands

```bash
mattstack config show   # Display current config
mattstack config path   # Print config file path
mattstack config init   # Create template config
```

## Plugin System

See [Plugin Guide](plugin-guide.md) for writing custom audit plugins.

## Optional cross-language tools

Keep these tools optional. Install them in your generated project, not in
mattstack. Pin the version and commit the lockfile. Do not add a second gate
that repeats Gauntlet checks.

### OpenAPI clients with Hey API

Use the runtime OpenAPI schema when regex-based `sync` cannot express your
backend contract. Prefer one client generator; do not install both Hey API
and Orval.

```bash
mattstack client add @hey-api/openapi-ts@0.99.0 --dev --exact
# Export your running backend's schema to openapi.json.
mattstack sync openapi
mattstack sync openapi --check
```

Use Node 22.18 or later. `sync openapi` runs only your installed local tool.
It does not fetch packages. It rejects edited or unmanaged output unless
you pass `--force`. `--check` reports drift without replacing files.
Keep the schema free of secrets and check the generated client with your
frontend typecheck and API integration tests.

Read the [Hey API setup guide](https://heyapi.dev/docs/openapi/typescript/get-started)
for SDK, Zod, and TanStack Query plugin configuration.

### React Doctor

Use React Doctor for React-specific diagnostics, not as a replacement for
your formatter, typechecker, tests, or accessibility checks.

```bash
mattstack client add react-doctor@0.9.14 --dev --exact
cd frontend
./node_modules/.bin/react-doctor . --yes --json --no-telemetry \
  --no-supply-chain --blocking error
```

Keep the JSON report outside commits when it contains source details.
Check each project's completion status and skipped checks; an empty
diagnostic list does not prove that analysis completed.
Use `--scope changed --base origin/main` only when that Git ref exists.
Review the [React Doctor license](https://github.com/millionco/react-doctor/blob/main/LICENSE):
its modified MIT terms restrict AI training/evaluation pipelines and some
paid hosted services. Do not enable it automatically in agent pipelines.
Read the [React Doctor CLI documentation](https://www.react.doctor/) for
the supported Node versions and flags.

### Rsdoctor and runtime checks

For an Rsbuild project, install `@rsdoctor/rspack-plugin@1.6.4` with
`mattstack client add --dev --exact`. Run your build with `RSDOCTOR=true`
when you need bundle or transform diagnostics. Keep it disabled for
normal builds. See the [Rsbuild Rsdoctor guide](https://rsbuild.rs/guide/debug/rsdoctor).

Use [Schemathesis](https://github.com/schemathesis/schemathesis) to test
your runtime OpenAPI contract. Pin a tested version with `uvx --from`.
Run it against a disposable database: generated requests can write data.
Use [Playwright with axe](https://playwright.dev/docs/accessibility-testing)
to verify rendered routes, authentication, API calls, and accessibility.

For backend development, consider
[Django extensions](https://django-extensions.readthedocs.io/en/latest/)
for management tools and
[django-migration-linter](https://github.com/3YOURMIND/django-migration-linter)
for deployment compatibility checks. Use the
[TanStack Router Devtools](https://tanstack.com/router/latest/docs/framework/react/devtools)
version that matches your router; do not change your router for this tool.
