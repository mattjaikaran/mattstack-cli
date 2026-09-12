# Gauntlet integration

Gauntlet is the verification engine. MattStack is the scaffolding and project-management
layer. This page explains the split and how to configure it.

## The two layers

| Layer | Tool | Responsibility |
|-------|------|----------------|
| Scaffold | MattStack | Clone boilerplates, generate code, manage the project, present findings |
| Verify | Gauntlet | Run every check, decide pass or fail, record evidence |

MattStack keeps no check logic. `mattstack audit` runs
`gauntlet check --tier=<tier> --json` in the project directory and formats the JSON
document that Gauntlet writes to stdout.

This follows the two-layer pattern in Gauntlet's integration guide: a project-specific layer
runs a generic codebase-level gate on the output. Do not teach Gauntlet your DSL, and do not
reimplement Gauntlet checks in MattStack.

## Install Gauntlet

MattStack does not vendor Gauntlet. Gauntlet is in alpha and has no release yet, so follow
[Gauntlet's building guide](https://github.com/mattjaikaran/gauntlet/blob/main/docs/BUILDING.md)
to build it from source. Then put the binary on `PATH`:

```bash
gauntlet --version
```

## Commands

### `mattstack audit`

Run Gauntlet and format the findings.

```bash
mattstack audit                          # Full tier
mattstack audit --tier standard          # Deterministic checks + conformance
mattstack audit --type sentinel          # Limit to one engine
mattstack audit -s error                 # Minimum severity
mattstack audit --json                   # Machine-readable output
mattstack audit --html                   # HTML dashboard
mattstack audit --no-todo                # Do not write tasks/todo.md
```

| Flag | Description |
|------|-------------|
| `--tier` | Gauntlet tier: `fast`, `standard`, `full`, `release`. Default `full` |
| `--type, -t` | Limit to a Gauntlet engine: `sentinel`, `conformance`, `review`, `quality`. Repeatable |
| `--severity, -s` | Minimum severity to show: `error`, `warning`, `info` |
| `--json` | Write the run as JSON |
| `--html` | Write `audit-report.html` |
| `--no-todo` | Skip the `tasks/todo.md` update |
| `--skip-if-absent` | Skip the run when Gauntlet is not installed |
| `--fail-if-absent` | Fail when Gauntlet is not installed |

`--live`, `--base-url`, and `--fix` are deprecated. Gauntlet does not probe live endpoints
and does not auto-fix. Use `mattstack lint --fix` for formatting and lint fixes.

### `mattstack gauntlet`

Call Gauntlet without knowing the binary path. The exit code passes through unchanged, so a
CI job still sees code 2 for a blocking failure.

```bash
mattstack gauntlet check --tier fast
mattstack gauntlet check --tier full -- --offline
mattstack gauntlet run vault show GAUNTLET-SENTINEL-SECRET-001
```

### `mattstack init`

New projects get a `gauntlet.toml` for the detected stack. The file enables the Python
adapter for a Python backend. Gauntlet has no TypeScript adapter in the alpha, so a frontend
is outside the gate until that adapter ships.

## Configuration

MattStack reads the `[integrations]` table from `gauntlet.toml`:

```toml
[integrations]
binary_path = "gauntlet"   # Path or name. A path with a separator is relative to the project
skip_if_absent = true      # Skip the audit when the binary is missing
default_target = "backend" # Optional default target directory
```

Behavior:

- No `gauntlet.toml` and no `[integrations]`: a missing binary is an error. An explicit
  `mattstack audit` fails loudly.
- `skip_if_absent = true`: a missing binary skips the audit with one line and exit code 0.
  This suits a scaffolded project or a CI job that runs Gauntlet in a separate step.

The full config reference lives in Gauntlet's `docs/spec/gauntlet-toml.md`. MattStack writes
only documented keys.

## Add a check

Add the check to Gauntlet, not to MattStack. Gauntlet supports user checks in
`.gauntlet/checks/` with a declarative or shell form. See Gauntlet's
`docs/spec/check-authoring.md` and `docs/spec/gauntlet-toml.md`.

The former `mattstack-plugins/` auditor plugin system is removed. A plugin could not be
reproduced by another developer and did not appear in Gauntlet's audit trail. Gauntlet
records every run in the vault, so a check has evidence.

## Output contract

MattStack parses the JSON document from `gauntlet check --json`. The document carries a
`schema_version` field. MattStack accepts version 1 and reports a clear error for any other
version. The wire format is in Gauntlet's `docs/spec/finding-schema.md`.
