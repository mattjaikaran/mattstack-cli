# S-CLI-42: Architecture contracts in generated projects (`audit --type architecture`)

| Field | Value |
|---|---|
| Spec ID | S-CLI-42 |
| Backlog item | GitHub issue #151; `docs/plans/2026-11-25-roadmap.md` (Theme 2) |
| Role | coding |
| Status | READY |
| Assigned executor | agent-run |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-42 |
| Depends on | S-CLI-29 (the opt-in `should_run` mechanism in `auditors/base.py` and the `--type` wiring) |
| Conflicts with | S-CLI-29, S-CLI-33, S-CLI-38, S-CLI-40 (`src/mattstack/auditors/base.py`, `src/mattstack/commands/audit.py`) |
| Files owned | `src/mattstack/auditors/architecture.py` (new), `src/mattstack/auditors/base.py`, `src/mattstack/commands/audit.py` |
| Migrations | none |
| Runtime locks | none |
| Human needed | none |
| Size | S |
| Max files | 8 |
| Max changed lines | 300 |
| Verification commands | `uv run ruff format --check src/`; `uv run ruff check src/`; `uv run mypy src/`; `uv run bandit -q -r src/ -c pyproject.toml`; `uv run python scripts/check_architecture.py`; `uv run python scripts/check_file_length.py`; `uv run python scripts/gauntlet.py --gate install` |
| Acceptance criteria | A1-A5 (table below) |

## Context and verified citations

Citations were read at base commit `e89fac4`. `src/` and `scripts/` have not changed since then (checked 2026-11-25). Items marked (unverified) are not confirmed yet.

**mattstack (base commit `e89fac4`):**
- `src/mattstack/auditors/base.py:11-14` `class Severity(StrEnum)` with `ERROR`, `WARNING`, `INFO`.
- `src/mattstack/auditors/base.py:17-23` `class AuditType(StrEnum)`: `TYPES`, `QUALITY`, `ENDPOINTS`, `TESTS`, `DEPENDENCIES`, `VULNERABILITIES`. S-CLI-29 adds `MIGRATIONS` as an opt-in type. This spec adds `ARCHITECTURE` the same way.
- `src/mattstack/auditors/base.py:61` `def should_run(self, audit_type: AuditType) -> bool`. S-CLI-29 changes it so opt-in types run only when named in `audit_types`. This spec adds `ARCHITECTURE` to that set.
- `src/mattstack/auditors/base.py:35` and `:139` `to_dict` (finding and report serialization). The dataclass is `AuditFinding` (`base.py:26-33`): `category: AuditType`, `severity: Severity`, `file: Path`, `line: int`, `message: str`, `suggestion: str = ""`.
- `src/mattstack/commands/audit.py:37-44` `AUDITOR_CLASSES: dict[AuditType, type[BaseAuditor]]`. `:47` `def run_audit(...)`. `:76-78` parses `audit_types`. `:122-123` loop: `if not config.should_run(audit_type): continue`.
- `src/mattstack/project.py:50-66` `ResolvedProject` (`backend_dir`, `frontend_dir`, `backend_framework`, `frontend_framework`, `root`, `config`). `:248` `resolve_project(path)`.
- `src/mattstack/auditors/types.py:37` already reads `project.frontend_dir / "package.json"`. Reuse that pattern.

**Boilerplate gate files (origin/main of django-ninja-boilerplate):**
- `justfile:451` `check-arch:`; `:452` runs `scripts/check_architecture.py`. The script exists.
- `.pre-commit-config.yaml:186` wires `check_architecture`.

**Frontend gate files (origin/main):**
- `react-vite-boilerplate/package.json:35`: `"check-conventions": "bun run scripts/check_conventions.ts"` (the `scripts` value contains `check_conventions`).
- `nextjs-starter/package.json:18`: same pattern.

Note: S-CLI-18 and S-CLI-41 were listed as conflicts in the old DRAFT. They edit `scripts/gauntlet.py`, which this spec does not touch, so they are dropped from this spec's Conflicts list.

## Goal and non-goals

**Goal.** `mattstack audit --type architecture` checks each generated component for an architecture gate. The gate is a command that a developer can run to enforce architecture rules (the boilerplate's `check_architecture.py` or the frontend's `check_conventions.ts`). If a component has no gate, the audit reports one WARNING for it. The audit never reports an ERROR.

**Non-goals.**
- Running the gate. The audit only checks that a gate is wired up.
- Any change to `scripts/gauntlet.py`.
- Any change to generated templates. The boilerplate already ships the gates.
- Making the check part of the default audit. It is opt-in.
- Any `tests/` file. Acceptance is the shell rows below.

## Implementation steps

1. **`src/mattstack/auditors/base.py`.** Add `ARCHITECTURE = "architecture"` to `AuditType` (`:17-23`); `category` is an enum, not a string. In `should_run`, extend the opt-in set that S-CLI-29 introduces (`MIGRATIONS` is its first member) to include `ARCHITECTURE`, so the type runs only when named in `audit_types`. Copy S-CLI-29's pattern, not S-CLI-33's, because S-CLI-33 runs by default. Do not change the behavior of any other type.
2. **`src/mattstack/auditors/architecture.py` (new).** `class ArchitectureAuditor(BaseAuditor)` with `audit_type = AuditType.ARCHITECTURE`, following the shape of the existing auditors in `auditors/`:
   - For each component that exists, resolve it through `resolve_project(path)`:
     - backend: `backend_dir`, always checked when it exists.
     - frontend: `frontend_dir`, checked only when `frontend_framework` is set.
     - skip any component whose framework is `None`, so a backend-only scaffold gets no frontend finding.
     - when `backend_dir == frontend_dir`, read the shared files once (dedupe by resolved path).
   - If `resolve_project` raises `EnvFileError` (`project.py:107`, raised at `:248-251`), emit one `WARNING` finding at the project root with the error message and continue. Do not crash the audit.
   - A component has a gate when any of these matches the token set `{check_architecture, check-architecture, check_conventions}`:
     - the text of `justfile`, `Makefile`, or `.pre-commit-config.yaml` in the component dir (read as text; a missing file counts as no match);
     - the `scripts` values in the component's `package.json` (frontend only; parse with `json`).
   - Gate found: no finding for that component.
   - No gate found: one `AuditFinding` with severity `Severity.WARNING`, `category=AuditType.ARCHITECTURE`, file = the component dir relative to the project root, line `0`, `suggestion` = one line naming the fix (add a `check_architecture` or `check_conventions` recipe or script to that component), and a message like `no architecture gate found (expected check_architecture or check_conventions in justfile, Makefile, .pre-commit-config.yaml, or package.json scripts)`.
   - The auditor never emits ERROR or INFO.
3. **`src/mattstack/commands/audit.py`.** Add `AuditType.ARCHITECTURE: ArchitectureAuditor` to `AUDITOR_CLASSES` (`:37-44`). Do not change `run_audit`'s flow beyond what the opt-in rule needs.

## Machine-checkable acceptance

Each row runs from the repo root. `$TMP` is created in A1. Warnings do not change the exit code, so each row checks the output.

| ID | Command | Expected |
|---|---|---|
| A1 | `TMP=$(mktemp -d) && uv run mattstack init "$TMP/proj" --preset starter-fullstack >/dev/null 2>&1; (cd "$TMP/proj" && uv run mattstack audit --type architecture); echo "exit=$?"` | `exit=0`; the output has zero architecture WARNING lines (fresh scaffold has gates in backend and frontend) |
| A2 | `printf '# stripped\n' > "$TMP/proj/backend/justfile"; : > "$TMP/proj/backend/Makefile"; : > "$TMP/proj/backend/.pre-commit-config.yaml"; (cd "$TMP/proj" && uv run mattstack audit --type architecture); echo "exit=$?"` | `exit=0`; exactly one architecture WARNING, for the `backend` component |
| A3 | `TMP3=$(mktemp -d) && uv run mattstack init "$TMP3/proj" --preset starter-fullstack >/dev/null 2>&1; sed -i.bak 's/check_conventions/nope/g' "$TMP3/proj/frontend/package.json"; (cd "$TMP3/proj" && uv run mattstack audit --type architecture); echo "exit=$?"` | `exit=0`; exactly one architecture WARNING, for the `frontend` component (fresh scaffold, so the backend keeps its gate) |
| A4 | `(cd "$TMP/proj" && uv run mattstack audit) \| grep -ci architecture` | `0` (opt-in: the default audit does not run the architecture type) |
| A5 | `uv run mattstack audit --type architecture --help >/dev/null; echo "exit=$?"` | `exit=0`, the `--type` option is accepted |

Also run, and paste the exit codes into the PR:
- `uv run ruff format --check src/`
- `uv run ruff check src/`
- `uv run mypy src/`
- `uv run bandit -q -r src/ -c pyproject.toml`
- `uv run python scripts/check_architecture.py`
- `uv run python scripts/check_file_length.py`
- `uv run python scripts/gauntlet.py --gate install`

## Stop conditions and PR evidence

**Stop and report, do not open a PR, if:**
- S-CLI-29 is not merged. This spec depends on its `should_run` opt-in mechanism.
- Any citation in this spec no longer matches at your HEAD: `base.py:17-23` or `:61`, `audit.py:37-44` or `:122-123`, or `project.py:50-66` or `:248`.
- A2 or A3 cannot be run because the `starter-fullstack` frontend has no `package.json` gate at the cited value. Report the actual value.
- A change would be needed in `scripts/gauntlet.py` or in any file outside Files owned.

**PR evidence:**
- Output and exit codes of A1-A5.
- Exit codes of every command in the verification list.
- The list of changed files, which must be a subset of Files owned.
- The Conflicts note: S-CLI-29, S-CLI-33, S-CLI-38, and S-CLI-40 share `base.py` and `audit.py`, so the merge order must be handled by the integration owner.
