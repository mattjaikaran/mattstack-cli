"""Google Cloud Run: one service plus one worker pool per task process.

Every required variable reads one Secret Manager secret (``secretKeyRef``),
so no file holds a credential and nothing parses a ``DATABASE_URL``. Images
contain ``${PROJECT_ID}`` and ``${REGION}``; render each file with
``envsubst`` before ``gcloud run ... replace``.

- Backend only: the API container is the ingress container.
- Full-stack: the frontend container is the ingress container and the API is
  a sidecar on ``localhost`` (https://cloud.google.com/run/docs/deploying#sidecars).
  The ``container-dependencies`` annotation starts the API first.
- Task processes: ``kind: WorkerPool`` with one manually scaled instance
  (https://cloud.google.com/run/docs/reference/yaml/v1). ``args`` keeps the
  image entrypoint, so workers run the same startup check.

App Engine is not generated: the standard runtime builds from the directory
that holds ``app.yaml`` with its own Python toolchain, so it cannot build the
``backend/`` uv project or run the django-matt ASGI server.
"""

from __future__ import annotations

from mattstack.config import ProjectConfig
from mattstack.runtime_profiles import TaskProcess, task_processes
from mattstack.templates.deploy_runtime import (
    BACKEND_DOCKERFILE,
    FRONTEND_DOCKERFILE,
    MIGRATE_COMMAND,
    api_service,
    health_path,
    required_env,
    tls_env,
)
from mattstack.templates.frontend_runtime import FRONTEND_PORT, api_prefix

_REGISTRY = "${REGION}-docker.pkg.dev/${PROJECT_ID}"


def gcp_files(config: ProjectConfig) -> dict[str, str]:
    """Return service.yaml plus workerpool-<service>.yaml per task process."""
    files = {"service.yaml": generate_cloud_run_yaml(config)}
    for process in task_processes(config, production=True):
        files[f"workerpool-{process.service}.yaml"] = generate_worker_pool_yaml(config, process)
    return files


def _image(config: ProjectConfig, role: str) -> str:
    return f"{_REGISTRY}/{config.name}/{config.name}-{role}:latest"


def _secret_env(config: ProjectConfig, *, web: bool, indent: int) -> list[str]:
    pad = " " * indent
    lines = [f"{pad}env:"]
    for req in required_env(config):
        if req.web_only and not web:
            continue
        lines.extend(
            [
                f"{pad}  - name: {req.name}",
                f"{pad}    valueFrom:",
                f"{pad}      secretKeyRef:",
                f"{pad}        name: {config.name}-{req.name}",
                f"{pad}        key: latest",
            ]
        )
    return lines


def _api_container(config: ProjectConfig, *, sidecar: bool) -> list[str]:
    port = config.backend_api_port
    lines = [
        "        - name: api",
        f"          image: {_image(config, 'api')}",
    ]
    if not sidecar:
        lines.extend(["          ports:", f"            - containerPort: {port}"])
    lines.extend(_secret_env(config, web=True, indent=10))
    if sidecar:
        # Cloud Run sets PORT for the ingress container; pin the sidecar's port.
        lines.extend(["            - name: APP_PORT", f"              value: '{port}'"])
    for key, value in tls_env(config).items():
        lines.extend([f"            - name: {key}", f"              value: '{value}'"])
    lines.extend(
        [
            "          resources:",
            "            limits:",
            "              cpu: '1'",
            "              memory: 512Mi",
            "          startupProbe:",
            *_probe(config, port),
            "            initialDelaySeconds: 10",
            "            periodSeconds: 10",
        ]
    )
    return lines


def _probe(config: ProjectConfig, port: int) -> list[str]:
    """HTTP startup probe on the health route.

    Django validates Host against ALLOWED_HOSTS, so its probe sends
    ``${PUBLIC_HOST}`` (rendered by envsubst; it must be in ALLOWED_HOSTS)
    and the edge's https scheme.
    """
    lines = [
        "            httpGet:",
        f"              path: {health_path(config)}",
        f"              port: {port}",
    ]
    if config.is_django_backend:
        lines.extend(
            [
                "              httpHeaders:",
                "                - name: Host",
                "                  value: ${PUBLIC_HOST}",
                "                - name: X-Forwarded-Proto",
                "                  value: https",
            ]
        )
    return lines


def _frontend_container(config: ProjectConfig) -> list[str]:
    port = FRONTEND_PORT if config.is_nextjs else 80
    lines = [
        "        - name: frontend",
        f"          image: {_image(config, 'frontend')}",
        "          ports:",
        f"            - containerPort: {port}",
    ]
    if not config.is_nextjs:
        # nginx renders API_UPSTREAM into its template at startup.
        upstream = f"http://localhost:{config.backend_api_port}"
        lines.extend(
            [
                "          env:",
                "            - name: API_UPSTREAM",
                f"              value: {upstream}",
                "            - name: API_PREFIX",
                f"              value: {api_prefix(config)}",
            ]
        )
    lines.extend(
        [
            "          resources:",
            "            limits:",
            "              cpu: '1'",
            "              memory: 256Mi",
        ]
    )
    return lines


def generate_cloud_run_yaml(config: ProjectConfig) -> str:
    """Generate service.yaml for ``gcloud run services replace``."""
    api = api_service(config)
    fullstack = config.has_frontend
    service_name = config.name if fullstack else api
    build = [
        f'#   docker build -f {BACKEND_DOCKERFILE} -t "{_image(config, "api")}" . && '
        f'docker push "{_image(config, "api")}"'
    ]
    annotations = ["        autoscaling.knative.dev/maxScale: '10'"]
    if fullstack:
        build_arg = (
            f" --build-arg INTERNAL_API_URL=http://localhost:{config.backend_api_port}"
            if config.is_nextjs
            else ""
        )
        frontend_image = _image(config, "frontend")
        build.append(
            f"#   docker build -f {FRONTEND_DOCKERFILE}{build_arg} "
            f'-t "{frontend_image}" . && docker push "{frontend_image}"'
        )
        dependencies = '{"frontend":["api"]}'
        annotations.append(f"        run.googleapis.com/container-dependencies: '{dependencies}'")
    containers = _frontend_container(config) if fullstack else []
    containers += _api_container(config, sidecar=fullstack)
    header = "\n".join(
        [
            "# Generated by mattstack.",
            "# Reference: https://cloud.google.com/run/docs/reference/yaml/v1",
            "# Build and push (authenticated):",
            *build,
            "# Store each secret (the service account needs roles/secretmanager.secretAccessor):",
            f"#   printf '%s' '<value>' | gcloud secrets create {config.name}-<NAME> --data-file=-",
            "# Deploy. Django probes send PUBLIC_HOST as Host, so it must be in ALLOWED_HOSTS.",
            "# The run.app host is deterministic, so it is known before the first deploy:",
            f'#   export PUBLIC_HOST={service_name}-$(gcloud projects describe "$PROJECT_ID" \\',
            "#     --format='value(projectNumber)').$REGION.run.app   # or your custom domain",
            '#   : "${PUBLIC_HOST:?set PUBLIC_HOST}" "${PROJECT_ID:?}" "${REGION:?}"',
            f"#   envsubst < service.yaml > /tmp/{api}.yaml && \\",
            f'#     gcloud run services replace /tmp/{api}.yaml --region "$REGION"',
            "# Migrate (Cloud Run job from the same image and secrets):",
            f"#   gcloud run jobs deploy {config.name}-migrate \\",
            f'#     --image "{_image(config, "api")}" \\',
            f'#     --region "$REGION" --args {MIGRATE_COMMAND.split()[-1]} \\',
            f"#     --set-secrets <NAME>={config.name}-<NAME>:latest,... --execute-now",
            "# For a Cloud SQL Unix socket, add the run.googleapis.com/cloudsql-instances",
            "# annotation and store DB_HOST as /cloudsql/<PROJECT>:<REGION>:<INSTANCE>.",
        ]
    )
    body = "\n".join(
        [
            "apiVersion: serving.knative.dev/v1",
            "kind: Service",
            "metadata:",
            f"  name: {service_name}",
            "spec:",
            "  template:",
            "    metadata:",
            "      annotations:",
            *annotations,
            "    spec:",
            "      containers:",
            *containers,
        ]
    )
    return f"{header}\n{body}\n"


def generate_worker_pool_yaml(config: ProjectConfig, process: TaskProcess) -> str:
    """Generate a Cloud Run worker pool for one task process."""
    name = f"{config.name}-{process.service}"
    args = "\n".join(f"            - {_yaml_str(arg)}" for arg in process.argv)
    env = "\n".join(_secret_env(config, web=False, indent=10))
    return f"""\
# Generated by mattstack. Reference: https://cloud.google.com/run/docs/deploy-worker-pools
# Deploy (authenticated; push the API image first, see service.yaml):
#   envsubst < workerpool-{process.service}.yaml > /tmp/{name}.yaml && \\
#     gcloud run worker-pools replace /tmp/{name}.yaml --region "$REGION"
# One instance: a {process.role} must not run twice.
apiVersion: run.googleapis.com/v1
kind: WorkerPool
metadata:
  name: {name}
  annotations:
    run.googleapis.com/manualInstanceCount: '1'
spec:
  template:
    spec:
      containers:
        - name: {process.service}
          image: {_image(config, "api")}
          args:
{args}
{env}
          resources:
            limits:
              cpu: '1'
              memory: 512Mi
"""


def _yaml_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
