# Resume: make the frontend work from `mattstack init`

## Goal

`mattstack init` must produce a scaffolded project whose frontend dev server
starts and reaches the backend, on every frontend preset. Today it does not: the
frontend is the last broken piece of the scaffold. The backend, database, and
migrations already work end to end.

Acceptance: `mattstack init` → `make setup` → `make up` → the SPA loads at
`http://localhost:3000` and reaches the API through the dev proxy. `make
frontend-typecheck` and `make frontend-test` pass, and the `frontend-dev`
container starts.

## Root cause, measured

Upstream `react-vite-boilerplate`'s `package.json` is internally inconsistent
with its own `vite.config.ts`. Two separate failures sit behind the one symptom.

**1. `@tanstack/router-generator` floats to an incompatible major.**

```
react-router  1.58.3  pins  router-generator 1.58.1  (exact)
router-plugin 1.58.4  wants router-generator ^1.58.1
                      -> resolves to 1.132.47
```

`1.132.47` no longer exports `generator`, which `router-plugin@1.58.4` imports:

```
SyntaxError: Export named 'generator' not found in module
'@tanstack/router-generator/dist/esm/index.js'
```

**2. `router-plugin@1.58.4` does not export `tanstackRouter`, but upstream's
`vite.config.ts` imports it.**

```ts
import { tanstackRouter } from '@tanstack/router-plugin/vite';
```

So `vite.config.ts` expects the newer plugin API while `package.json` pins the
older plugin. Fixing only failure 1 moves the error to failure 2. Both were
reproduced on a real scaffold at `/tmp/mst-v10/todoapp`.

## Two options, both measured

### Option A — pin the family to 1.58.x (no app-code change)

Add an override and match the config to the older plugin export.

```json
"overrides": { "@tanstack/router-generator": "1.58.1" }
```

Verified: the `generator` export returns. It then still fails with
`does not provide an export named 'tanstackRouter'`, so `vite.config.ts` must
also stop importing `tanstackRouter` and use whatever `router-plugin@1.58.4`
actually exports. Lower blast radius, but it commits the project to a version
line upstream has already left, and the next `bun update` reintroduces the skew.

### Option B — upgrade the family together (worked end to end)

```bash
bun add @tanstack/react-router@latest @tanstack/router-plugin@latest \
        @tanstack/router-devtools@latest
```

Resolved: `react-router` 1.170.32, `router-plugin` 1.168.35,
`router-generator` 1.167.33.

Verified on the scaffold with the real app source:

| Check | Result |
|---|---|
| `bun run dev` | `VITE v5.4.8 ready`, serves **HTTP 200** on `:3000` |
| `bun run type-check` | exit 0 |
| `bun run test` | 5 passed |

`react-router` jumps `1.58.3 → 1.170.32`, which is a long way. The app source
type-checks and its tests pass, so the public API it uses is stable, but review
`src/routes` and anything importing `@tanstack/react-router` before you trust it.

**Pick one and state which.** Option B is verified working today; Option A is
lower risk but leaves the project on a dead version line.

## Where the fix belongs

Not in a hand-edit of the scaffold. The frontend is cloned, then rewritten by
post-processors, so the fix must live in the generator:

- `src/mattstack/post_processors/frontend_config.py` — where the frontend is
  configured for the monorepo. This is the natural home for a dependency
  reconciliation step.
- The frontend framework is known there via `config.frontend_framework`, so gate
  the fix per framework rather than applying it blindly.

Two constraints:

1. **Regenerate `frontend/bun.lock`.** `docker/frontend/Dockerfile.dev` runs
   `bun install --frozen-lockfile`, which fails when `package.json` and the lock
   disagree. A `package.json` edit alone breaks the container build.
2. **Cover every frontend preset.** `react-vite`, `react-vite-starter`,
   `react-rsbuild`, `react-rsbuild-kibo`, `nextjs`. Check each; the rsbuild and
   nextjs boilerplates pin different versions.

## Also fix while you are in here

- **The dev proxy is dead code.** `post_processors/frontend_config.py` writes
  `vite.config.monorepo.ts`, but `bun run dev` runs upstream's `vite.config.ts`,
  so the proxy to `:8000` never loads. "Reaches the API" cannot pass until this
  is resolved — either merge the proxy into the config upstream actually uses, or
  point `dev` at the monorepo config.
- **`make gauntlet` mutates the working tree.** The generated Makefile `gauntlet`
  targets run `mattstack audit --fail-if-absent` without `--no-todo`, so a gate
  writes `tasks/todo.md`. Add `--no-todo` to match the CI job.
- **Check the vite startup log for a non-fatal plugin error.** The successful run
  printed a stack trace ending in `Promise.all (index 0)` before `ready`. Vite
  still served, but confirm it is benign and not a plugin silently failing.

## Verify

Do not trust a single `vite` boot. The earlier bug survived because verification
stopped at "vite started".

1. `mattstack init todoapp -p starter-fullstack`, then `make setup`, `make up`.
2. `make frontend-dev` — the page loads at `:3000` **and** a request to the API
   through the proxy returns a real response, not a 404.
3. `docker compose up frontend-dev` — the container starts, proving the lockfile
   and `--frozen-lockfile` agree.
4. `make frontend-typecheck` and `make frontend-test`.
5. Repeat step 1 for `starter-frontend`, an rsbuild preset, and
   `nextjs-frontend`.
6. Run the repo gates: `uv run pytest -q`, `ruff check`, `mypy src/`.

## Context

- Repo: `~/dev/mattstack-cli`, currently on `main` with #2 merged.
- The Gauntlet work is separate: PR #1 (`feat/gauntlet-audit-delegation`), draft,
  blocked until the Gauntlet binary ships. Do not mix it into this change.
- Pre-existing and unrelated: five files exceed the 400-line gate, and bandit
  reports findings. Leave both alone.
