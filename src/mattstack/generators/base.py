"""Base generator with common functionality."""

from __future__ import annotations

import json
import re
import shutil
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mattstack.config import ProjectConfig, get_repo_urls
from mattstack.templates.agent_files import agent_files
from mattstack.templates.dockerfiles import generate_dockerignore
from mattstack.templates.gauntlet_toml import generate_gauntlet_toml
from mattstack.utils.console import (
    create_progress,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from mattstack.utils.git import (
    clone_repo,
    copy_worktree,
    create_initial_commit,
    init_repo,
    remove_git_history,
)
from mattstack.utils.sources import record_sources, redact_repo, source_revision
from mattstack.utils.versions import snapshot_pins


def project_dir_is_free(path: Path) -> bool:
    """Return True when the path is absent or an empty directory."""
    return not path.exists() or (path.is_dir() and not any(path.iterdir()))


class BaseGenerator(ABC):
    """Base class for project generators."""

    def __init__(self, config: ProjectConfig) -> None:
        self.config = config
        self.created_files: list[Path] = []
        self._owns_root = False
        self._preexisting_empty_root = False
        # Component dir name -> {repo, commit[, dirty]} for mattstack.yml.
        self.sources: dict[str, dict[str, Any]] = {}

    def create_root_directory(self) -> bool:
        """Create the project root directory."""
        if self.config.dry_run:
            print_info(f"[dry-run] Would create directory: {self.config.path}")
            return True
        if not project_dir_is_free(self.config.path):
            print_error(f"Directory already exists: {self.config.path}")
            return False
        existed = self.config.path.exists()
        try:
            self.config.path.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            print_error(f"Directory already exists: {self.config.path}")
            return False
        self._owns_root = not existed
        self._preexisting_empty_root = existed
        print_success(f"Created directory: {self.config.path}")
        return True

    def clone_and_strip(self, repo_key: str, dest_name: str) -> bool:
        """Clone a repo and strip its .git history."""
        url = get_repo_urls()[repo_key]
        shown = redact_repo(url)
        if self.config.dry_run:
            print_info(f"[dry-run] Would clone {shown} into {dest_name}/")
            return True
        dest = self.config.path / dest_name
        local = Path(url).expanduser()
        if local.is_dir():
            print_info(f"Copying the {repo_key} working tree from {local}")
            if not copy_worktree(local, dest):
                return False
            record = source_revision(url, local, worktree=True)
        elif not clone_repo(url, dest):
            return False
        else:
            record = source_revision(url, dest)
        if record:
            self.sources[dest_name] = record
        remove_git_history(dest)
        if dest_name == "backend":
            # Consolidation later removes the Compose files and Dockerfile.
            self.config.source_pins = snapshot_pins(self.config.path)
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

    def write_agent_files(self) -> None:
        """Write root AGENTS.md and its adapters, Claude settings, MCP, and gauntlet.toml."""
        for relative, content in agent_files(self.config).items():
            self.write_file(relative, content)
        self.write_file("gauntlet.toml", generate_gauntlet_toml(self.config))

    def write_env_files(self) -> None:
        """Write the env examples, then private env files with generated secrets.

        ``.env`` and ``.env.production`` get separate values, mode 0600, and
        are never overwritten. A django-ninja backend's own
        ``scripts/env_secrets.py`` generates them from the examples; a missing
        or failing script raises ``SecretsScriptError``. Only names print.
        ``.env`` records a free host port for each published service, so it
        never points host-mode commands at a host server on a Compose default.
        """
        from mattstack.templates.root_env import (
            generate_env_example,
            generate_env_file,
            generate_env_production_example,
            generate_env_production_file,
        )
        from mattstack.utils.env_secrets import (
            delegates_secrets,
            run_backend_script,
            secret_names,
            write_private_file,
        )
        from mattstack.utils.ports import free_host_ports, write_env_ports

        ports = free_host_ports(self._preferred_ports())
        self.write_file(".env.example", generate_env_example(self.config))
        self.write_file(".env.production.example", generate_env_production_example(self.config))
        delegate = delegates_secrets(self.config)
        names = ", ".join(secret_names(self.config)) or "none"
        for relative, render in (
            (".env", generate_env_file),
            (".env.production", generate_env_production_file),
        ):
            if self.config.dry_run:
                print_info(f"[dry-run] Would create {relative} (mode 0600) with fresh secrets")
                continue
            path = self.config.path / relative
            if path.exists():
                print_warning(f"Kept existing {relative}; generated no new secrets")
                continue
            if delegate:
                template = self.config.path / f"{relative}.example"
                summary = run_backend_script(self.config.backend_dir, path, template)
                print_info(f"{relative} (mode 0600): {summary}")
            elif write_private_file(path, render(self.config)):
                print_info(f"Generated {relative} (mode 0600; secrets: {names})")
            if relative == ".env" and path.is_file():
                write_env_ports(path, ports)
            self.created_files.append(path)

    def _preferred_ports(self) -> dict[str, int]:
        """Return the host-side env names and defaults the root Compose publishes."""
        from mattstack.templates.frontend_runtime import FRONTEND_PORT
        from mattstack.templates.root_env import DB_PORT, REDIS_PORT

        ports = {"API_PORT": self.config.backend_api_port, "FRONTEND_PORT": FRONTEND_PORT}
        if self.config.has_backend:
            ports["DB_PORT"] = DB_PORT
            if self.config.use_redis:
                ports["REDIS_PORT"] = REDIS_PORT
        return ports

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
        """Remove what this run wrote when a step fails."""
        if self.config.dry_run or not self.config.path.exists():
            return
        if self._owns_root:
            shutil.rmtree(self.config.path, ignore_errors=True)
        elif self._preexisting_empty_root:
            # The user created the root, so keep it and remove only this run's files.
            for child in self.config.path.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
        else:
            return
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
            record_sources(self.config.path / "mattstack.yml", self.sources)
        return True
