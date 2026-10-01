"""Provider deployment configs follow the production runtime contract."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from mattstack.config import (
    BackendFramework,
    DeploymentTarget,
    FrontendFramework,
    ProjectConfig,
    ProjectType,
    TaskBackend,
)
from mattstack.templates.deploy_files import deployment_files, unsupported_deployment_reason
from mattstack.templates.deploy_runtime import health_path, required_env


class _ComposeLoader(yaml.SafeLoader):
    """Accept Compose's ``!reset`` tag."""


_ComposeLoader.add_constructor("!reset", lambda loader, node: None)


def _config(tmp_path: Path, target: DeploymentTarget, **kwargs: Any) -> ProjectConfig:
    return ProjectConfig(name="my-app", path=tmp_path / "my-app", deployment=target, **kwargs)


def _parse(path: str, content: str) -> Any:
    if path.endswith(".json"):
        return json.loads(content)
    if path.endswith((".yml", ".yaml")):
        return yaml.load(content, Loader=_ComposeLoader)  # noqa: S506 # SafeLoader subclass.
    if path.endswith(".toml"):
        return tomllib.loads(content)
    return content


def _files(tmp_path: Path, target: DeploymentTarget, **kwargs: Any) -> dict[str, str]:
    return deployment_files(_config(tmp_path, target, **kwargs))


_COMBOS = [
    (target, project_type, backend, frontend)
    for target in DeploymentTarget
    for project_type in ProjectType
    for backend in BackendFramework
    for frontend in (FrontendFramework.REACT_VITE, FrontendFramework.NEXTJS)
]


@pytest.mark.parametrize(("target", "project_type", "backend", "frontend"), _COMBOS)
def test_every_supported_combination_renders_parseable_safe_files(
    tmp_path: Path,
    target: DeploymentTarget,
    project_type: ProjectType,
    backend: BackendFramework,
    frontend: FrontendFramework,
) -> None:
    config = _config(
        tmp_path,
        target,
        project_type=project_type,
        backend_framework=backend,
        frontend_framework=frontend,
    )
    if unsupported_deployment_reason(config):
        with pytest.raises(ValueError, match="Choose"):
            deployment_files(config)
        return
    for path, content in deployment_files(config).items():
        _parse(path, content)
        # Legacy per-app Dockerfile paths no longer exist after consolidation.
        assert "backend/Dockerfile" not in content.replace("docker/backend/Dockerfile", "")
        assert "frontend/Dockerfile" not in content.replace("docker/frontend/Dockerfile", "")
        assert ":-postgres}" not in content
        assert "runserver" not in content


@pytest.mark.parametrize(
    ("target", "project_type", "frontend"),
    [
        (DeploymentTarget.CLOUDFLARE, ProjectType.BACKEND_ONLY, FrontendFramework.REACT_VITE),
        (DeploymentTarget.CLOUDFLARE, ProjectType.FULLSTACK, FrontendFramework.NEXTJS),
        (DeploymentTarget.RENDER, ProjectType.FULLSTACK, FrontendFramework.NEXTJS),
        (DeploymentTarget.AWS, ProjectType.FRONTEND_ONLY, FrontendFramework.REACT_VITE),
    ],
)
def test_unsupported_combinations_explain_alternatives(
    tmp_path: Path, target: DeploymentTarget, project_type: ProjectType, frontend: FrontendFramework
) -> None:
    config = _config(tmp_path, target, project_type=project_type, frontend_framework=frontend)
    reason = unsupported_deployment_reason(config)
    assert reason is not None and "Choose" in reason


def test_frontend_framework_does_not_affect_backend_only_support(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        DeploymentTarget.RENDER,
        project_type=ProjectType.BACKEND_ONLY,
        frontend_framework=FrontendFramework.NEXTJS,
    )
    assert unsupported_deployment_reason(config) is None


@pytest.mark.parametrize(
    ("backend", "path"),
    [
        (BackendFramework.DJANGO_NINJA, "/api/health/"),
        (BackendFramework.DJANGO_MATT, "/api/health"),
        (BackendFramework.FASTAPI, "/api/health/live"),
        (BackendFramework.NESTJS, "/api/v1/health"),
    ],
)
def test_health_path_matches_each_backend_route(
    tmp_path: Path, backend: BackendFramework, path: str
) -> None:
    config = _config(tmp_path, DeploymentTarget.FLY_IO, backend_framework=backend)
    assert health_path(config) == path


def test_render_maps_discrete_database_properties_and_independent_secrets(tmp_path: Path) -> None:
    files = _files(tmp_path, DeploymentTarget.RENDER, task_backend=TaskBackend.HUEY)
    spec = _parse("render.yaml", files["render.yaml"])
    services = {s["name"]: s for s in spec["services"]}
    api = services["my-app-api"]
    env = {e["key"]: e for e in api["envVars"]}
    assert "DATABASE_URL" not in env
    assert env["DB_HOST"]["fromDatabase"]["property"] == "host"
    assert env["DB_PASSWORD"]["fromDatabase"]["property"] == "password"
    for key in ("SECRET_KEY", "NINJA_JWT_SIGNING_KEY", "CENTRIFUGO_TOKEN_SECRET"):
        assert env[key]["generateValue"] is True
    assert env["ALLOWED_HOSTS"]["sync"] is False
    assert api["preDeployCommand"] == "app-entrypoint migrate"
    worker = services["my-app-huey-worker"]
    assert worker["dockerCommand"] == "app-entrypoint python manage.py run_huey"
    worker_env = {e["key"]: e for e in worker["envVars"]}
    assert worker_env["SECRET_KEY"]["fromService"]["envVarKey"] == "SECRET_KEY"
    assert "ALLOWED_HOSTS" not in worker_env


def test_render_static_frontend_rewrites_backend_paths_before_the_spa(tmp_path: Path) -> None:
    spec = _parse("render.yaml", _files(tmp_path, DeploymentTarget.RENDER)["render.yaml"])
    frontend = next(s for s in spec["services"] if s["name"] == "my-app-frontend")
    env = {e["key"]: e["value"] for e in frontend["envVars"]}
    assert env["VITE_API_BASE_URL"] == "/api"
    sources = [route["source"] for route in frontend["routes"]]
    assert sources == ["/api/*", "/admin/*", "/static/*", "/media/*", "/*"]


def test_digitalocean_static_frontend_fronts_a_private_api(tmp_path: Path) -> None:
    spec = _parse(".do/app.yaml", _files(tmp_path, DeploymentTarget.DIGITAL_OCEAN)[".do/app.yaml"])
    services = {s["name"]: s for s in spec["services"]}
    api, frontend = services["api"], services["frontend"]
    assert "routes" not in api and api["internal_ports"] == [8000]
    # Django rejects the probe Host, so App Platform falls back to a TCP check.
    assert "http_path" not in api["health_check"]
    env = {e["key"]: e["value"] for e in api["envs"]}
    assert env["DB_HOST"] == "${db.HOSTNAME}"
    assert "SECRET_KEY" not in env  # app-level secrets reach every component
    assert all("type" not in e for e in api["envs"])  # bindables must stay interpolated
    upstream = {e["key"]: e["value"] for e in frontend["envs"]}["API_UPSTREAM"]
    assert upstream == "${api.PRIVATE_URL}"
    app_envs = {e["key"]: e for e in spec["envs"]}
    assert app_envs["SECRET_KEY"]["type"] == "SECRET" and "value" not in app_envs["SECRET_KEY"]
    assert spec["jobs"][0]["kind"] == "PRE_DEPLOY"


def test_digitalocean_routes_backend_paths_in_front_of_nextjs(tmp_path: Path) -> None:
    files = _files(
        tmp_path, DeploymentTarget.DIGITAL_OCEAN, frontend_framework=FrontendFramework.NEXTJS
    )
    api = _parse(".do/app.yaml", files[".do/app.yaml"])["services"][0]
    assert {"path": "/static", "preserve_path_prefix": True} in api["routes"]


def test_railway_uses_infrastructure_as_code_with_pg_references(tmp_path: Path) -> None:
    files = _files(tmp_path, DeploymentTarget.RAILWAY)
    assert set(files) == {".railway/railway.ts", ".railway/package.json"}
    source = files[".railway/railway.ts"]
    assert 'dockerfilePath: "docker/backend/Dockerfile"' in source
    assert "DB_HOST: db.env.PGHOST," in source
    assert "NINJA_JWT_SIGNING_KEY: preserve()," in source
    assert "SECRET_KEY: api.env.SECRET_KEY," in source  # workers share the API value
    assert 'start: "app-entrypoint celery -A api worker' in source
    assert json.loads(files[".railway/package.json"])["devDependencies"]["railway"]


def test_railway_without_redis_declares_no_cache(tmp_path: Path) -> None:
    source = _files(
        tmp_path,
        DeploymentTarget.RAILWAY,
        backend_framework=BackendFramework.DJANGO_MATT,
        use_redis=False,
        task_backend=TaskBackend.NONE,
    )[".railway/railway.ts"]
    assert "redis(" not in source and "cache" not in source


def test_fly_fullstack_reaches_a_private_backend_over_flycast(tmp_path: Path) -> None:
    files = _files(tmp_path, DeploymentTarget.FLY_IO, task_backend=TaskBackend.DRAMATIQ)
    backend = _parse("fly.toml", files["fly.toml"])
    assert backend["deploy"]["release_command"] == "app-entrypoint migrate"
    assert backend["processes"]["worker"].startswith("app-entrypoint dramatiq ")
    assert backend["http_service"]["force_https"] is False  # Flycast is HTTP-only
    check = backend["http_service"]["checks"][0]
    # Django validates Host; the route is exempt from the TLS redirect.
    assert check["headers"] == {"Host": "my-app.fly.dev", "X-Forwarded-Proto": "https"}
    assert backend["env"] == {"USE_TLS": "true"}
    frontend = _parse("fly.frontend.toml", files["fly.frontend.toml"])
    assert frontend["app"] == "my-app-frontend"
    assert frontend["env"]["API_UPSTREAM"] == "http://my-app.flycast"


def test_aws_reads_every_requirement_from_ssm(tmp_path: Path) -> None:
    config = _config(tmp_path, DeploymentTarget.AWS)
    files = deployment_files(config)
    task = _parse("t.json", files["ecs-task-definition.json"])
    containers = {c["name"]: c for c in task["containerDefinitions"]}
    api, frontend = containers["my-app-api"], containers["my-app-frontend"]
    # The load balancer may be HTTP-only, so TLS mode stays an operator opt-in.
    assert "environment" not in api
    assert api["healthCheck"]["command"] == ["CMD", "app-entrypoint", "health"]
    assert [s["name"] for s in api["secrets"]] == [req.name for req in required_env(config)]
    assert {"name": "API_UPSTREAM", "value": "http://localhost:8000"} in frontend["environment"]
    assert frontend["dependsOn"] == [{"containerName": "my-app-api", "condition": "HEALTHY"}]
    worker_def = _parse("t.json", files["ecs-celery-worker-task-definition.json"])
    worker = worker_def["containerDefinitions"][0]
    assert worker["command"][:3] == ["celery", "-A", "api"]
    assert "ALLOWED_HOSTS" not in [s["name"] for s in worker["secrets"]]
    manifest = _parse("m.yml", files["copilot/my-app-api/manifest.yml"])
    assert manifest["type"] == "Backend Service"
    assert manifest["image"]["healthcheck"]["command"] == ["CMD", "app-entrypoint", "health"]
    assert manifest["image"]["build"]["dockerfile"] == "docker/backend/Dockerfile"


def test_gcp_runs_frontend_ingress_api_sidecar_and_worker_pools(tmp_path: Path) -> None:
    config = _config(tmp_path, DeploymentTarget.GCP)
    files = deployment_files(config)
    assert set(files) == {
        "service.yaml",
        "workerpool-celery-worker.yaml",
        "workerpool-celery-beat.yaml",
    }
    service = _parse("service.yaml", files["service.yaml"])
    frontend, api = service["spec"]["template"]["spec"]["containers"]
    assert frontend["name"] == "frontend" and frontend["ports"] == [{"containerPort": 80}]
    assert "ports" not in api
    probe = api["startupProbe"]["httpGet"]
    assert probe["path"] == "/api/health/"
    assert {"name": "Host", "value": "${PUBLIC_HOST}"} in probe["httpHeaders"]
    assert {"name": "USE_TLS", "value": "true"} in api["env"]
    secret_env = [e for e in api["env"] if "valueFrom" in e]
    refs = {e["name"]: e["valueFrom"]["secretKeyRef"]["name"] for e in secret_env}
    assert set(refs) == {req.name for req in required_env(config)}
    pool = _parse("w.yaml", files["workerpool-celery-beat.yaml"])
    assert pool["kind"] == "WorkerPool"
    assert pool["metadata"]["annotations"]["run.googleapis.com/manualInstanceCount"] == "1"
    container = pool["spec"]["template"]["spec"]["containers"][0]
    assert "command" not in container  # args keep the image entrypoint
    assert container["args"][:3] == ["celery", "-A", "api"]


@pytest.mark.parametrize(
    ("target", "override", "proxy"),
    [
        (DeploymentTarget.HETZNER, "docker-compose.caddy.yml", "caddy"),
        (DeploymentTarget.SELF_HOSTED, "docker-compose.nginx.yml", "nginx"),
    ],
)
def test_host_targets_extend_the_production_compose(
    tmp_path: Path, target: DeploymentTarget, override: str, proxy: str
) -> None:
    files = _files(tmp_path, target)
    assert "docker-compose.prod.yml" not in files
    services = _parse(override, files[override])["services"]
    # Only the !reset override, plus the edge's TLS mode for Ninja.
    assert services["api"] == {"ports": None, "environment": {"USE_TLS": "true"}}
    assert services[proxy]["environment"]["DOMAIN"] == "${DOMAIN:?Set DOMAIN in .env.production}"


def test_caddy_routes_backend_paths_only_in_front_of_nextjs(tmp_path: Path) -> None:
    static = _files(tmp_path, DeploymentTarget.HETZNER)["Caddyfile"]
    assert static == "{$DOMAIN} {\n    reverse_proxy frontend:80\n}\n"
    nextjs = _files(
        tmp_path, DeploymentTarget.HETZNER, frontend_framework=FrontendFramework.NEXTJS
    )["Caddyfile"]
    assert "@backend path /api /api/* /admin /admin/* /static /static/*" in nextjs
    assert "reverse_proxy frontend:3000" in nextjs


def test_cloudflare_pages_calls_an_https_backend(tmp_path: Path) -> None:
    files = _files(tmp_path, DeploymentTarget.CLOUDFLARE)
    data = tomllib.loads(files["wrangler.toml"])
    assert data["pages_build_output_dir"] == "frontend/dist"
    assert "VITE_API_BASE_URL=https://<api-domain>/api bun run build" in files["wrangler.toml"]
    assert files["Caddyfile"] == "{$DOMAIN} {\n    reverse_proxy api:8000\n}\n"
    caddy = _parse("c.yml", files["docker-compose.caddy.yml"])["services"]["caddy"]
    assert caddy["depends_on"] == ["api"]
