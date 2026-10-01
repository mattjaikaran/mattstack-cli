"""The generated push hook runs the backend gauntlet inside backend/."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
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


def test_gauntlet_entry_names_the_fix_when_uv_is_missing(
    tmp_path: Path, starter_fullstack_config: ProjectConfig
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "just").symlink_to(sys.executable)
    result = _run_gauntlet_entry(starter_fullstack_config, tmp_path / "project", bin_dir)
    assert result.returncode == 1
    assert "https://astral.sh/uv/install.sh" in result.stderr
