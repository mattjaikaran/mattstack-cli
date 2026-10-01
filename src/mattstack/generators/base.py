"""Base generator with common functionality."""

from __future__ import annotations

import json
import re
import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from mattstack.config import ProjectConfig, get_repo_urls
from mattstack.templates.dockerfiles import generate_dockerignore
from mattstack.utils.console import (
    create_progress,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from mattstack.utils.git import (
    clone_repo,
    create_initial_commit,
    init_repo,
    remove_git_history,
)


class BaseGenerator(ABC):
    """Base class for project generators."""

    def __init__(self, config: ProjectConfig) -> None:
        self.config = config
        self.created_files: list[Path] = []
        self._owns_root = False

    def create_root_directory(self) -> bool:
        """Create the project root directory."""
        if self.config.dry_run:
            print_info(f"[dry-run] Would create directory: {self.config.path}")
            return True
        try:
            self.config.path.mkdir(parents=True, exist_ok=False)
            self._owns_root = True
            print_success(f"Created directory: {self.config.path}")
            return True
        except FileExistsError:
            print_error(f"Directory already exists: {self.config.path}")
            return False

    def clone_and_strip(self, repo_key: str, dest_name: str) -> bool:
        """Clone a repo and strip its .git history."""
        if self.config.dry_run:
            url = get_repo_urls()[repo_key]
            print_info(f"[dry-run] Would clone {url} into {dest_name}/")
            return True
        url = get_repo_urls()[repo_key]
        dest = self.config.path / dest_name
        if not clone_repo(url, dest):
            return False
        remove_git_history(dest)
        # Remove the cli/ directory from django boilerplate if present
        cli_dir = dest / "cli"
        if cli_dir.exists():
            shutil.rmtree(cli_dir)
        # Validate cloned contents have expected files
        return self._validate_clone(dest, dest_name)

    def _validate_clone(self, dest: Path, dest_name: str) -> bool:
        """Verify cloned repo contains expected files."""
        expected: dict[str, list[str]] = {
            "backend": ["pyproject.toml"],
            "frontend": ["package.json"],
            "ios": ["Package.swift"],
        }
        valid = True
        for filename in expected.get(dest_name, []):
            if not (dest / filename).exists():
                print_warning(f"Expected file '{filename}' not found in cloned {dest_name}")
                valid = False
        if not valid:
            print_error(f"Cloned {dest_name} is missing critical files")
        return valid

    def write_file(self, relative_path: str, content: str) -> None:
        """Write a file relative to the project root."""
        if self.config.dry_run:
            print_info(f"[dry-run] Would create {relative_path}")
            return
        file_path = self.config.path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        self.created_files.append(file_path)

    def update_file(
        self,
        file_path: Path,
        replacements: dict[str, str],
        *,
        warn_on_miss: bool = False,
    ) -> None:
        """Apply string replacements to a file."""
        if not file_path.exists():
            print_error(f"File not found: {file_path}")
            return
        content = file_path.read_text()
        for old, new in replacements.items():
            if warn_on_miss and old not in content:
                print_warning(f"Pattern not found in {file_path.name}: '{old[:50]}'")
            content = content.replace(old, new)
        file_path.write_text(content)

    def update_file_regex(self, file_path: Path, pattern: str, replacement: str) -> None:
        """Apply regex replacement to a file."""
        if not file_path.exists():
            print_error(f"File not found: {file_path}")
            return
        content = file_path.read_text()
        content = re.sub(pattern, replacement, content)
        file_path.write_text(content)

    def update_json_file(self, file_path: Path, updates: dict[str, object]) -> None:
        """Update fields in a JSON file (e.g., package.json)."""
        if not file_path.exists():
            print_error(f"File not found: {file_path}")
            return
        try:
            data = json.loads(file_path.read_text())
        except json.JSONDecodeError as e:
            print_error(f"Malformed JSON in {file_path.name}: {e}")
            return
        data.update(updates)
        file_path.write_text(json.dumps(data, indent=2) + "\n")

    def init_git_repository(self) -> bool:
        """Initialize a fresh git repo with initial commit."""
        if self.config.dry_run:
            print_info("[dry-run] Would initialize git repository")
            return True
        if not self.config.init_git:
            return True
        if not init_repo(self.config.path):
            print_error("Failed to initialize git repository")
            return False
        if not create_initial_commit(self.config.path):
            print_warning("Git repo initialized but initial commit failed")
            return True  # Non-fatal
        print_success("Initialized git repository")
        return True

    def cleanup(self) -> None:
        """Remove the project directory on failure."""
        if self._owns_root and not self.config.dry_run and self.config.path.exists():
            shutil.rmtree(self.config.path, ignore_errors=True)
            print_warning(f"Cleaned up partial project: {self.config.path}")

    @property
    @abstractmethod
    def steps(self) -> list[tuple[str, Callable[..., bool]]]:
        """Return list of (description, step_fn) tuples for the generator."""

    def run(self) -> bool:
        """Execute the generator steps with a progress bar."""
        with create_progress() as progress:
            task = progress.add_task("Generating project...", total=len(self.steps))
            for description, step_fn in self.steps:
                progress.update(task, description=description)
                try:
                    result = step_fn()
                except BaseException:
                    self.cleanup()
                    raise
                if result is False:
                    self.cleanup()
                    return False
                progress.advance(task)
        return True

    def prepare_runtime(self) -> bool:
        """Add TASK_BACKEND=none when needed, then check runtime prerequisites."""
        from mattstack.post_processors.task_runtime import prepare_runtime

        return prepare_runtime(self.config, dry_run=self.config.dry_run)

    def write_project_configuration(self) -> bool:
        """Write project metadata before the initial Git commit."""
        from mattstack.project import save_project_config
        from mattstack.templates.mattstack_yml import generate_mattstack_yml

        self.write_file("mattstack.yml", generate_mattstack_yml())
        self.write_file(".dockerignore", generate_dockerignore())
        if not self.config.dry_run:
            save_project_config(self.config)
        return True
