"""Hetzner deployment config templates (Docker Compose + Caddy)."""

from __future__ import annotations

from mattstack.config import ProjectConfig


def generate_hetzner_compose(config: ProjectConfig) -> str:
    pkg = config.wsgi_app
    """Generate docker-compose.prod.yml for Hetzner with Caddy."""
    lines: list[str] = [
        "version: '3.8'",
        "",
        "services:",
        "  caddy:",
        "    image: caddy:2-alpine",
        "    restart: unless-stopped",
        "    ports:",
        '      - "80:80"',
        '      - "443:443"',
        "    volumes:",
        "      - ./Caddyfile:/etc/caddy/Caddyfile",
        "      - caddy_data:/data",
        "      - caddy_config:/config",
        "    depends_on:",
    ]

    if config.has_backend:
        lines.append("      - api")
    if config.has_frontend:
        lines.append("      - frontend")

    if config.has_backend:
        lines.extend(
            [
                "",
                "  api:",
                "    build: ./backend",
                f"    command: gunicorn {pkg}.wsgi:application --bind 0.0.0.0:8000",
                "    restart: unless-stopped",
                "    env_file: .env",
                "    expose:",
                '      - "8000"',
                "    depends_on:",
                "      - db",
            ]
        )
        if config.use_redis:
            lines.append("      - redis")

    lines.extend(
        [
            "",
            "  db:",
            "    image: postgres:16-alpine",
            "    restart: unless-stopped",
            "    volumes:",
            "      - postgres_data:/var/lib/postgresql/data",
            "    environment:",
            "      POSTGRES_DB: ${POSTGRES_DB:-app}",
            "      POSTGRES_USER: ${POSTGRES_USER:-postgres}",
            "      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}",
        ]
    )

    if config.use_redis:
        lines.extend(
            [
                "",
                "  redis:",
                "    image: redis:7-alpine",
                "    restart: unless-stopped",
            ]
        )

    if config.has_frontend:
        lines.extend(
            [
                "",
                "  frontend:",
                "    build: ./frontend",
                "    restart: unless-stopped",
                "    expose:",
                '      - "3000"',
            ]
        )

    lines.extend(
        [
            "",
            "volumes:",
            "  postgres_data:",
            "  caddy_data:",
            "  caddy_config:",
        ]
    )

    return "\n".join(lines) + "\n"


def generate_caddyfile(config: ProjectConfig) -> str:
    """Generate Caddyfile for reverse proxy with auto-HTTPS."""
    lines: list[str] = [
        f"{config.name}.example.com {{",
    ]

    if config.has_backend and config.has_frontend:
        lines.extend(
            [
                "    handle /api/* {",
                "        reverse_proxy api:8000",
                "    }",
                "    handle /admin/* {",
                "        reverse_proxy api:8000",
                "    }",
                "    handle {",
                "        reverse_proxy frontend:3000",
                "    }",
            ]
        )
    elif config.has_backend:
        lines.extend(
            [
                "    reverse_proxy api:8000",
            ]
        )
    elif config.has_frontend:
        lines.extend(
            [
                "    reverse_proxy frontend:3000",
            ]
        )

    lines.append("}")
    return "\n".join(lines) + "\n"
