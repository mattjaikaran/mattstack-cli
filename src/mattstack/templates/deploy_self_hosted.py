"""Self-hosted deployment config templates (Docker Compose + nginx + systemd)."""

from __future__ import annotations

from mattstack.config import ProjectConfig


def generate_self_hosted_compose(config: ProjectConfig) -> str:
    pkg = config.wsgi_app
    """Generate docker-compose.prod.yml for self-hosted with nginx."""
    lines: list[str] = [
        "version: '3.8'",
        "",
        "services:",
        "  nginx:",
        "    image: nginx:alpine",
        "    restart: unless-stopped",
        "    ports:",
        '      - "80:80"',
        '      - "443:443"',
        "    volumes:",
        "      - ./nginx.conf:/etc/nginx/conf.d/default.conf",
        "      - ./certbot/conf:/etc/letsencrypt",
        "      - ./certbot/www:/var/www/certbot",
        "    depends_on:",
    ]

    if config.has_backend:
        lines.append("      - api")
    if config.has_frontend:
        lines.append("      - frontend")

    lines.extend(
        [
            "",
            "  certbot:",
            "    image: certbot/certbot",
            "    entrypoint: \"/bin/sh -c 'trap exit TERM; while :; "
            "do certbot renew; sleep 12h & wait $${!}; done;'\"",
            "    volumes:",
            "      - ./certbot/conf:/etc/letsencrypt",
            "      - ./certbot/www:/var/www/certbot",
        ]
    )

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
        ]
    )

    return "\n".join(lines) + "\n"


def generate_nginx_conf(config: ProjectConfig) -> str:
    """Generate nginx reverse proxy config."""
    lines: list[str] = [
        "server {",
        "    listen 80;",
        f"    server_name {config.name}.example.com;",
        "",
        "    # Certbot challenge",
        "    location /.well-known/acme-challenge/ {",
        "        root /var/www/certbot;",
        "    }",
        "",
        "    location / {",
        "        return 301 https://$host$request_uri;",
        "    }",
        "}",
        "",
        "server {",
        "    listen 443 ssl;",
        f"    server_name {config.name}.example.com;",
        "",
        f"    ssl_certificate /etc/letsencrypt/live/{config.name}.example.com/fullchain.pem;",
        f"    ssl_certificate_key /etc/letsencrypt/live/{config.name}.example.com/privkey.pem;",
        "",
    ]

    if config.has_backend and config.has_frontend:
        lines.extend(
            [
                "    location /api/ {",
                "        proxy_pass http://api:8000;",
                "        proxy_set_header Host $host;",
                "        proxy_set_header X-Real-IP $remote_addr;",
                "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
                "        proxy_set_header X-Forwarded-Proto $scheme;",
                "    }",
                "",
                "    location /admin/ {",
                "        proxy_pass http://api:8000;",
                "        proxy_set_header Host $host;",
                "        proxy_set_header X-Real-IP $remote_addr;",
                "    }",
                "",
                "    location / {",
                "        proxy_pass http://frontend:3000;",
                "        proxy_set_header Host $host;",
                "        proxy_set_header X-Real-IP $remote_addr;",
                "    }",
            ]
        )
    elif config.has_backend:
        lines.extend(
            [
                "    location / {",
                "        proxy_pass http://api:8000;",
                "        proxy_set_header Host $host;",
                "        proxy_set_header X-Real-IP $remote_addr;",
                "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
                "        proxy_set_header X-Forwarded-Proto $scheme;",
                "    }",
            ]
        )
    elif config.has_frontend:
        lines.extend(
            [
                "    location / {",
                "        proxy_pass http://frontend:3000;",
                "        proxy_set_header Host $host;",
                "        proxy_set_header X-Real-IP $remote_addr;",
                "    }",
            ]
        )

    lines.append("}")
    return "\n".join(lines) + "\n"


def generate_systemd_service(config: ProjectConfig) -> str:
    """Generate systemd unit file for docker-compose."""
    return f"""\
[Unit]
Description={config.display_name} Application
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/{config.name}
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
"""
