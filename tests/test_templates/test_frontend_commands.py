"""Tests for per-framework frontend script resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from mattstack.config import FrontendFramework, ProjectConfig, ProjectType, TaskBackend
from mattstack.templates.frontend_commands import frontend_commands
from mattstack.templates.root_makefile import generate_makefile


def _config(tmp_path: Path, framework: FrontendFramework) -> ProjectConfig:
    return ProjectConfig(
        name="test-app",
        path=tmp_path / "test-app",
        project_type=ProjectType.FULLSTACK,
        frontend_framework=framework,
        task_backend=TaskBackend.NONE,
        use_redis=False,
        init_git=False,
    )


@pytest.mark.parametrize(
    "framework",
    [
        FrontendFramework.REACT_VITE_STARTER,
        FrontendFramework.REACT_RSBUILD,
        FrontendFramework.REACT_RSBUILD_KIBO,
    ],
)
def test_typecheck_uses_hyphenless_script(tmp_path: Path, framework: FrontendFramework) -> None:
    """These boilerplates define `typecheck`, not `type-check`."""
    assert frontend_commands(_config(tmp_path, framework)).typecheck == "bun run typecheck"


def test_react_vite_uses_hyphenated_script(tmp_path: Path) -> None:
    """react-vite-boilerplate defines `type-check` with a hyphen."""
    cmds = frontend_commands(_config(tmp_path, FrontendFramework.REACT_VITE))
    assert cmds.typecheck == "bun run type-check"


def test_react_vite_test_forces_a_single_run(tmp_path: Path) -> None:
    """`bun run test` is bare vitest in that repo, which watches forever."""
    cmds = frontend_commands(_config(tmp_path, FrontendFramework.REACT_VITE))
    assert cmds.test == "bunx vitest run"


def test_nextjs_has_no_test_script(tmp_path: Path) -> None:
    """nextjs-starter ships no test runner, so no test job is emitted."""
    cmds = frontend_commands(_config(tmp_path, FrontendFramework.NEXTJS))
    assert cmds.test is None
    assert cmds.typecheck == "bunx tsc --noEmit"


def test_makefile_emits_the_resolved_command(tmp_path: Path) -> None:
    """A hardcoded name breaks `make test`; the resolver must reach the file."""
    vite = generate_makefile(_config(tmp_path, FrontendFramework.REACT_VITE))
    assert "bun run type-check" in vite
    assert "bun run typecheck" not in vite

    starter = generate_makefile(_config(tmp_path, FrontendFramework.REACT_VITE_STARTER))
    assert "bun run typecheck" in starter
    assert "bun run type-check" not in starter


def test_makefile_ships_a_read_only_gauntlet_target(tmp_path: Path) -> None:
    """The local gate must not write tasks/todo.md, matching the CI job."""
    makefile = generate_makefile(_config(tmp_path, FrontendFramework.REACT_VITE))
    assert "\tmattstack audit --no-todo\n" in makefile


def test_makefile_sync_api_uses_the_openapi_command(tmp_path: Path) -> None:
    """The Makefile regenerates the client through the OpenAPI contract."""
    makefile = generate_makefile(_config(tmp_path, FrontendFramework.REACT_VITE))
    assert "\tmattstack sync openapi\n" in makefile
