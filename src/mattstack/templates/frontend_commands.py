"""Frontend script names, resolved per boilerplate.

The boilerplates do not agree on their npm script names:

- `react-vite-boilerplate` calls its type checker `type-check`.
- `react-rsbuild-boilerplate`, `react-rsbuild-kibo-boilerplate`, and
  `react-vite-starter` call it `typecheck`.
- `nextjs-starter` ships no type-check script and no test script.
- `react-vite-boilerplate` runs `vitest` in watch mode for `test`; the
  others run `vitest run`.

Emitting one hardcoded name breaks `make test` for most presets, so resolve
the command from the chosen framework. Both the generated Makefile and the
generated CI workflow read this module, so they cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass

from mattstack.config import FrontendFramework, ProjectConfig


@dataclass(frozen=True)
class FrontendCommands:
    """Shell commands for one frontend boilerplate.

    ``None`` means the boilerplate has no script for that job.
    """

    lint: str
    typecheck: str | None
    test: str | None
    format: str | None


_VITE = FrontendCommands(
    lint="bun run lint",
    # The script is `type-check`, with a hyphen.
    typecheck="bun run type-check",
    # `bun run test` is bare `vitest`, which watches. Force a single run.
    test="bunx vitest run",
    format="bun run format",
)

_TYPECHECK_NO_HYPHEN = FrontendCommands(
    lint="bun run lint",
    typecheck="bun run typecheck",
    # These repos define `test` as `vitest run` already.
    test="bun run test",
    format="bun run format",
)

_NEXTJS = FrontendCommands(
    lint="bun run lint",
    # nextjs-starter has no type-check script. Run the compiler directly.
    typecheck="bunx tsc --noEmit",
    # No test runner is configured in this boilerplate.
    test=None,
    format=None,
)

_BY_FRAMEWORK: dict[FrontendFramework, FrontendCommands] = {
    FrontendFramework.REACT_VITE: _VITE,
    FrontendFramework.REACT_VITE_STARTER: _TYPECHECK_NO_HYPHEN,
    FrontendFramework.REACT_RSBUILD: _TYPECHECK_NO_HYPHEN,
    FrontendFramework.REACT_RSBUILD_KIBO: _TYPECHECK_NO_HYPHEN,
    FrontendFramework.NEXTJS: _NEXTJS,
}

# Every frontend boilerplate defines a `gauntlet` script that runs its own
# format, lint, type-check, and test gates.
FRONTEND_GAUNTLET_COMMAND = "bun run gauntlet"


def frontend_commands(config: ProjectConfig) -> FrontendCommands:
    """Return the resolved commands for the project's frontend."""
    return _BY_FRAMEWORK.get(config.frontend_framework, _TYPECHECK_NO_HYPHEN)
