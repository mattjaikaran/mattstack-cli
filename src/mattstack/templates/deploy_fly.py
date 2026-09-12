"""Fly.io deployment config templates."""

from __future__ import annotations

from mattstack.config import ProjectConfig


def generate_fly_toml(config: ProjectConfig) -> str:
    """Generate fly.toml for Fly.io deployment."""
    app_name = config.name

    sections: list[str] = [f'app = "{app_name}"', 'primary_region = "iad"', ""]

    if config.has_backend:
        sections.extend(
            [
                "[build]",
                '  dockerfile = "backend/Dockerfile"',
                "",
                "[env]",
                f'  DJANGO_SETTINGS_MODULE = "{config.wsgi_app}.settings"',
                '  PYTHONUNBUFFERED = "1"',
                "",
                "[http_service]",
                "  internal_port = 8000",
                "  force_https = true",
                "  auto_stop_machines = true",
                "  auto_start_machines = true",
                "  min_machines_running = 0",
                "",
                "[[http_service.checks]]",
                '  grace_period = "10s"',
                '  interval = "30s"',
                '  method = "GET"',
                '  path = "/api/health/"',
                '  timeout = "5s"',
                "",
                "[[vm]]",
                '  size = "shared-cpu-1x"',
                '  memory = "512mb"',
            ]
        )
    elif config.has_frontend:
        sections.extend(
            [
                "[build]",
                '  dockerfile = "frontend/Dockerfile"',
                "",
                "[http_service]",
                "  internal_port = 3000",
                "  force_https = true",
                "  auto_stop_machines = true",
                "  auto_start_machines = true",
                "",
                "[[vm]]",
                '  size = "shared-cpu-1x"',
                '  memory = "256mb"',
            ]
        )

    return "\n".join(sections) + "\n"
