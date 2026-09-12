"""DigitalOcean App Platform deployment config templates."""

from __future__ import annotations

from mattstack.config import ProjectConfig


def generate_do_app_spec(config: ProjectConfig) -> str:
    """Generate .do/app.yaml App Platform spec."""
    lines: list[str] = [
        f"name: {config.name}",
        "region: nyc",
        "",
    ]

    services: list[str] = []
    databases: list[str] = []

    if config.has_backend:
        backend = [
            "services:",
            f"  - name: {config.name}-api",
            "    github:",
            "      repo: OWNER/REPO",
            "      branch: main",
            "      deploy_on_push: true",
            "    source_dir: backend",
            "    dockerfile_path: backend/Dockerfile",
            "    http_port: 8000",
            "    instance_count: 1",
            "    instance_size_slug: basic-xxs",
            "    routes:",
            "      - path: /api",
            "    health_check:",
            "      http_path: /api/health/",
            "      initial_delay_seconds: 15",
            "      period_seconds: 30",
            "    envs:",
            "      - key: DJANGO_SECRET_KEY",
            "        type: SECRET",
            "        value: ${DJANGO_SECRET_KEY}",
            "      - key: DJANGO_SETTINGS_MODULE",
            f"        value: {config.django_package}.settings",
            "      - key: DATABASE_URL",
            f"        value: ${{db-{config.name}.DATABASE_URL}}",
            "      - key: ALLOWED_HOSTS",
            "        value: ${APP_DOMAIN}",
        ]

        if config.use_redis:
            backend.extend(
                [
                    "      - key: REDIS_URL",
                    "        value: ${REDIS_URL}",
                ]
            )

        services.extend(backend)

        databases.extend(
            [
                "",
                "databases:",
                f"  - name: db-{config.name}",
                "    engine: PG",
                "    version: '16'",
                "    size: db-s-dev-database",
                "    num_nodes: 1",
            ]
        )

    if config.has_frontend:
        if services and not config.has_backend:
            services.append("services:")

        fe_build = "bun install && bun run build"
        fe_output = "dist"
        if config.is_nextjs:
            fe_output = ".next"

        fe_lines = [
            "" if services else "services:",
            f"  - name: {config.name}-frontend",
            "    github:",
            "      repo: OWNER/REPO",
            "      branch: main",
            "      deploy_on_push: true",
            "    source_dir: frontend",
        ]

        if config.is_nextjs:
            fe_lines.extend(
                [
                    "    dockerfile_path: frontend/Dockerfile",
                    "    http_port: 3000",
                    "    instance_count: 1",
                    "    instance_size_slug: basic-xxs",
                ]
            )
        else:
            fe_lines.extend(
                [
                    f"    build_command: {fe_build}",
                    f"    output_dir: {fe_output}",
                    "    environment_slug: node-js",
                ]
            )

        fe_lines.append("    routes:")
        fe_lines.append("      - path: /")

        if config.has_backend:
            env_key = "NEXT_PUBLIC_API_BASE_URL" if config.is_nextjs else "VITE_API_BASE_URL"
            fe_lines.extend(
                [
                    "    envs:",
                    f"      - key: {env_key}",
                    "        value: ${APP_URL}/api/v1",
                ]
            )

        if not services:
            services.append(fe_lines[0])
            services.extend(fe_lines[1:])
        else:
            services.extend(fe_lines)

    lines.extend(services)
    lines.extend(databases)

    return "\n".join(lines) + "\n"
