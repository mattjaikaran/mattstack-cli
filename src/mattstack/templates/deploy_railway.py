"""Railway deployment config templates."""

from __future__ import annotations

import json
from typing import Any

from mattstack.config import ProjectConfig


def generate_railway_json(config: ProjectConfig) -> str:
    """Generate railway.json with build and deploy config."""
    deploy: dict[str, Any] = {
        "$schema": "https://railway.app/railway.schema.json",
        "build": {},
        "deploy": {},
    }

    if config.has_backend:
        deploy["build"]["builder"] = "NIXPACKS"
        deploy["build"]["buildCommand"] = "pip install uv && uv sync"
        deploy["deploy"]["startCommand"] = (
            "uv run python manage.py migrate && uv run python manage.py runserver 0.0.0.0:$PORT"
        )
        deploy["deploy"]["healthcheckPath"] = "/api/health/"
        deploy["deploy"]["healthcheckTimeout"] = 30
        deploy["deploy"]["restartPolicyType"] = "ON_FAILURE"
        deploy["deploy"]["restartPolicyMaxRetries"] = 3

    if config.has_frontend and not config.has_backend:
        deploy["build"]["builder"] = "NIXPACKS"
        deploy["build"]["buildCommand"] = "bun install && bun run build"
        deploy["deploy"]["startCommand"] = "bun run preview --host --port $PORT"

    return json.dumps(deploy, indent=2) + "\n"


def generate_railway_toml(config: ProjectConfig) -> str:
    """Generate railway.toml with service definitions."""
    sections: list[str] = []

    if config.has_backend:
        start_cmd = (
            "uv run python manage.py migrate && "
            f"uv run gunicorn {config.wsgi_app}.wsgi:application --bind 0.0.0.0:$PORT"
        )
        backend_section = f"""\
[build]
builder = "nixpacks"

[deploy]
startCommand = "{start_cmd}"
healthcheckPath = "/api/health/"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3"""
        sections.append(backend_section)

    if config.has_frontend and not config.has_backend:
        frontend_section = """\
[build]
builder = "nixpacks"
buildCommand = "bun install && bun run build"

[deploy]
startCommand = "bun run preview --host --port $PORT" """
        sections.append(frontend_section.rstrip())

    return "\n".join(sections) + "\n"
