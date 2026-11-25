# S-CLI-42: Architecture contracts in generated projects (DRAFT)

| Field | Value |
|---|---|
| Spec ID | S-CLI-42 |
| Backlog item | GitHub issue #151; `docs/plans/2026-11-25-roadmap.md:118-119` (section 6: architecture contracts in generated projects) |
| Role | coding (after decisions) |
| Status | DRAFT |
| Assigned executor | none. Not claimable until D1-D3 below are recorded |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-42 (not created yet) |
| Depends on | D1-D3 decisions; the roadmap itself is "Draft (scope decisions pending)" (`docs/plans/2026-11-25-roadmap.md:3-4`) |
| Conflicts with | to be set after D1-D3 (if any work touches `scripts/gauntlet.py`, declare it against S-CLI-18, S-CLI-40 and S-CLI-41) |
| Files owned | none yet |
| Migrations | none |
| Runtime locks | none |
| Human needed | yes: decide D1, D2 and D3 below |
| Size | TBD (S if D1 = B and D3 = audit; larger otherwise) |
| Max files | TBD |
| Max changed lines | TBD |
| Verification commands | the standard list from the parent (ruff, mypy, bandit, `check_architecture.py`, `check_file_length.py`, `gauntlet.py --gate install`) plus the rows written after the decisions |
| Acceptance criteria | to be written after D1-D3. No rows are claimable yet |

Rules for the eventual spec: no changes under `tests/`, no pytest, no new dependency without a recorded decision.

## Context and verified citations

Verified on `e89fac4` and on each boilerplate's `origin/main` (2026-11-25).

- The roadmap asks for "import-linter layers for Django apps, dependency-cruiser boundaries for React features" in generated projects (`docs/plans/2026-11-25-roadmap.md:118-119`). The roadmap is a draft with scope decisions pending (L3-4).
- mattstack generates projects by cloning boilerplate repos (`src/mattstack/utils/git.py:30` `clone_repo`). So the generated project's gates come from the boilerplate, not from mattstack's templates.
- Survey of `origin/main` across `~/dev/boilerplates` (architecture-style gates only):
  - `django-ninja-boilerplate` (`fcea3e0`): has `scripts/check_architecture.py`. It enforces layers (`LAYERS` L27-36, `FORBIDDEN_LAYER_DEPS` L57-74) with no import-linter. It is wired into `.pre-commit-config.yaml:186` and `justfile:452`. Its `docs/ARCHITECTURE.md:100` calls it the ARCHITECTURE gate.
  - `react-vite-boilerplate` (`986cce9`), `react-vite-starter`, `react-rsbuild-boilerplate`, `react-rsbuild-kibo-boilerplate`, `nextjs-starter`, `nextjs-b2b-boilerplate`, `fullstack-b2b`: have `scripts/check_conventions.ts` (or `frontend/scripts/check_conventions.ts`). Its header lists 12 checks (L2-16). None is a module-boundary rule. No dependency-cruiser config exists in any React repo.
  - `django-api-b2b`, `django-api-starter`, `django-matt-b2b`, `django-matt-starter`, `fastapi-boilerplate`, `nestjs-boilerplate`, `swift-ios-starter`: no architecture gate found.
- mattstack's own `scripts/check_architecture.py` (L1-10) enforces mattstack's CLI layering, not the generated projects'.
- The `fleet` group that would check conformance across repos is not built yet (`docs/plans/2026-11-25-roadmap.md:66-77`; `src/` has no `fleet` command).

## Decisions required

D1. Who owns the Django import-linter contract?
- A. mattstack writes an import-linter config into generated Django projects. This adds a dev dependency to generated output and touches the boilerplates' pyproject files indirectly.
- B. Rely on the boilerplate's `scripts/check_architecture.py`, which already exists. mattstack only detects that the gate is present.
- Recommendation: B for now. The layer rules already exist, and A duplicates them.

D2. What about React dependency-cruiser boundaries?
- A. Add dependency-cruiser to the React boilerplates. This is a change in several repos, outside mattstack-cli.
- B. Defer until `fleet` exists, so the change can be made across repos at once.
- Recommendation: B. The roadmap's own Theme 2 (`fleet`) is the right channel.

D3. What does the mattstack-cli piece do?
- A. An audit type (for example `audit --type architecture`) that reports a generated project with no architecture gate. It does not re-run the rules. This is small and fits S-CLI-40's `audit` surface.
- B. Nothing in mattstack-cli. Only the boilerplates change.
- C. Full `fleet check` conformance. Too large for this spec; belongs with the roadmap's Theme 2.

## Open questions for the human

- Should the four boilerplates with no gate (`django-api-*`, `django-matt-*`, `fastapi-boilerplate`, `nestjs-boilerplate`) get one? That is a boilerplate-repo decision, not a mattstack-cli one.
- If D3 = A, which file does the detector read: `justfile`, the pre-commit config, or `scripts/`?

Once D1-D3 are recorded, replace this DRAFT with a READY spec with its own acceptance rows, and set the Conflicts and Files owned fields.
