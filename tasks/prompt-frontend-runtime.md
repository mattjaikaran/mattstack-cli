# Resume: make the frontend work from `mattstack init`

## Goal

`mattstack init` must produce a scaffolded project whose frontend dev server
starts, serves the app, and reaches the backend, on every frontend preset. The
backend, database, and migrations already work end to end. The frontend is the
last broken piece.

Acceptance: `mattstack init` → `make setup` → `make up` → the SPA loads at
`http://localhost:3000` and reaches the API through the dev proxy.
`make frontend-typecheck` and `make frontend-test` pass, and the `frontend-dev`
container starts.

## Router: TanStack Router is the default, and this is not a swap

`@tanstack/react-router` **is** TanStack Router. The scope matters, because two
different routers are in play and confusing them changes the whole approach:

| Package | What it is | Where it appears |
|---|---|---|
| `@tanstack/react-router` | **TanStack Router** — the default we want | react-vite, react-rsbuild, react-rsbuild-kibo |
| `react-router-dom` | **React Router** — a different router, a different project | `react-vite-starter` only |

Do not write bare "react-router" when you mean `@tanstack/react-router`, and do
not let a version bump cross between them. The fix below keeps TanStack Router;
it changes the version of TanStack Router.

### What each boilerplate ships

| Boilerplate | Router | Packages (versions) | State |
|---|---|---|---|
| `react-vite-boilerplate` | TanStack Router | `@tanstack/react-router` 1.58.3, `@tanstack/router-plugin` 1.58.4 | **broken** |
| `react-vite-starter` | **React Router** | `react-router-dom` 7.1.0 | different router; see below |
| `react-rsbuild-boilerplate` | TanStack Router | `@tanstack/react-router` 1.169.2, `@tanstack/router-plugin` 1.167.34 | coherent |
| `react-rsbuild-kibo-boilerplate` | TanStack Router | `@tanstack/react-router` 1.169.2, `@tanstack/router-plugin` 1.167.34 | coherent |
| `nextjs-starter` | none | — | Next.js has its own file router; no dependency needed |

Read those package names fully. `@tanstack/react-router` and `react-router-dom`
are unrelated projects that happen to share a word.

**The rsbuild pair is the known-good reference.** It already ships a coherent
TanStack Router line. Align `react-vite-boilerplate` to it rather than pulling
`@latest`, which drifts.

`react-vite-starter` is the one preset that is not TanStack Router — it uses
React Router (`BrowserRouter` in `src/main.tsx`). Decide explicitly whether that
stays (it is a deliberate alternative) or migrates to TanStack Router for
consistency. Do not silently rewrite it.

## Root cause, measured

`react-vite-boilerplate` disagrees with itself. `package.json` pins
`@tanstack/react-router@1.58.3` (which pins `@tanstack/router-generator@1.58.1`
exactly) and `@tanstack/router-plugin@1.58.4` (which allows `^1.58.1`, so it
resolves `router-generator@1.132.47`). Its `vite.config.ts` then imports
`tanstackRouter`, an export `router-plugin@1.58.4` does not provide.

Two failures behind one symptom:

1. `1.132.47` no longer exports `generator`, which `router-plugin@1.58.4` imports.

   ```
   SyntaxError: Export named 'generator' not found in module
   '@tanstack/router-generator/dist/esm/index.js'
   ```

2. `router-plugin@1.58.4` does not export `tanstackRouter`, which
   `vite.config.ts` imports. Fixing only failure 1 moves the error here.

Verified on a real scaffold at `/tmp/mst-v10/todoapp`: pinning
`router-generator` to `1.58.1` restores `generator`, then fails with
`does not provide an export named 'tanstackRouter'`.

## The fix, and the third problem it exposes

Align the three router packages to the rsbuild line in `react-vite-boilerplate`:

```bash
bun add @tanstack/react-router@1.169.2 @tanstack/router-plugin@1.167.34 \
        @tanstack/router-devtools@1.169.2
```

Verified with `@latest` (which resolved 1.170.32 / 1.168.35 — the same line):

| Check | Result |
|---|---|
| `bun run dev` | **serves HTTP 200 on :3000** (clean measurement: ready in 934 ms, serving after 3 s) |
| `bun run type-check` | exit 0 |
| `bun run test` | 5 passed |
| route transforms | **FAIL** — see below |

**A 200 does not mean the app works.** The dev server serves the HTML shell, but
the log shows the router failing to transform route files:

```
Error transforming route file src/routes/dashboard/index.tsx:
Error: expected route id to be a string literal or plain template literal in /dashboard/
```

Same for `/profile/` and `/settings/`. The cause is in the app source:

```ts
createFileRoute('/dashboard' as any)
```

The newer router rejects a type assertion in a route id. Remove the cast:

```ts
createFileRoute('/dashboard')
```

Grep `src/routes` for `as any` and fix each one. This is the app-code change the
version jump requires, and it is why the acceptance check must load a route, not
just the shell.

## Plugin entry points are bundler-specific

`@tanstack/router-plugin` exposes one entry point per bundler. Do not cross them:

- Vite: `import { tanstackRouter } from '@tanstack/router-plugin/vite'`
- Rsbuild/Rspack: `import { TanStackRouterRspack } from '@tanstack/router-plugin/rspack'`

The rsbuild boilerplates already use the `/rspack` form with
`TanStackRouterRspack`. If you touch the rsbuild config, keep that import.

## Where the fix belongs

Not in the scratch project. `mattstack init` re-clones on every run, so a fix
applied in `/tmp` is lost and "works from init" stays false. The fix belongs in:

- the boilerplate repo itself (`react-vite-boilerplate` `package.json`, plus the
  `as any` route files), or
- a post-processor in `src/mattstack/post_processors/frontend_config.py`, where
  the frontend is configured for the monorepo and `config.frontend_framework`
  tells you which framework you are handling.

Two constraints:

1. **Regenerate `frontend/bun.lock`.** `docker/frontend/Dockerfile.dev` runs
   `bun install --frozen-lockfile`, which fails when `package.json` and the lock
   disagree. A `package.json` edit alone breaks the container build.
2. **Cover every frontend preset.** The rsbuild and kibo boilers already look
   correct — verify them rather than assuming, and leave `react-vite-starter`
   alone unless you decide to migrate it.

## Also fix while you are in here

- **The dev proxy is dead code.** `frontend_config.py` writes
  `vite.config.monorepo.ts`, but `bun run dev` runs upstream's `vite.config.ts`,
  so the proxy to `:8000` never loads. "Reaches the API" cannot pass until this
  is resolved — merge the proxy into the config that `dev` actually uses.
- **`make gauntlet` mutates the working tree.** The generated Makefile `gauntlet`
  targets run `mattstack audit --fail-if-absent` without `--no-todo`, so a gate
  writes `tasks/todo.md`. Add `--no-todo` to match the CI job.

## Verify

Do not trust a single `vite` boot. The earlier bug survived because verification
stopped at "vite started", and a 200 alone has the same weakness.

1. `mattstack init todoapp -p starter-fullstack`, then `make setup`, `make up`.
2. `make frontend-dev` — the page loads at `:3000`, **a route resolves without a
   transform error**, and a request through the proxy reaches the API with a real
   response, not a 404.
3. Check the vite log for `Error transforming route file`.
4. `docker compose up frontend-dev` — the container starts, proving the lockfile
   and `--frozen-lockfile` agree.
5. `make frontend-typecheck` and `make frontend-test`.
6. Repeat step 1 for `starter-frontend`, an rsbuild preset, and
   `nextjs-frontend`.
7. Run the repo gates: `uv run pytest -q`, `ruff check src/`, `mypy src/`.

## Context

- Repo: `~/dev/mattstack-cli`. Work on a branch off the latest `main`; #2 is
  merged there.
- The Gauntlet work is separate: PR #1 (`feat/gauntlet-audit-delegation`), draft,
  blocked until the Gauntlet binary ships. Do not mix it into this change.
- Pre-existing and unrelated: five files exceed the 400-line gate, and bandit
  reports findings. Leave both alone.
