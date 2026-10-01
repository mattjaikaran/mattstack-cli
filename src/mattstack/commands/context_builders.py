"""Context builders: collect project stack, models, routes, and types for AI agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mattstack.config import BackendFramework
from mattstack.parsers.frontend_layout import FrontendLayout, detect_frontend_layout
from mattstack.parsers.frontend_routes import find_ui_routes
from mattstack.project import ResolvedProject, resolve_project
from mattstack.utils.package_manager import detect_package_manager
from mattstack.utils.process import command_available, get_command_version

# ── detection helpers ────────────────────────────────────────────────────────


def _has_backend(project: ResolvedProject) -> bool:
    return project.backend_framework is not None or any(
        (project.backend_dir / name).is_file() for name in ("pyproject.toml", "manage.py")
    )


def _detect_components(project: ResolvedProject) -> dict[str, bool]:
    root = project.root
    return {
        "backend": _has_backend(project),
        "frontend": (project.frontend_dir / "package.json").is_file(),
        "ios": (root / "ios").is_dir() and any((root / "ios").glob("*.xcodeproj")),
        "docker": any((root / name).is_file() for name in ("docker-compose.yml", "compose.yml")),
        "makefile": (root / "Makefile").exists(),
        "claude_md": (root / "CLAUDE.md").exists(),
    }


def _detect_backend_stack(project: ResolvedProject) -> dict[str, Any]:
    framework = project.backend_framework
    info: dict[str, Any]
    if framework == BackendFramework.NESTJS:
        pm = detect_package_manager(project.backend_dir)
        info = {"language": "typescript", "package_manager": pm.value}
    else:
        info = {"language": "python", "package_manager": "uv"}
    info["framework"] = framework.value if framework else None
    if project.config.use_celery:
        info["task_queue"] = "celery"
    if project.settings_module:
        info["settings_module"] = project.settings_module
    info["api_prefix"] = project.api_prefix
    info["port"] = project.api_port
    return info


_ROUTER_NAMES = {"tanstack": "tanstack-router", "react-router": "react-router", "nextjs": "nextjs"}


def _relative(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _detect_frontend_stack(project: ResolvedProject, layout: FrontendLayout) -> dict[str, Any]:
    pkg_json = project.frontend_dir / "package.json"
    if not pkg_json.is_file():
        return {}
    try:
        pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    root = project.root.resolve()
    pm = detect_package_manager(project.frontend_dir)
    framework = project.frontend_framework
    info: dict[str, Any] = {
        "language": "typescript",
        "package_manager": pm.value,
        "framework": framework.value if framework else None,
    }
    if layout.bundler != "unknown":
        info["bundler"] = layout.bundler
    if "react" in deps:
        info["ui_library"] = "react"
    if layout.router in _ROUTER_NAMES:
        info["router"] = _ROUTER_NAMES[layout.router]
    route_source = layout.routes_dir or layout.app_entry or layout.app_dir
    if route_source is not None:
        info["route_source"] = _relative(route_source, root)
    if layout.pages_dir is not None:
        info["pages_dir"] = _relative(layout.pages_dir, root)
    if "tailwindcss" in deps or "@tailwindcss/vite" in deps:
        info["styling"] = "tailwind"
    info["port"] = project.frontend_port
    scripts = pkg.get("scripts", {})
    if scripts:
        info["scripts"] = list(scripts.keys())
    return info


def _ui_routes(project: ResolvedProject, layout: FrontendLayout) -> list[dict[str, Any]]:
    """Client-side routes the frontend renders; never server endpoints or auth."""
    root = project.root.resolve()
    return [
        {
            "router": _ROUTER_NAMES[route.router],
            "path": route.path,
            "kind": route.kind,
            "file": _relative(route.file, root),
            "route_id": route.route_id,
            "element": route.element,
            "layouts": list(route.layouts),
        }
        for route in find_ui_routes(layout)
    ]


def detect_env_vars(path: Path) -> list[str]:
    """Return variable names (never values) from ``.env.example``."""
    env_example = path / ".env.example"
    if not env_example.exists():
        return []
    names = []
    for line in env_example.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            names.append(line.split("=", 1)[0].strip())
    return names


def detect_makefile_targets(path: Path) -> list[str]:
    makefile = path / "Makefile"
    if not makefile.exists():
        return []
    targets = []
    for line in makefile.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("\t") and not line.startswith("#") and ":" in line:
            target = line.split(":")[0].strip()
            if target and not target.startswith("."):
                targets.append(target)
    return targets


def _tool_versions() -> dict[str, str]:
    tools = ["git", "uv", "bun", "node", "python", "docker", "make"]
    versions: dict[str, str] = {}
    for tool in tools:
        if command_available(tool):
            ver = get_command_version(tool)
            versions[tool] = ver.split("\n")[0] if ver else "installed"
    return versions


# ── stack context ─────────────────────────────────────────────────────────────


def build_stack_context(path: Path) -> dict[str, Any]:
    project = resolve_project(path)
    root = project.root
    components = _detect_components(project)
    ctx: dict[str, Any] = {
        "project_name": root.name,
        "project_path": str(root),
        "components": components,
        "execution_mode": project.execution_mode,
    }
    if components["backend"]:
        ctx["backend"] = _detect_backend_stack(project)
    if components["frontend"]:
        layout = detect_frontend_layout(project.frontend_dir)
        ctx["frontend"] = _detect_frontend_stack(project, layout)
        ctx["ui_routes"] = _ui_routes(project, layout)
    env_vars = detect_env_vars(root)
    if env_vars:
        ctx["env_vars"] = env_vars
    targets = detect_makefile_targets(root)
    if targets:
        ctx["makefile_targets"] = targets
    ctx["tools"] = _tool_versions()
    return ctx


# ── models context ────────────────────────────────────────────────────────────


def build_models_context(path: Path) -> dict[str, Any]:
    from mattstack.parsers.django_models import find_model_files, parse_models_file

    model_files = find_model_files(path)
    models_out = []
    for mf in model_files:
        try:
            for m in parse_models_file(mf):
                fields_out = [{"name": f.name, "type": f.field_type, **f.kwargs} for f in m.fields]
                models_out.append(
                    {
                        "name": m.name,
                        "app": m.app,
                        "file": str(mf.relative_to(path)),
                        "inherits": m.inherits,
                        "fields": fields_out,
                    }
                )
        except OSError:
            pass
    return {"models": models_out}


# ── routes context ────────────────────────────────────────────────────────────


def build_routes_context(path: Path) -> dict[str, Any]:
    from mattstack.parsers.django_routes import find_controller_files, parse_controller_file

    controller_files = find_controller_files(path)
    routes_out = []
    for cf in controller_files:
        try:
            for c in parse_controller_file(cf):
                endpoints = [
                    {
                        "method": ep.method,
                        "path": ep.path,
                        "handler": ep.handler,
                        "response": ep.response,
                        "auth": ep.auth,
                    }
                    for ep in c.endpoints
                ]
                routes_out.append(
                    {
                        "controller": c.name,
                        "prefix": c.prefix,
                        "tag": c.tag,
                        "file": str(cf.relative_to(path)),
                        "endpoints": endpoints,
                    }
                )
        except OSError:
            pass
    return {"routes": routes_out}


# ── types context ─────────────────────────────────────────────────────────────


def build_types_context(path: Path) -> dict[str, Any]:
    from mattstack.parsers.typescript_types import find_typescript_type_files, parse_typescript_file
    from mattstack.parsers.zod_schemas import find_zod_files, parse_zod_file

    ts_files = find_typescript_type_files(path)
    interfaces_out = []
    for tf in ts_files:
        try:
            for iface in parse_typescript_file(tf):
                fields_out = [
                    {"name": f.name, "type": f.type_str, "optional": f.optional}
                    for f in iface.fields
                ]
                interfaces_out.append(
                    {
                        "name": iface.name,
                        "file": str(tf.relative_to(path)),
                        "extends": iface.extends,
                        "fields": fields_out,
                    }
                )
        except OSError:
            pass

    zod_files = find_zod_files(path)
    zod_out = []
    for zf in zod_files:
        try:
            for schema in parse_zod_file(zf):
                fields_out = [
                    {"name": f.name, "type": f.type_str, "optional": f.optional}
                    for f in schema.fields
                ]
                zod_out.append(
                    {
                        "name": schema.name,
                        "file": str(zf.relative_to(path)),
                        "fields": fields_out,
                    }
                )
        except OSError:
            pass

    return {"interfaces": interfaces_out, "zod_schemas": zod_out}


# ── full context ──────────────────────────────────────────────────────────────


def build_full_context(path: Path) -> dict[str, Any]:
    ctx = build_stack_context(path)
    ctx.update(build_models_context(path))
    ctx.update(build_routes_context(path))
    ctx.update(build_types_context(path))
    return ctx
