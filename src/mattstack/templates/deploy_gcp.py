"""GCP deployment config templates."""

from __future__ import annotations

from mattstack.config import ProjectConfig


def generate_cloud_run_yaml(config: ProjectConfig) -> str:
    """Generate Cloud Run service YAML."""
    lines: list[str] = [
        "apiVersion: serving.knative.dev/v1",
        "kind: Service",
        "metadata:",
        f"  name: {config.name}-api",
        "spec:",
        "  template:",
        "    metadata:",
        "      annotations:",
        "        autoscaling.knative.dev/minScale: '0'",
        "        autoscaling.knative.dev/maxScale: '10'",
        "    spec:",
        "      containers:",
        f"        - image: gcr.io/PROJECT_ID/{config.name}-api",
        "          ports:",
        "            - containerPort: 8000",
        "          env:",
        "            - name: DJANGO_SETTINGS_MODULE",
        f'              value: "{config.wsgi_app}.settings"',
        "            - name: PYTHONUNBUFFERED",
        '              value: "1"',
        "          resources:",
        "            limits:",
        "              cpu: '1'",
        "              memory: 512Mi",
        "          startupProbe:",
        "            httpGet:",
        "              path: /api/health/",
        "              port: 8000",
        "            initialDelaySeconds: 10",
        "            periodSeconds: 10",
    ]
    return "\n".join(lines) + "\n"


def generate_app_engine_yaml(config: ProjectConfig) -> str:
    """Generate App Engine app.yaml."""
    lines: list[str] = [
        "runtime: python312",
        f"entrypoint: gunicorn {config.wsgi_app}.wsgi:application --bind :$PORT",
        "",
        "env_variables:",
        f"  DJANGO_SETTINGS_MODULE: '{config.wsgi_app}.settings'",
        "  PYTHONUNBUFFERED: '1'",
        "",
        "automatic_scaling:",
        "  min_instances: 0",
        "  max_instances: 10",
        "  target_cpu_utilization: 0.65",
        "",
        "handlers:",
        "  - url: /static",
        "    static_dir: staticfiles",
        "  - url: /.*",
        "    script: auto",
        "    secure: always",
    ]
    return "\n".join(lines) + "\n"
