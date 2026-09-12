"""Docker Compose override example template."""

from __future__ import annotations

from mattstack.config import ProjectConfig


def generate_docker_compose_override(config: ProjectConfig) -> str:
    """Generate docker-compose.override.yml.example for per-developer customization."""
    lines = [
        "# docker-compose.override.yml",
        "# Copy this file to docker-compose.override.yml for local customization.",
        "# This file is gitignored and will not be committed.",
        "#",
        "# Uncomment and modify sections as needed.",
        "",
        "services:",
    ]

    if config.has_backend:
        lines.extend(
            [
                "  # api-dev:",
                "  #   ports:",
                '  #     - "8001:8000"  # Use different host port',
                "  #   environment:",
                "  #     DEBUG: true",
                '  #     SECRET_KEY: "my-local-secret"',
                "  #   volumes:",
                "  #     - ./backend:/app",
                "",
            ]
        )

    if config.has_frontend:
        env_var = "NEXT_PUBLIC_API_BASE_URL" if config.is_nextjs else "VITE_API_BASE_URL"
        lines.extend(
            [
                "  # frontend-dev:",
                "  #   ports:",
                '  #     - "3001:3000"  # Use different host port',
                "  #   environment:",
                f'  #     {env_var}: "http://localhost:8001/api/v1"',
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
