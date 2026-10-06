"""Three-way upgrade against the boilerplate commit recorded in mattstack.yml."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from mattstack.commands.upgrade import run_upgrade

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

PYPROJECT = "[project]\nname = 'myapp'\ndependencies = ['django-ninja']\n"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, files: dict[str, str]) -> str:
    for name, content in files.items():
        (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "change")
    return _git(repo, "rev-parse", "HEAD")


def test_upgrade_merges_against_recorded_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    _git(upstream, "init", "-q")
    base = _commit(
        upstream,
        {
            "pyproject.toml": PYPROJECT,
            "settings.py": "one\ntwo\nthree\n",
            "urls.py": "x\n",
            "views.py": "upstream\n",
            "models.py": "keep\n",
        },
    )
    project = tmp_path / "proj"
    backend = project / "backend"
    backend.mkdir(parents=True)
    for name in ("pyproject.toml", "settings.py", "urls.py", "views.py", "models.py"):
        shutil.copy(upstream / name, backend / name)
    source = {"repo": str(upstream), "commit": base}
    (project / "mattstack.yml").write_text(
        yaml.safe_dump({"project": {"backend": {"framework": "django-ninja", "source": source}}}),
        encoding="utf-8",
    )
    # Project customizations.
    (backend / "settings.py").write_text("one-mine\ntwo\nthree\n", encoding="utf-8")
    (backend / "views.py").write_text("mine\n", encoding="utf-8")
    (backend / "models.py").write_text("customized\n", encoding="utf-8")
    # Upstream moves on.
    _commit(
        upstream,
        {
            "settings.py": "one\ntwo\nthree-up\n",
            "urls.py": "y\n",
            "views.py": "theirs\n",
            "new.py": "new\n",
        },
    )
    monkeypatch.setenv("MATTSTACK_SOURCE_DJANGO_NINJA", str(upstream))

    run_upgrade(project, force=True)

    # Both sides changed different lines: merged.
    assert (backend / "settings.py").read_text() == "one-mine\ntwo\nthree-up\n"
    # Only upstream changed: replaced. New upstream file: added.
    assert (backend / "urls.py").read_text() == "y\n"
    assert (backend / "new.py").read_text() == "new\n"
    # Upstream did not change it: the customization survives.
    assert (backend / "models.py").read_text() == "customized\n"
    # Conflict: never written, and the merge base stays put.
    assert (backend / "views.py").read_text() == "mine\n"
    recorded = yaml.safe_load((project / "mattstack.yml").read_text())
    assert recorded["project"]["backend"]["source"]["commit"] == base
