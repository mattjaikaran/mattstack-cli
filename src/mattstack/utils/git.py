"""Git utilities: clone, init, commit."""

from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404 # Required CLI subprocess support.
from pathlib import Path

from mattstack.utils.console import print_error
from mattstack.utils.sources import redact_repo

# `<transport>::<address>` runs a git remote helper (`ext::` runs any command).
_REMOTE_HELPER = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*::")


def clone_source_error(url: str) -> str | None:
    """Return why ``url`` is not an acceptable clone source, or None."""
    if not url or url.startswith("-"):
        return "a clone source must be a URL or path and must not start with '-'"
    if _REMOTE_HELPER.match(url):
        return "git remote-helper sources (`<transport>::<address>`) are not allowed"
    return None


def git_available() -> bool:
    return shutil.which("git") is not None


def clone_repo(url: str, destination: Path, branch: str | None = None, depth: int = 1) -> bool:
    """Shallow clone the requested branch, or the repository's default branch."""
    shown = redact_repo(url)
    error = clone_source_error(url)
    if error:
        print_error(f"Refusing to clone {shown}: {error}")
        return False
    command = ["git", "clone", "--depth", str(depth)]
    if branch:
        command.extend(["--branch", branch])
    command.extend(["--", url, str(destination)])
    try:
        subprocess.run(  # nosec B603 # Argv; trust project tools and PATH.
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to clone {shown}: {e.stderr.strip().replace(url, shown)}")
        return False
    except (OSError, subprocess.TimeoutExpired) as exc:
        print_error(f"Could not clone {shown}: {str(exc).replace(url, shown)}")
        return False


def copy_worktree(source: Path, destination: Path) -> bool:
    """Copy a local repository's working tree, including uncommitted changes.

    Copy tracked and untracked files that ``.gitignore`` does not exclude, so
    ``.env``, virtual environments, and ``node_modules`` stay behind.
    """
    try:
        result = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=source,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print_error(f"{source} is not a git working tree: {e.stderr.strip()}")
        return False
    except OSError as exc:
        print_error(f"Could not list files in {source}: {exc}")
        return False
    for relative in filter(None, result.stdout.split("\0")):
        origin = source / relative
        if not origin.is_file():
            continue  # Deleted in the working tree, or a submodule.
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target, follow_symlinks=False)
    return True


def remove_git_history(path: Path) -> bool:
    """Remove .git directory from a cloned repo."""
    git_dir = path / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)
    return True


def init_repo(path: Path) -> bool:
    """Initialize a new git repo."""
    try:
        subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
            ["git", "init"],
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to init git repo: {e.stderr.strip()}")
        return False
    except OSError as exc:
        print_error(f"Could not initialize git repository: {exc}")
        return False


def create_initial_commit(path: Path, message: str = "Initial commit") -> bool:
    """Stage all files and create initial commit."""
    try:
        subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
            ["git", "add", "."],
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
            ["git", "commit", "-m", message],
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create initial commit: {e.stderr.strip()}")
        return False
    except OSError as exc:
        print_error(f"Could not create initial commit: {exc}")
        return False


def get_git_user() -> tuple[str, str]:
    """Return (name, email) from git config, falling back to empty strings."""
    name = ""
    email = ""
    try:
        result = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
            ["git", "config", "user.name"], capture_output=True, text=True, check=True
        )
        name = result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    try:
        result = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
            ["git", "config", "user.email"], capture_output=True, text=True, check=True
        )
        email = result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return name, email
