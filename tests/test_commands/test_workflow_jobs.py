"""Tests for CI workflow generation.

Job names are a contract: `mattstack protect` requires the `gauntlet` status
check, and the frontend jobs must run commands the boilerplate defines.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mattstack.commands.workflow import (
    _detect_frontend_framework,
    _generate_github_actions,
    _generate_gitlab_ci,
)
from mattstack.config import FrontendFramework

# The scripts each boilerplate actually ships, from its package.json.
BOILERPLATE_SCRIPTS: dict[str, dict[str, str]] = {
    "react-vite": {"dev": "vite", "test": "vitest", "type-check": "tsc --noEmit"},
    "react-vite-starter": {"dev": "vite", "test": "vitest run", "typecheck": "tsc --noEmit"},
    "react-rsbuild": {"dev": "rsbuild dev", "test": "vitest run", "typecheck": "tsc --noEmit"},
    "nextjs": {"dev": "next dev", "lint": "eslint"},
}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("react-vite", FrontendFramework.REACT_VITE),
        ("react-vite-starter", FrontendFramework.REACT_VITE_STARTER),
        ("react-rsbuild", FrontendFramework.REACT_RSBUILD),
        ("nextjs", FrontendFramework.NEXTJS),
    ],
)
def test_detects_framework_from_package_json(
    tmp_path: Path, name: str, expected: FrontendFramework
) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps({"name": "app", "scripts": BOILERPLATE_SCRIPTS[name]})
    )
    assert _detect_frontend_framework(tmp_path) is expected


def _project(tmp_path: Path, scripts: dict[str, str]) -> Path:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(json.dumps({"name": "app", "scripts": scripts}))
    return tmp_path


@pytest.mark.parametrize(
    ("name", "expected_command", "absent_command"),
    [
        ("react-vite", "bun run type-check", "bun run typecheck"),
        ("react-vite-starter", "bun run typecheck", "bun run type-check"),
        ("react-rsbuild", "bun run typecheck", "bun run type-check"),
    ],
)
def test_frontend_typecheck_job_uses_a_real_script(
    tmp_path: Path, name: str, expected_command: str, absent_command: str
) -> None:
    """A wrong script name fails the job on its first run."""
    project = _project(tmp_path, BOILERPLATE_SCRIPTS[name])
    workflow = _generate_github_actions(project, "fullstack", with_gauntlet=False)
    assert expected_command in workflow
    assert absent_command not in workflow


def test_nextjs_project_omits_the_test_job(tmp_path: Path) -> None:
    """nextjs-starter ships no test script, so no job can run one."""
    project = _project(tmp_path, BOILERPLATE_SCRIPTS["nextjs"])
    workflow = _generate_github_actions(project, "frontend-only", with_gauntlet=False)
    assert "frontend-test:" not in workflow
    assert "frontend-typecheck:" in workflow
    assert "frontend-lint:" in workflow


def test_gauntlet_job_is_present_when_requested(tmp_path: Path) -> None:
    """protect.py requires this exact status-check name."""
    project = _project(tmp_path, BOILERPLATE_SCRIPTS["react-vite"])
    workflow = _generate_github_actions(project, "fullstack", with_gauntlet=True)
    assert "  gauntlet:" in workflow
    assert "mattstack audit" in workflow


def test_gauntlet_job_is_absent_when_not_requested(tmp_path: Path) -> None:
    project = _project(tmp_path, BOILERPLATE_SCRIPTS["react-vite"])
    workflow = _generate_github_actions(project, "fullstack", with_gauntlet=False)
    assert "gauntlet:" not in workflow


def test_gitlab_emits_resolved_frontend_commands(tmp_path: Path) -> None:
    project = _project(tmp_path, BOILERPLATE_SCRIPTS["react-vite"])
    config = _generate_gitlab_ci(project, "fullstack", with_gauntlet=True)
    assert "bun run type-check" in config
    assert "gauntlet:" in config
    assert "mattstack audit" in config


def test_github_output_is_valid_yaml(tmp_path: Path) -> None:
    project = _project(tmp_path, BOILERPLATE_SCRIPTS["react-rsbuild"])
    import yaml

    workflow = _generate_github_actions(project, "fullstack", with_gauntlet=True)
    document = yaml.safe_load(workflow)
    assert "gauntlet" in document["jobs"]
    assert "backend-test" in document["jobs"]
    assert "frontend-typecheck" in document["jobs"]


def test_job_names_are_stable_for_branch_protection(tmp_path: Path) -> None:
    """protect.py hardcodes `gauntlet`; a rename silently blocks merges."""
    from mattstack.commands.protect import DEFAULT_STATUS_CHECKS

    project = _project(tmp_path, BOILERPLATE_SCRIPTS["react-vite"])
    workflow = _generate_github_actions(project, "fullstack", with_gauntlet=True)
    jobs = __import__("yaml").safe_load(workflow)["jobs"]
    for check in DEFAULT_STATUS_CHECKS:
        assert check in jobs, f"required status check {check!r} has no job"
