"""Inventory of provider-specific files for every deployment target.

The generators write ``deployment_files(config)`` after the root files. Each
provider's files reference only paths the generator emits
(``docker/backend/Dockerfile``, ``docker/frontend/Dockerfile``) and start the
backend through the image entrypoint. ``unsupported_deployment_reason``
names the combinations that have no working template, so ``init`` can refuse
them before it clones anything.
"""

from __future__ import annotations

from mattstack.config import DeploymentTarget, ProjectConfig
from mattstack.templates.deploy_runtime import FRONTEND_DOCKERFILE

_FRONTEND_ONLY_TARGETS = (
    DeploymentTarget.DOCKER,
    DeploymentTarget.FLY_IO,
    DeploymentTarget.CLOUDFLARE,
    DeploymentTarget.RENDER,
    DeploymentTarget.DIGITAL_OCEAN,
)


def unsupported_deployment_reason(config: ProjectConfig) -> str | None:
    """Return why ``config.deployment`` cannot deploy this stack, or ``None``."""
    target = config.deployment.value
    if not config.has_frontend and config.deployment == DeploymentTarget.CLOUDFLARE:
        return (
            f"Deployment target '{target}' hosts static frontends only; it cannot run the "
            f"{config.backend_framework.value} backend container. Choose docker, fly-io, "
            "render, railway, digital-ocean, aws, gcp, hetzner, or self-hosted."
        )
    if config.is_nextjs and config.deployment == DeploymentTarget.CLOUDFLARE:
        return (
            "Next.js on Cloudflare needs the OpenNext adapter, which mattstack does not "
            "generate. Choose a react-* frontend or the fly-io, render, or digital-ocean target."
        )
    if config.is_nextjs and config.is_fullstack and config.deployment == DeploymentTarget.RENDER:
        return (
            "Next.js bakes its API rewrite target at build time, and a Render Blueprint "
            "cannot pass the API service URL to the Docker build. Choose digital-ocean, "
            "docker, hetzner, or self-hosted, or a react-* frontend on render."
        )
    if not config.has_backend and config.deployment not in _FRONTEND_ONLY_TARGETS:
        supported = ", ".join(t.value for t in _FRONTEND_ONLY_TARGETS)
        return (
            f"Deployment target '{target}' has no frontend-only template. "
            f"Choose one of: {supported}."
        )
    return None


def deployment_files(config: ProjectConfig) -> dict[str, str]:
    """Return ``{relative path: content}`` for the configured deployment target."""
    reason = unsupported_deployment_reason(config)
    if reason:
        raise ValueError(reason)
    target = config.deployment
    if target == DeploymentTarget.RAILWAY:
        from mattstack.templates.deploy_railway import railway_files

        return railway_files(config)
    if target == DeploymentTarget.RENDER:
        from mattstack.templates.deploy_render import generate_render_yaml

        return {"render.yaml": generate_render_yaml(config), **_frontend_only_image(config)}
    if target == DeploymentTarget.FLY_IO:
        from mattstack.templates.deploy_fly import fly_files

        return {**fly_files(config), **_frontend_only_image(config)}
    if target == DeploymentTarget.AWS:
        from mattstack.templates.deploy_aws import aws_files

        return aws_files(config)
    if target == DeploymentTarget.GCP:
        from mattstack.templates.deploy_gcp import gcp_files

        return gcp_files(config)
    if target == DeploymentTarget.HETZNER:
        from mattstack.templates.deploy_hetzner import generate_caddy_compose, generate_caddyfile

        return {
            "docker-compose.caddy.yml": generate_caddy_compose(config),
            "Caddyfile": generate_caddyfile(config),
        }
    if target == DeploymentTarget.SELF_HOSTED:
        from mattstack.templates.deploy_self_hosted import (
            generate_nginx_compose,
            generate_nginx_conf,
            generate_systemd_service,
        )

        return {
            "docker-compose.nginx.yml": generate_nginx_compose(config),
            "nginx.conf.template": generate_nginx_conf(config),
            f"{config.name}.service": generate_systemd_service(config),
        }
    if target == DeploymentTarget.CLOUDFLARE:
        from mattstack.templates.deploy_cloudflare import cloudflare_files

        return cloudflare_files(config)
    if target == DeploymentTarget.DIGITAL_OCEAN:
        from mattstack.templates.deploy_digitalocean import generate_do_app_spec

        return {".do/app.yaml": generate_do_app_spec(config), **_frontend_only_image(config)}
    return {}


def _frontend_only_image(config: ProjectConfig) -> dict[str, str]:
    """Frontend-only projects get no root Docker files; container targets need them."""
    if config.has_backend:
        return {}
    if config.deployment != DeploymentTarget.FLY_IO and not config.is_nextjs:
        return {}  # Render and App Platform build static sites without a container.
    from mattstack.templates.dockerfiles import (
        generate_frontend_dockerfile,
        generate_frontend_nginx_conf,
    )

    # BaseGenerator.write_project_configuration already writes .dockerignore.
    files = {FRONTEND_DOCKERFILE: generate_frontend_dockerfile(config)}
    if not config.is_nextjs:
        files["docker/frontend/nginx.conf"] = generate_frontend_nginx_conf(config)
    return files
