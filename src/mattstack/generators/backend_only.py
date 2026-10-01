"""Backend-only project generator."""

from __future__ import annotations

from collections.abc import Callable

from mattstack.generators.base import BaseGenerator
from mattstack.post_processors.b2b import print_b2b_instructions
from mattstack.post_processors.consolidate import consolidate_backend
from mattstack.post_processors.customizer import customize_backend
from mattstack.templates.backend_entrypoint import generate_backend_entrypoint
from mattstack.templates.cursorrules import generate_cursorrules
from mattstack.templates.deploy_files import deployment_files
from mattstack.templates.docker_compose import generate_docker_compose
from mattstack.templates.docker_compose_override import generate_docker_compose_override
from mattstack.templates.docker_compose_prod import generate_docker_compose_prod
from mattstack.templates.dockerfiles import generate_backend_dockerfile
from mattstack.templates.pre_commit_config import generate_pre_commit_config
from mattstack.templates.root_claude_md import generate_claude_md
from mattstack.templates.root_env import (
    generate_env_example,
    generate_env_file,
    generate_env_production_example,
)
from mattstack.templates.root_gitignore import generate_gitignore
from mattstack.templates.root_makefile import generate_makefile
from mattstack.templates.root_readme import generate_readme
from mattstack.utils.console import print_error, print_info


class BackendOnlyGenerator(BaseGenerator):
    """Generate a backend-only project (Django API)."""

    @property
    def steps(self) -> list[tuple[str, Callable[[], bool]]]:
        return [
            ("Creating project directory", self._step_create_dir),
            ("Cloning backend", self._step_clone_backend),
            ("Consolidating monorepo", self._step_consolidate),
            ("Checking task and realtime runtime", self.prepare_runtime),
            ("Creating root files", self._step_create_root_files),
            ("Writing pre-commit config", self._write_pre_commit_config),
            ("Customizing backend", self._step_customize_backend),
            ("Writing project configuration", self.write_project_configuration),
            ("Initializing git", self._step_init_git),
            ("Finishing up", self._step_finish),
        ]

    def _step_create_dir(self) -> bool:
        return self.create_root_directory()

    def _step_clone_backend(self) -> bool:
        return self.clone_and_strip(self.config.backend_repo_key, "backend")

    def _step_consolidate(self) -> bool:
        try:
            consolidate_backend(self.config)
            return True
        except OSError as e:
            print_error(f"Failed to consolidate monorepo: {e}")
            return False

    def _step_create_root_files(self) -> bool:
        try:
            self.write_file("Makefile", generate_makefile(self.config))
            self.write_file("docker-compose.yml", generate_docker_compose(self.config))
            self.write_file("docker-compose.prod.yml", generate_docker_compose_prod(self.config))
            self.write_file(
                "docker-compose.override.yml.example",
                generate_docker_compose_override(self.config),
            )
            self.write_file(".env.example", generate_env_example(self.config))
            self.write_file(".env", generate_env_file(self.config))
            self.write_file(".env.production.example", generate_env_production_example(self.config))
            self.write_file(".env.production", generate_env_production_example(self.config))
            self.write_file("README.md", generate_readme(self.config))
            self.write_file("CLAUDE.md", generate_claude_md(self.config))
            self.write_file(".cursorrules", generate_cursorrules(self.config))
            self.write_file(".gitignore", generate_gitignore(self.config))
            self.write_file("tasks/todo.md", f"# {self.config.display_name} TODO\n")
            self.write_file("docker/backend/Dockerfile", generate_backend_dockerfile(self.config))
            self.write_file(
                "docker/backend/entrypoint.sh", generate_backend_entrypoint(self.config)
            )
            for relative, content in deployment_files(self.config).items():
                self.write_file(relative, content)

            return True
        except OSError as e:
            print_error(f"Failed to create root files: {e}")
            return False

    def _write_pre_commit_config(self) -> bool:
        try:
            self.write_file(".pre-commit-config.yaml", generate_pre_commit_config(self.config))
            return True
        except OSError as e:
            print_error(f"Failed to write pre-commit config: {e}")
            return False

    def _step_customize_backend(self) -> bool:
        if self.config.dry_run:
            print_info("[dry-run] Would customize backend")
            return True
        try:
            customize_backend(self.config)
            return True
        except Exception as e:
            print_error(f"Failed to customize backend: {e}")
            return False

    def _step_init_git(self) -> bool:
        return self.init_git_repository()

    def _step_finish(self) -> bool:
        if self.config.is_b2b:
            print_b2b_instructions(self.config)
        return True
