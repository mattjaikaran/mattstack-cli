"""Git utilities: clone, init, commit."""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 # Required CLI subprocess support.
from pathlib import Path

from mattstack.utils.console import print_error


def git_available() -> bool:
    return shutil.which("git") is not None


def clone_repo(url: str, destination: Path, branch: str | None = None, depth: int = 1) -> bool:
    """Shallow clone the requested branch, or the repository's default branch."""
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
        print_error(f"Failed to clone {url}: {e.stderr.strip()}")
        return False
    except (OSError, subprocess.TimeoutExpired) as exc:
        print_error(f"Could not clone {url}: {exc}")
        return False


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
