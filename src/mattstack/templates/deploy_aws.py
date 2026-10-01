"""AWS ECS task definitions and Copilot manifests.

Both build or run the generated production image. Every required variable is
an ECS ``secrets`` entry that reads one SSM parameter, so the task definition
holds no credentials and nothing parses a ``DATABASE_URL``. The task
definitions contain ``${AWS_ACCOUNT_ID}`` and ``${AWS_REGION}``; render them
with ``envsubst '$AWS_ACCOUNT_ID $AWS_REGION'`` before
``aws ecs register-task-definition``. Health checks run ``app-entrypoint
health`` inside the container, so no manifest needs shell expansion. Copilot reads
secrets stored by ``copilot secret init`` from its own parameter path.

Full-stack ECS runs the frontend and the API in one ``awsvpc`` task, which
shares ``localhost``; the load balancer targets the frontend. Full-stack
Copilot runs the frontend as the Load Balanced Web Service and the API as a
Backend Service that the frontend reaches through service discovery
(``<service>.<env>.<app>.local``).
"""

from __future__ import annotations

import json
from typing import Any

from mattstack.config import ProjectConfig
from mattstack.runtime_profiles import TaskProcess, task_processes
from mattstack.templates.deploy_runtime import (
    BACKEND_DOCKERFILE,
    ENTRYPOINT,
    FRONTEND_DOCKERFILE,
    api_service,
    health_path,
    required_env,
    tls_env,
)
from mattstack.templates.frontend_runtime import FRONTEND_PORT, api_prefix

_COPILOT_DOCS = "https://aws.github.io/copilot-cli/docs/manifest"
# The entrypoint's health mode sends an allowed Host and the edge's scheme.
_HEALTH = ["CMD", ENTRYPOINT, "health"]


def _web_env(config: ProjectConfig) -> dict[str, str]:
    """API settings: TLS at the edge, and the task IP for ALB health checks.

    Only a backend-only API sits directly behind the load balancer; in a
    full-stack task the load balancer targets the frontend.
    """
    env = dict(tls_env(config))
    if config.is_django_backend and not config.has_frontend:
        env["ALLOWED_HOSTS_INCLUDE_TASK_IP"] = "true"
    return env


def aws_files(config: ProjectConfig) -> dict[str, str]:
    """Return the ECS task definitions and Copilot manifests."""
    api = api_service(config)
    processes = task_processes(config, production=True)
    files = {
        "ecs-task-definition.json": generate_ecs_task_definition(config),
        f"copilot/{api}/manifest.yml": generate_copilot_manifest(config),
    }
    if config.has_frontend:
        files[f"copilot/{config.name}-frontend/manifest.yml"] = generate_copilot_frontend_manifest(
            config
        )
    for process in processes:
        name = f"{config.name}-{process.service}"
        files[f"ecs-{process.service}-task-definition.json"] = generate_ecs_task_definition(
            config, process
        )
        files[f"copilot/{name}/manifest.yml"] = generate_copilot_worker_manifest(config, process)
    return files


def generate_ecs_task_definition(config: ProjectConfig, process: TaskProcess | None = None) -> str:
    """Generate the Fargate task definition for the API or one task process."""
    name = api_service(config) if process is None else f"{config.name}-{process.service}"
    port = config.backend_api_port
    container: dict[str, Any] = {
        "name": name,
        "image": (
            "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/"
            f"{api_service(config)}:latest"
        ),
        "essential": True,
        "secrets": [
            {
                "name": req.name,
                "valueFrom": (
                    "arn:aws:ssm:${AWS_REGION}:${AWS_ACCOUNT_ID}:parameter/"
                    f"{config.name}/production/{req.name}"
                ),
            }
            for req in required_env(config)
            if process is None or not req.web_only
        ],
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {
                "awslogs-group": f"/ecs/{config.name}",
                "awslogs-region": "${AWS_REGION}",
                "awslogs-stream-prefix": name,
            },
        },
    }
    if process is None:
        container["portMappings"] = [{"containerPort": port, "protocol": "tcp"}]
        container["healthCheck"] = {
            "command": _HEALTH,
            "interval": 30,
            "timeout": 5,
            "retries": 3,
            "startPeriod": 30,
        }
        web_env = _web_env(config)
        if web_env:
            container["environment"] = [{"name": k, "value": v} for k, v in web_env.items()]
    else:
        # Keep the image entrypoint: the command runs after the startup check.
        container["command"] = list(process.argv)
    containers = [container]
    cpu, memory = "256", "512"
    if process is None and config.has_frontend:
        containers.insert(0, _ecs_frontend(config))
        cpu, memory = "512", "1024"
    task_def: dict[str, Any] = {
        "family": name,
        "networkMode": "awsvpc",
        "requiresCompatibilities": ["FARGATE"],
        "cpu": cpu,
        "memory": memory,
        "executionRoleArn": f"arn:aws:iam::${{AWS_ACCOUNT_ID}}:role/{config.name}-ecs-execution",
        "containerDefinitions": containers,
    }
    return json.dumps(task_def, indent=2) + "\n"


def _ecs_frontend(config: ProjectConfig) -> dict[str, Any]:
    """Frontend container in the API task; awsvpc tasks share localhost."""
    port = FRONTEND_PORT if config.is_nextjs else 80
    frontend: dict[str, Any] = {
        "name": f"{config.name}-frontend",
        "image": (
            "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/"
            f"{config.name}-frontend:latest"
        ),
        "essential": True,
        "portMappings": [{"containerPort": port, "protocol": "tcp"}],
        # The API container runs `app-entrypoint health` for every backend.
        "dependsOn": [{"containerName": api_service(config), "condition": "HEALTHY"}],
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {
                "awslogs-group": f"/ecs/{config.name}",
                "awslogs-region": "${AWS_REGION}",
                "awslogs-stream-prefix": f"{config.name}-frontend",
            },
        },
    }
    if not config.is_nextjs:
        # nginx renders API_UPSTREAM into its template at startup.
        frontend["environment"] = [
            {"name": "API_UPSTREAM", "value": f"http://localhost:{config.backend_api_port}"},
            {"name": "API_PREFIX", "value": api_prefix(config)},
        ]
    return frontend


def _copilot_secrets(config: ProjectConfig, *, web: bool) -> list[str]:
    lines = ["secrets:"]
    for req in required_env(config):
        if req.web_only and not web:
            continue
        path = "/copilot/${COPILOT_APPLICATION_NAME}/${COPILOT_ENVIRONMENT_NAME}/secrets"
        lines.append(f"  {req.name}: {path}/{req.name}")
    return lines


def _copilot_image(dockerfile: str = BACKEND_DOCKERFILE) -> list[str]:
    return [
        "image:",
        "  build:",
        f"    dockerfile: {dockerfile}",
        "    context: .",
    ]


def _discovery_origin(config: ProjectConfig) -> str:
    return (
        f"http://{api_service(config)}.${{COPILOT_ENVIRONMENT_NAME}}"
        f".${{COPILOT_APPLICATION_NAME}}.local:{config.backend_api_port}"
    )


def generate_copilot_manifest(config: ProjectConfig) -> str:
    """Generate the Copilot manifest for the API.

    Backend-only: a Load Balanced Web Service. Full-stack: a Backend Service
    behind the frontend, reachable only through service discovery.
    """
    head = [
        "# Generated by mattstack. Store each secret before deploying:",
        "#   copilot secret init --name <NAME>",
    ]
    if config.is_django_backend and not config.is_django_matt:
        head.extend(
            [
                "# The load balancer may serve HTTP only. Once the environment has an HTTPS",
                '# listener (a certificate), add USE_TLS: "true" under variables to enable',
                "# the HTTPS redirect, HSTS, and secure cookies.",
            ]
        )
    head.append(f"name: {api_service(config)}")
    if config.has_frontend:
        head[0:0] = [f"# Reference: {_COPILOT_DOCS}/backend-service/"]
        service = [
            "type: Backend Service",
            "",
            *_copilot_image(),
            f"  port: {config.backend_api_port}",
            "  healthcheck:",
            f"    command: {json.dumps(_HEALTH)}",
        ]
    else:
        head[0:0] = [f"# Reference: {_COPILOT_DOCS}/lb-web-service/"]
        service = [
            "type: Load Balanced Web Service",
            "",
            *_copilot_image(),
            f"  port: {config.backend_api_port}",
            "",
            "http:",
            "  path: '/'",
            "  healthcheck:",
            f"    path: '{health_path(config)}'",
            "    interval: 30s",
            "    timeout: 5s",
            "    healthy_threshold: 2",
            "    unhealthy_threshold: 3",
        ]
    web_env = _web_env(config)
    variables = ["", "variables:", *(f'  {k}: "{v}"' for k, v in web_env.items())]
    lines = [
        *head,
        *service,
        "",
        "cpu: 256",
        "memory: 512",
        "count: 1",
        *(variables if web_env else []),
        "",
        *_copilot_secrets(config, web=True),
    ]
    return "\n".join(lines) + "\n"


def generate_copilot_frontend_manifest(config: ProjectConfig) -> str:
    """Generate the Copilot Load Balanced Web Service for the frontend image."""
    port = FRONTEND_PORT if config.is_nextjs else 80
    upstream = _discovery_origin(config)
    image = _copilot_image(FRONTEND_DOCKERFILE)
    if config.is_nextjs:
        # next.config.ts bakes the rewrite target into the build.
        image.extend(["    args:", f"      INTERNAL_API_URL: {upstream}"])
    ecs_arg = (
        f" --build-arg INTERNAL_API_URL=http://localhost:{config.backend_api_port}"
        if config.is_nextjs
        else ""
    )
    lines = [
        "# Generated by mattstack.",
        f"# Reference: {_COPILOT_DOCS}/lb-web-service/",
        "# The ECS task definition runs the same frontend image beside the API, sharing",
        "# localhost. Build it for ECS with:",
        f"#   docker build -f {FRONTEND_DOCKERFILE}{ecs_arg} -t {config.name}-frontend .",
        f"name: {config.name}-frontend",
        "type: Load Balanced Web Service",
        "",
        *image,
        f"  port: {port}",
        "",
        "http:",
        "  path: '/'",
        "  healthcheck:",
        "    path: '/'",
        "",
        "cpu: 256",
        "memory: 512",
        "count: 1",
    ]
    if not config.is_nextjs:
        # nginx renders API_UPSTREAM into its template at startup.
        lines.extend(
            [
                "",
                "variables:",
                f"  API_UPSTREAM: {upstream}",
                f"  API_PREFIX: {api_prefix(config)}",
            ]
        )
    return "\n".join(lines) + "\n"


def generate_copilot_worker_manifest(config: ProjectConfig, process: TaskProcess) -> str:
    """Generate a Copilot Backend Service manifest for one task process."""
    lines = [
        "# Generated by mattstack. Reference:",
        "# https://aws.github.io/copilot-cli/docs/manifest/backend-service/",
        f"name: {config.name}-{process.service}",
        "type: Backend Service",
        "",
        *_copilot_image(),
        "",
        f"command: {json.dumps(process.command)}",
        "cpu: 256",
        "memory: 512",
        "count: 1",
        "",
        *_copilot_secrets(config, web=False),
    ]
    return "\n".join(lines) + "\n"
