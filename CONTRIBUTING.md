# Contributing

## Set up

```bash
uv sync --extra dev
uv run mattstack hooks install
git config --get core.hooksPath   # Must print nothing; pre-commit refuses otherwise
```

The pre-push hook runs `make gauntlet-quick`. Read
[docs/architecture.md](docs/architecture.md) before you move code between layers.

## Work flow

Two tracks run at the same time:

- **Owner sessions:** larger or supervised work, such as L issues and design
  decisions. Open a PR like any other change.
- **Overnight agents:** agent-run runs READY specs from `tasks/specs/` and opens
  one PR per spec. See [Overnight agents](#overnight-agents).

1. Start from a GitHub issue or a READY spec in `tasks/specs/`.
2. Branch from `main` with a prefix such as `feat/`, `fix/`, `docs/` or `chore/`.
   Agent-run specs use `agent/<Spec ID>`.
3. Commit with `<type>(<scope>): <Capitalized imperative summary>`. Keep the
   subject at 50 characters or fewer and wrap the body at 72. Every commit body
   names its issue: `Closes #N` when the commit finishes the issue, `Refs #N`
   otherwise.
4. Run `make gauntlet-quick` before you push.
5. Open a PR with the [pull request template](.github/pull_request_template.md).

## Batch PRs

Do not open a PR for each small issue. Group issues in the same area and wave
(a GitHub milestone, when the owner sets one) into one batch PR:

- One area per PR.
- 2,000 inserted lines or fewer, counted as the Sizes table counts them.
- One commit per issue, so a reviewer can read the batch issue by issue.
- The PR closes every issue in the batch with a `Closes #N` line for each one.

## Sizes

Limits count changed files and inserted lines, tests included. Lockfiles,
generated files and deleted lines do not count.

| Size | Limit | Who does it |
|---|---|---|
| S | At most 8 files and 300 inserted lines | Overnight agent (small model) |
| M | At most 15 files and 800 inserted lines | Overnight agent (small model) |
| L | At most 30 files and 2,000 inserted lines | Supervised session with a frontier model, which splits the work into S and M specs |

Each spec records its size in the `Size` header field.

Size each GitHub issue with the same table. A frontier model splits each L
issue into S and M specs in `tasks/specs/` before an overnight agent takes any
of its work; no agent takes an L issue whole.

## Overnight agents

agent-run claims the first READY spec in ID order whose Assigned executor is
`agent-run`, whose dependencies are done, that has no open or merged pull
request, and that shares no owned file or declared conflict with a claimed
spec. It works on `agent/<Spec ID>`, changes only the spec's Files owned, and
opens one PR per spec. The spec format is in
[tasks/specs/README.md](tasks/specs/README.md).

## Review process

1. `make gauntlet-quick` must pass. This repository has no hosted CI, so the
   Verification section of the PR is the evidence.
2. `matt-reviewer` reviews every PR. Fix or answer each finding.
3. The owner, `mattjaikaran`, approves. A PR merges only with both approvals on
   its current head commit.

## Tests

The testing policy is in [AGENTS.md](AGENTS.md#testing-policy). The smoke
checks outside the unit suite are `make smoke-scaffold` and
`make smoke-frontend-dev`; both need network access. This repository has no
Playwright journeys.
