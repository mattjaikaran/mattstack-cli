"""The generated push hook runs the backend gauntlet inside backend/."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import yaml

from mattstack.config import ProjectConfig
from mattstack.templates.pre_commit_config import generate_pre_commit_config


def _run_gauntlet_entry(
    config: ProjectConfig, root: Path, bin_dir: Path
) -> subprocess.CompletedProcess[str]:
    """Run the hook entry with a PATH that holds only bash and ``bin_dir``'s tools."""
    bash = shutil.which("bash")
    assert bash is not None
    (bin_dir / "bash").symlink_to(bash)
    data = yaml.safe_load(generate_pre_commit_config(config))
    hooks = {hook["id"]: hook for repo in data["repos"] for hook in repo["hooks"]}
    (root / "backend").mkdir(parents=True)
    return subprocess.run(
        shlex.split(hooks["backend-gauntlet-quick"]["entry"]),
        cwd=root,
        env={**os.environ, "PATH": str(bin_dir)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_gauntlet_entry_names_the_fix_when_just_is_missing(
    tmp_path: Path, starter_fullstack_config: ProjectConfig
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    result = _run_gauntlet_entry(starter_fullstack_config, tmp_path / "project", bin_dir)
    assert result.returncode == 1
    assert "uv tool install rust-just" in result.stderr


def test_gauntlet_entry_runs_the_root_backend_recipe(
    tmp_path: Path, starter_fullstack_config: ProjectConfig
) -> None:
    """The boilerplate justfile is dropped, so the hook uses the root recipe."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "just-args"
    fake_just = bin_dir / "just"
    fake_just.write_text(f'#!/bin/sh\necho "$@" > {log}\n', encoding="utf-8")
    fake_just.chmod(0o755)
    result = _run_gauntlet_entry(starter_fullstack_config, tmp_path / "project", bin_dir)
    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").strip() == "backend-gauntlet-quick"
