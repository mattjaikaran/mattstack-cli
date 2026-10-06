"""Record which boilerplate commit each component came from.

`mattstack init` stores ``project.<component>.source`` (``repo``, ``commit``,
and ``dirty`` for a local working tree with uncommitted changes) in
mattstack.yml. `mattstack upgrade` uses that commit as the merge base.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404 # Required CLI subprocess support.
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from mattstack.config_file import load_project_section, write_project_section

COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")


def _git(directory: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
            ["git", *args],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def redact_repo(url: str) -> str:
    """Drop credentials from a repository URL before it is stored or printed."""
    parts = urlsplit(url)
    if not parts.scheme or "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit(parts._replace(netloc=host))


def source_revision(repo: str, checkout: Path, *, worktree: bool = False) -> dict[str, Any] | None:
    """Return the source record for ``checkout``, or None when it has no commit.

    ``worktree`` marks a copied local working tree, whose uncommitted changes
    are part of the copy.
    """
    if not (checkout / ".git").exists():
        return None
    head = (_git(checkout, "rev-parse", "HEAD") or "").strip()
    if not COMMIT_PATTERN.match(head):
        return None
    record: dict[str, Any] = {"repo": redact_repo(repo), "commit": head}
    if worktree and (_git(checkout, "status", "--porcelain") or "").strip():
        record["dirty"] = True
    return record


def recorded_source(config_file: Path, component: str) -> dict[str, Any] | None:
    """Return ``project.<component>.source`` from mattstack.yml when it names a commit."""
    section = load_project_section(config_file).get(component)
    source = section.get("source") if isinstance(section, dict) else None
    if isinstance(source, dict) and COMMIT_PATTERN.match(str(source.get("commit", ""))):
        return source
    return None


def record_sources(config_file: Path, sources: dict[str, dict[str, Any]]) -> None:
    """Store ``sources`` under each component's ``project`` entry in mattstack.yml."""
    section = load_project_section(config_file)
    if not section:
        return
    for component, record in sources.items():
        entry = section.get(component)
        if isinstance(entry, dict):
            entry["source"] = record
    write_project_section(config_file, section)


def advance_sources(config_file: Path, commits: dict[str, str]) -> None:
    """Set the recorded commit of each component that already has a source record."""
    sources = {
        component: {**source, "commit": commit}
        for component, commit in commits.items()
        if commit and (source := recorded_source(config_file, component))
    }
    if sources:
        record_sources(config_file, sources)
