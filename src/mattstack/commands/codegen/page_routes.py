"""Plan pages in supported router declarations without partial writes."""

from __future__ import annotations

from pathlib import Path

from mattstack.commands.codegen.backend_layout import GenerateError
from mattstack.commands.codegen.crud_frontend import route_group_for, router_next_steps, ui_segment
from mattstack.commands.codegen.fields import to_pascal
from mattstack.commands.codegen.nextjs_pages import next_route_segments, plan_nextjs_page
from mattstack.commands.codegen.plan import FilePlan
from mattstack.commands.codegen.react_basic import render_default_page, render_tanstack_page
from mattstack.commands.codegen.react_router import (
    RouteGroup,
    plan_react_router_page,
    react_router_package,
)
from mattstack.commands.codegen.route_options import RouteOptions, check_route_options
from mattstack.commands.codegen.tanstack_routes import plan_tanstack_page
from mattstack.parsers.frontend_layout import FrontendLayout

_DEFAULT_OPTIONS = RouteOptions()


def _relative_directory(directory: Path | None, root: Path) -> list[str]:
    if directory is None:
        return []
    try:
        return list(directory.resolve().relative_to(root.resolve()).parts)
    except ValueError as exc:
        raise GenerateError(
            f"Page directory {directory} is outside the configured route root {root}. "
            "Set --path to a directory inside that root, or use --route."
        ) from exc


def plan_page(
    plan: FilePlan,
    layout: FrontendLayout,
    name: str,
    *,
    directory: Path | None = None,
    route: str | None = None,
    group: RouteGroup | None = None,
    replace_existing: bool = False,
    options: RouteOptions = _DEFAULT_OPTIONS,
) -> list[str]:
    """Return next steps after validating and planning one router-native page."""
    selected_group = route_group_for(layout, group)
    check_route_options(layout, options)
    segment, pascal = ui_segment(name), to_pascal(name)
    if route is not None and not route.startswith("/"):
        raise GenerateError(
            "--route must start with '/'; use a router-native path such as /reports."
        )
    if layout.router == "nextjs" and layout.app_dir is not None:
        prefix = _relative_directory(directory, layout.app_dir)
        segments = prefix + (next_route_segments(route) if route is not None else [segment])
        plan_nextjs_page(plan, layout, segments, render_default_page(pascal))
    elif layout.router == "tanstack":
        prefix = _relative_directory(directory, layout.routes_dir) if layout.routes_dir else []
        path = "/" + "/".join(prefix + [segment]) if route is None else route
        plan_tanstack_page(
            plan,
            layout,
            path,
            lambda target: render_tanstack_page(target, pascal, options),
            options=options,
        )
    elif layout.router == "react-router":
        pages_dir = directory or layout.pages_dir or layout.src_dir / "pages"
        plan_react_router_page(
            plan,
            layout,
            pages_dir / f"{pascal}Page.tsx",
            render_default_page(pascal, react_router_package(layout) if options.error else None),
            route or f"/{segment}",
            selected_group,
            replace_existing=replace_existing,
            options=options,
        )
    else:
        raise GenerateError(
            "Page generation supports TanStack Router, React Router, and Next.js; "
            f"this frontend uses {layout.router}. Configure a supported router before retrying."
        )
    return router_next_steps(layout, selected_group, options)
