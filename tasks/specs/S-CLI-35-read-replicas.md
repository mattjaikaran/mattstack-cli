# S-CLI-35: read replicas for the Django backend (DRAFT)

| Field | Value |
|---|---|
| Spec ID | S-CLI-35 |
| Backlog item | `docs/plans/2026-11-25-roadmap.md:90-99` (section 4, "Scaling: vertical and horizontal", read-replica item) |
| Role | coding |
| Status | DRAFT |
| Assigned executor | none until a human approves the open decisions below |
| Base commit | e89fac4 |
| Branch | agent/S-CLI-35 |
| Depends on | none (S-CLI-34 is related: both touch compose and settings; see Conflicts) |
| Conflicts with | S-CLI-34 (`templates/docker_compose.py`, `templates/compose_env.py`, `post_processors/customizer.py`) |
| Files owned | none yet (to be decided after the human decisions) |
| Migrations | none |
| Runtime locks | none |
| Human needed | yes: decisions 1-3 below |
| Size | L (estimate; re-size after decisions) |
| Max files | 30 |
| Max changed lines | 2000 |
| Verification commands | not claimable yet; the standard set (`ruff`, `mypy`, `bandit`, `check_architecture.py`, `check_file_length.py`, `gauntlet.py --gate install`) applies once the spec becomes READY |
| Acceptance criteria | none until READY |

## Context and verified citations

Base commit `e89fac4`. Items marked `(unverified)` need confirmation before this spec becomes READY.

- Roadmap source: `docs/plans/2026-11-25-roadmap.md:90-99`.
- Django-ninja boilerplate `ROADMAP.md:185`: `| 4.24 | **Multi-Database Configuration** | P1 | Django multi-DB config for read replicas, analytics DB, external sources. Router class for read/write splitting. |`. Status: planned, P1. The router is not in the boilerplate yet (verified by the same read).
- Delta rule (parent): the boilerplate already ships deployment manifests (deploy/k3s and Helm, `(unverified)`). Replica wiring in those manifests is owned by the boilerplate, not this CLI.
- `src/mattstack/templates/compose_env.py:139` `db_service`. A replica needs a second Postgres service with streaming replication settings (`(unverified)`: replication-user and `primary_conninfo` requirements for the chosen Postgres image). Not designed here.
- `src/mattstack/post_processors/customizer.py:46` `_customize_django_backend` edits backend files by exact string replacement. A DATABASES `replica` entry and a router class could be patched the same way, but only if the boilerplate anchor text is stable (`(unverified)`).

## Goal and non-goals

Goal (draft): `mattstack add replica` adds a read-only PostgreSQL replica to the compose file and wires Django to send reads to it, through a router class.

Non-goals (draft):
- No automatic failover or promotion.
- No multi-region replicas.
- No analytics DB or external source DB (ROADMAP 4.24 covers those separately).
- No change to the boilerplate's deploy manifests.

## Open decisions (human needed before READY)

1. Router ownership: does the CLI generate the router class and the `DATABASES["replica"]` entry through the customizer, or does the boilerplate ship it first (ROADMAP 4.24, P1)? Recommendation: the boilerplate ships the router (4.24) and the CLI only sets the replica DSN and the `DATABASE_ROUTERS` entry. This avoids the CLI owning a Django router.
2. Replica-lag policy for reads-after-writes: read from primary for N seconds after a write by the same user, or always read from primary for selected views, or accept stale reads everywhere. No default is chosen here.
3. Replica topology in compose: one replica or N, sync or async replication, and whether the replica is part of the dev stack or production only.

Without decisions 1-3 this spec cannot be claimed. It is recorded as DRAFT so the queue shows the work exists without starting an unattended run.

## Implementation steps

Not set. Written after decisions 1-3 are recorded here by a human.

## Acceptance criteria

None yet. Acceptance rows will be added when the spec becomes READY.

## Stop conditions and PR evidence

Not applicable until READY. Do not start an executor run on this spec while Status is DRAFT.
