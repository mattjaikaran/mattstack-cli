"""Docker Compose override example template."""

from __future__ import annotations

from mattstack.config import ProjectConfig


def generate_docker_compose_override(config: ProjectConfig) -> str:
    """Generate docker-compose.override.yml.example for per-developer customization.

    Compose appends `ports:` lists from an override to the base file, so an
    override that lists a new mapping publishes both the old and the new port
    and collides with other projects. Change host ports in `.env` instead; the
    base file reads API_PORT, FRONTEND_PORT, DB_PORT, and REDIS_PORT.
    """
    lines = [
        "# docker-compose.override.yml",
        "# Copy this file to docker-compose.override.yml for local customization.",
        "# This file is gitignored and will not be committed.",
        "#",
        "# To change a published port, set API_PORT, FRONTEND_PORT, DB_PORT, or",
        "# REDIS_PORT in .env. Do not add `ports:` here: Compose appends them to",
        "# the base mapping, so both ports are published. If you must replace the",
        "# list, use `ports: !override` (Compose 2.24 or later).",
        "#",
        "# The file is valid as copied: each service below starts as an empty",
        "# mapping. Replace `{}` with settings, such as the commented examples.",
        "",
        "services:",
    ]

    if config.has_backend:
        lines.extend(
            [
                "  api-dev: {}",
                "  # api-dev:",
                "  #   environment:",
                '  #     DEBUG: "true"',
                '  #     SECRET_KEY: "my-local-secret"',
                "",
            ]
        )

    if config.has_frontend:
        lines.extend(
            [
                "  frontend-dev: {}",
                "  # frontend-dev:",
                "  #   environment:",
                '  #     CHOKIDAR_USEPOLLING: "true"  # file watching on some mounts',
                "",
            ]
        )

    lines.extend(
        [
            "  # --- Add custom services below ---",
            "  # mailhog:",
            "  #   image: mailhog/mailhog",
            "  #   ports:",
            '  #     - "8025:8025"',
            '  #     - "1025:1025"',
        ]
    )

    return "\n".join(lines) + "\n"
