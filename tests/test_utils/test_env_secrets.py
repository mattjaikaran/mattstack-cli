"""The generated env files carry every secret the backend's own script lists."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mattstack.commands.init import run_init
from mattstack.config import source_env_var
from mattstack.project import parse_env_file

# The env var wins; otherwise use a sibling checkout next to this repository.
_SIBLING = Path(__file__).resolve().parents[3] / "django-ninja-boilerplate"
_SOURCE = os.environ.get(source_env_var("django-ninja")) or (
    str(_SIBLING) if (_SIBLING / "scripts" / "env_secrets.py").is_file() else ""
)


@pytest.mark.skipif(
    not _SOURCE or not Path(_SOURCE).is_dir(),
    reason="no MATTSTACK_SOURCE_DJANGO_NINJA and no ../django-ninja-boilerplate",
)
def test_env_files_match_backend_secret_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(source_env_var("django-ninja"), _SOURCE)
    run_init(name="drift", preset="starter-api", output_dir=tmp_path)
    root = tmp_path / "drift"
    listed = subprocess.run(
        [sys.executable, "scripts/env_secrets.py", "list", "--json"],
        cwd=root / "backend",
        capture_output=True,
        text=True,
        check=True,
    )
    names = [item["name"] for item in json.loads(listed.stdout)["secrets"]]
    assert names
    dev = parse_env_file(root / ".env")
    prod = parse_env_file(root / ".env.production")
    for name in names:
        # Booleans only, so pytest's assertion rewriting never prints a value.
        present = bool(dev.get(name)) and bool(prod.get(name))
        assert present, f"{name} is missing or empty"
        reused = dev[name] == prod[name]
        assert not reused, f"{name} is reused across environments"
