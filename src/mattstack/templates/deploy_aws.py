"""AWS deployment config templates."""

from __future__ import annotations

import json
from typing import Any

from mattstack.config import ProjectConfig


def generate_ecs_task_definition(config: ProjectConfig) -> str:
    pkg = config.wsgi_app
    """Generate ECS task definition JSON."""
    task_def: dict[str, Any] = {
        "family": f"{config.name}-task",
        "networkMode": "awsvpc",
        "requiresCompatibilities": ["FARGATE"],
        "cpu": "256",
        "memory": "512",
        "executionRoleArn": f"arn:aws:iam::role/{config.name}-execution-role",
        "containerDefinitions": [],
    }

    if config.has_backend:
        task_def["containerDefinitions"].append(
            {
                "name": f"{config.name}-api",
                "image": f"{config.name}-api:latest",
                "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
                "environment": [
                    {"name": "DJANGO_SETTINGS_MODULE", "value": f"{pkg}.settings"},
                    {"name": "PYTHONUNBUFFERED", "value": "1"},
                ],
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": f"/ecs/{config.name}",
                        "awslogs-region": "us-east-1",
                        "awslogs-stream-prefix": "api",
                    },
                },
                "healthCheck": {
                    "command": ["CMD-SHELL", "curl -f http://localhost:8000/api/health/ || exit 1"],
                    "interval": 30,
                    "timeout": 5,
                    "retries": 3,
                },
            }
        )

    if config.has_frontend and not config.has_backend:
        task_def["containerDefinitions"].append(
            {
                "name": f"{config.name}-frontend",
                "image": f"{config.name}-frontend:latest",
                "portMappings": [{"containerPort": 3000, "protocol": "tcp"}],
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": f"/ecs/{config.name}",
                        "awslogs-region": "us-east-1",
                        "awslogs-stream-prefix": "frontend",
                    },
                },
            }
        )

    return json.dumps(task_def, indent=2) + "\n"


def generate_copilot_manifest(config: ProjectConfig) -> str:
    pkg = config.wsgi_app
    """Generate AWS Copilot service manifest YAML."""
    lines: list[str] = [
        f"name: {config.name}-api",
        "type: Load Balanced Web Service",
        "",
        "image:",
        "  build: backend/Dockerfile",
        "  port: 8000",
        "",
        "http:",
        "  path: '/'",
        "  healthcheck:",
        "    path: '/api/health/'",
        "    interval: 30s",
        "    timeout: 5s",
        "    healthy_threshold: 2",
        "    unhealthy_threshold: 3",
        "",
        "cpu: 256",
        "memory: 512",
        "count: 1",
        "",
        "variables:",
        f"  DJANGO_SETTINGS_MODULE: {pkg}.settings",
        "  PYTHONUNBUFFERED: 1",
    ]
    return "\n".join(lines) + "\n"
