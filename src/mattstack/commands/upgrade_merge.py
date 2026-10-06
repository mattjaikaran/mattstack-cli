"""Three-way upgrade against the boilerplate commit recorded in mattstack.yml.

``base`` is the recorded commit, ``theirs`` is the current upstream, and
``ours`` is the project's component directory. A file that upstream did not
change is never touched, so project customizations survive. A file that only
upstream changed is replaced; a file that both sides changed is merged with
``git merge-file``, and a merge with conflicts is reported, never written.
"""

from __future__ import annotations

import subprocess  # nosec B404 # Required CLI subprocess support.
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from mattstack.utils.git import clone_source_error, copy_worktree
from mattstack.utils.sources import COMMIT_PATTERN, redact_repo


@dataclass
class Revisions:
    """Checked-out base and upstream trees, or the reason they are missing."""

    base: Path
    theirs: Path
    upstream_commit: str = ""
    error: str | None = None


@dataclass
class ThreeWay:
    """Per-file classification of a three-way comparison."""

    new: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    merged: dict[str, bytes] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    removed_locally: list[str] = field(default_factory=list)
    deleted_upstream: list[str] = field(default_factory=list)


def _git(
    *args: str, cwd: Path | None = None, timeout: int = 300
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def fetch_revisions(url: str, commit: str, workdir: Path) -> Revisions:
    """Check out ``commit`` and the current upstream of ``url`` under ``workdir``.

    A local directory source contributes its working tree, including
    uncommitted changes, as the upstream side; `init` copies it the same way.
    """
    revisions = Revisions(base=workdir / "base", theirs=workdir / "theirs")
    if not COMMIT_PATTERN.match(commit):
        revisions.error = f"recorded commit is not a full SHA: {commit!r}"
        return revisions
    source_error = clone_source_error(url)
    if source_error:
        revisions.error = source_error
        return revisions
    clone = workdir / "repo"
    try:
        steps = [
            ("clone", ["clone", "--quiet", "--no-checkout", "--", url, str(clone)], None),
            (
                "base",
                ["worktree", "add", "--quiet", "--detach", str(revisions.base), commit],
                clone,
            ),
        ]
        local = Path(url).expanduser()
        if not local.is_dir():
            steps.append(
                (
                    "upstream",
                    ["worktree", "add", "--quiet", "--detach", str(revisions.theirs)],
                    clone,
                )
            )
        for label, args, cwd in steps:
            result = _git(*args, cwd=cwd)
            if result.returncode != 0:
                stderr = result.stderr.strip().replace(url, redact_repo(url))
                revisions.error = f"git {label} failed: {stderr}"
                return revisions
        if local.is_dir():
            if not copy_worktree(local, revisions.theirs):
                revisions.error = f"could not copy the working tree of {local}"
                return revisions
            revisions.upstream_commit = _git("rev-parse", "HEAD", cwd=local).stdout.strip()
        else:
            revisions.upstream_commit = _git("rev-parse", "HEAD", cwd=clone).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        revisions.error = f"git failed: {exc}"
    return revisions


def merge_file(ours: Path, base: bytes, theirs: Path) -> bytes | None:
    """Return the clean three-way merge of one file, or None on conflict or binary."""
    with tempfile.NamedTemporaryFile() as base_file:
        base_file.write(base)
        base_file.flush()
        result = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
            ["git", "merge-file", "-p", "--", str(ours), base_file.name, str(theirs)],
            capture_output=True,
            timeout=60,
        )
    return result.stdout if result.returncode == 0 else None


def classify(
    revisions: Revisions,
    ours: Path,
    comparable: Callable[[Path, Path], bool],
    writable: Callable[[Path], bool],
) -> ThreeWay:
    """Classify every upstream file against the merge base and the project."""
    result = ThreeWay()
    base_root, theirs_root = revisions.base, revisions.theirs
    for theirs_file in sorted(theirs_root.rglob("*")):
        rel = theirs_file.relative_to(theirs_root)
        if not comparable(theirs_file, rel):
            continue
        name, ours_file, base_file = str(rel), ours / rel, base_root / rel
        base = base_file.read_bytes() if base_file.is_file() else None
        upstream = theirs_file.read_bytes()
        if base == upstream or not writable(ours_file):
            continue
        if not ours_file.exists():
            # A file, or a directory holding it (consolidation drops `cli/`,
            # `docker/`, ...), that the project removed stays removed.
            removed = base is not None or any(
                (base_root / parent).is_dir() and not (ours / parent).exists()
                for parent in rel.parents
                if parent != Path(".")
            )
            (result.removed_locally if removed else result.new).append(name)
            continue
        current = ours_file.read_bytes()
        if current == upstream:
            continue
        if current == base:
            result.updated.append(name)
            continue
        merged = merge_file(ours_file, base or b"", theirs_file)
        if merged is None:
            result.conflicts.append(name)
        elif merged != current:  # Equal when the project already has upstream's change.
            result.merged[name] = merged
    for base_file in sorted(base_root.rglob("*")):
        rel = base_file.relative_to(base_root)
        upstream_deleted = comparable(base_file, rel) and not (theirs_root / rel).exists()
        if upstream_deleted and (ours / rel).is_file():
            result.deleted_upstream.append(str(rel))
    return result
