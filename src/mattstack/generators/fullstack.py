"""Fullstack monorepo generator (backend + frontend + optional iOS)."""

from __future__ import annotations

from collections.abc import Callable

from mattstack.config import DeploymentTarget
from mattstack.generators.base import BaseGenerator
from mattstack.post_processors.b2b import print_b2b_instructions
from mattstack.post_processors.consolidate import consolidate_backend, consolidate_frontend
from mattstack.post_processors.customizer import customize_backend, customize_frontend
from mattstack.post_processors.frontend_config import setup_frontend_monorepo
from mattstack.templates.cursorrules import generate_cursorrules
from mattstack.templates.docker_compose import generate_docker_compose
from mattstack.templates.docker_compose_override import generate_docker_compose_override
from mattstack.templates.docker_compose_prod import generate_docker_compose_prod
from mattstack.templates.dockerfiles import (
    generate_backend_dockerfile,
    generate_frontend_dev_dockerfile,
    generate_frontend_dockerfile,
    generate_frontend_nginx_conf,
)
from mattstack.templates.pre_commit_config import generate_pre_commit_config
from mattstack.templates.root_claude_md import generate_claude_md
from mattstack.templates.root_env import generate_env_example, generate_env_production_example
from mattstack.templates.root_gitignore import generate_gitignore
from mattstack.templates.root_makefile import generate_makefile
from mattstack.templates.root_readme import generate_readme
from mattstack.utils.console import print_error, print_info


class FullstackGenerator(BaseGenerator):
    """Generate a fullstack monorepo: backend + frontend + optional iOS."""

    @property
    def steps(self) -> list[tuple[str, Callable[[], bool]]]:
        steps: list[tuple[str, Callable[[], bool]]] = [
            ("Creating project directory", self._step_create_dir),
            ("Cloning backend", self._step_clone_backend),
            ("Cloning frontend", self._step_clone_frontend),
            ("Consolidating monorepo", self._step_consolidate),
            ("Creating root files", self._step_create_root_files),
            ("Writing pre-commit config", self._write_pre_commit_config),
            ("Customizing backend", self._step_customize_backend),
            ("Customizing frontend", self._step_customize_frontend),
            ("Writing project configuration", self.write_project_configuration),
            ("Initializing git", self._step_init_git),
            ("Finishing up", self._step_finish),
        ]

        # Insert iOS clone step if needed
        if self.config.include_ios:
            steps.insert(3, ("Cloning iOS starter", self._step_clone_ios))

        return steps

    def _step_create_dir(self) -> bool:
        return self.create_root_directory()

    def _step_clone_backend(self) -> bool:
        return self.clone_and_strip(self.config.backend_repo_key, "backend")

    def _step_clone_frontend(self) -> bool:
        return self.clone_and_strip(self.config.frontend_repo_key, "frontend")

    def _step_clone_ios(self) -> bool:
        return self.clone_and_strip("swift-ios", "ios")

    def _step_consolidate(self) -> bool:
        try:
            consolidate_backend(self.config)
            consolidate_frontend(self.config)
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
            self.write_file(".env", generate_env_example(self.config))
            self.write_file(".env.production.example", generate_env_production_example(self.config))
            self.write_file(".env.production", generate_env_production_example(self.config))
            self.write_file("README.md", generate_readme(self.config))
            self.write_file("CLAUDE.md", generate_claude_md(self.config))
            self.write_file(".cursorrules", generate_cursorrules(self.config))
            self.write_file(".gitignore", generate_gitignore(self.config))
            self.write_file("tasks/todo.md", f"# {self.config.display_name} TODO\n")
            # Consolidated Dockerfiles (build context = repo root)
            if self.config.has_backend:
                self.write_file(
                    "docker/backend/Dockerfile", generate_backend_dockerfile(self.config)
                )
            if self.config.has_frontend:
                self.write_file(
                    "docker/frontend/Dockerfile", generate_frontend_dockerfile(self.config)
                )
                self.write_file(
                    "docker/frontend/Dockerfile.dev", generate_frontend_dev_dockerfile(self.config)
                )
                if not self.config.is_nextjs:
                    self.write_file("docker/frontend/nginx.conf", generate_frontend_nginx_conf())

            # Deployment configs
            if self.config.deployment == DeploymentTarget.RAILWAY:
                from mattstack.templates.deploy_railway import (
                    generate_railway_json,
                    generate_railway_toml,
                )

                self.write_file("railway.json", generate_railway_json(self.config))
                self.write_file("railway.toml", generate_railway_toml(self.config))
            elif self.config.deployment == DeploymentTarget.RENDER:
                from mattstack.templates.deploy_render import generate_render_yaml

                self.write_file("render.yaml", generate_render_yaml(self.config))
            elif self.config.deployment == DeploymentTarget.FLY_IO:
                from mattstack.templates.deploy_fly import generate_fly_toml

                self.write_file("fly.toml", generate_fly_toml(self.config))
            elif self.config.deployment == DeploymentTarget.AWS:
                from mattstack.templates.deploy_aws import (
                    generate_copilot_manifest,
                    generate_ecs_task_definition,
                )

                self.write_file(
                    "ecs-task-definition.json",
                    generate_ecs_task_definition(self.config),
                )
                self.write_file(
                    "copilot/api/manifest.yml",
                    generate_copilot_manifest(self.config),
                )
            elif self.config.deployment == DeploymentTarget.GCP:
                from mattstack.templates.deploy_gcp import (
                    generate_app_engine_yaml,
                    generate_cloud_run_yaml,
                )

                self.write_file("service.yaml", generate_cloud_run_yaml(self.config))
                self.write_file("app.yaml", generate_app_engine_yaml(self.config))
            elif self.config.deployment == DeploymentTarget.HETZNER:
                from mattstack.templates.deploy_hetzner import (
                    generate_caddyfile,
                    generate_hetzner_compose,
                )

                self.write_file(
                    "docker-compose.prod.yml",
                    generate_hetzner_compose(self.config),
                )
                self.write_file("Caddyfile", generate_caddyfile(self.config))
            elif self.config.deployment == DeploymentTarget.SELF_HOSTED:
                from mattstack.templates.deploy_self_hosted import (
                    generate_nginx_conf,
                    generate_self_hosted_compose,
                    generate_systemd_service,
                )

                self.write_file(
                    "docker-compose.prod.yml",
                    generate_self_hosted_compose(self.config),
                )
                self.write_file("nginx.conf", generate_nginx_conf(self.config))
                self.write_file(
                    f"{self.config.name}.service",
                    generate_systemd_service(self.config),
                )
            elif self.config.deployment == DeploymentTarget.CLOUDFLARE:
                from mattstack.templates.deploy_cloudflare import generate_wrangler_toml

                self.write_file("wrangler.toml", generate_wrangler_toml(self.config))
            elif self.config.deployment == DeploymentTarget.DIGITAL_OCEAN:
                from mattstack.templates.deploy_digitalocean import (
                    generate_do_app_spec,
                )

                self.write_file(".do/app.yaml", generate_do_app_spec(self.config))
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

    def _step_customize_frontend(self) -> bool:
        if self.config.dry_run:
            print_info("[dry-run] Would customize frontend and configure its API proxy")
            return True
        try:
            customize_frontend(self.config)
            setup_frontend_monorepo(self.config)
            return True
        except Exception as e:
            print_error(f"Failed to customize frontend: {e}")
            return False

    def _step_init_git(self) -> bool:
        return self.init_git_repository()

    def _step_finish(self) -> bool:
        if self.config.is_b2b:
            print_b2b_instructions(self.config)
        return True
