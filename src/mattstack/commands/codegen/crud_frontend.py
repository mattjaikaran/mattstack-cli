"""Plan frontend CRUD artifacts and router registration atomically."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from mattstack.commands.codegen.backend_layout import BackendLayout, GenerateError
from mattstack.commands.codegen.fields import FK_KEY_TYPES, FieldSpec, to_snake
from mattstack.commands.codegen.nextjs_pages import next_group_segments, plan_nextjs_page
from mattstack.commands.codegen.plan import FilePlan
from mattstack.commands.codegen.react_crud import (
    render_list_component,
    render_list_page,
    render_tanstack_hooks,
    render_ts_api_client,
    render_vitest,
)
from mattstack.commands.codegen.react_router import (
    PROTECTED_NOTICE,
    RouteGroup,
    plan_react_router_page,
    react_router_package,
)
from mattstack.commands.codegen.route_options import (
    DEFAULT_ROUTE_OPTIONS,
    GUARD_NOTICE,
    RouteOptions,
    check_route_options,
)
from mattstack.commands.codegen.tanstack_routes import (
    TANSTACK_NEXT_STEPS,
    TanStackTarget,
    plan_tanstack_page,
)
from mattstack.parsers.frontend_layout import FrontendLayout, detect_frontend_layout


def ui_segment(name: str) -> str:
    """Return the kebab-case URL segment for *name* (`ProductItem` -> `product-item`)."""
    return to_snake(name).replace("_", "-")


def route_group_for(layout: FrontendLayout, group: RouteGroup | None) -> RouteGroup:
    """Validate `--route-group` against the router; default to public routes."""
    if group is not None and layout.router != "react-router":
        raise GenerateError(f"--route-group applies to React Router, not {layout.router}.")
    return group or RouteGroup.public


def router_next_steps(
    layout: FrontendLayout, group: RouteGroup, options: RouteOptions = DEFAULT_ROUTE_OPTIONS
) -> list[str]:
    steps: list[str] = []
    if layout.router == "tanstack":
        steps.append(TANSTACK_NEXT_STEPS)
        if options.guard:
            steps.append(GUARD_NOTICE)
    if layout.router == "react-router" and group is RouteGroup.protected:
        steps.append(PROTECTED_NOTICE)
    return steps


def _app_group(layout: FrontendLayout, app_group: str | None) -> list[str]:
    """Validate `--app-group`; it only places Next.js App Router pages."""
    if app_group is None:
        return []
    if layout.router != "nextjs":
        raise GenerateError(f"--app-group places Next.js App Router pages, not {layout.router}.")
    return next_group_segments(app_group)


def plan_frontend(
    plan: FilePlan,
    frontend_dir: Path,
    name: str,
    fields: list[FieldSpec],
    backend: BackendLayout,
    *,
    api_env_var: str | None = None,
    with_tests: bool,
    route_group: RouteGroup | None = None,
    replace_existing: bool = False,
    options: RouteOptions = DEFAULT_ROUTE_OPTIONS,
    app_group: str | None = None,
) -> tuple[list[str], list[str]]:
    """Add the API client, hooks, list component, route, and test.

    Return (warnings, router next steps). API paths stay snake_case like the
    backend prefix; UI routes use kebab-case segments. Router flags and
    `app_group` are validated before anything is planned; route planners
    raise before their own `plan.create`, and nothing is written until the
    caller applies *plan*.
    """
    layout = detect_frontend_layout(frontend_dir, api_env_var)
    if backend.camel_schema_module is not None:  # CamelCaseSchema serializes camelCase keys
        layout = replace(layout, camel_case_keys=True)
    group = route_group_for(layout, route_group)
    check_route_options(layout, options, has_loader=True)
    groups = _app_group(layout, app_group)
    id_type = FK_KEY_TYPES[backend.pk_key][1]
    warnings: list[str] = []
    src, snake = layout.src_dir, to_snake(name)
    ui_plural = f"{ui_segment(name)}s"
    client_file = src / "api" / f"{snake}.ts"
    hooks_file = src / "hooks" / f"use{name}s.ts"
    component_file = src / "components" / f"{name}List" / "index.tsx"
    if "@tanstack/react-query" not in (frontend_dir / "package.json").read_text(encoding="utf-8"):
        raise GenerateError(
            "The frontend does not depend on @tanstack/react-query; CRUD hooks need it."
        )

    plan.create(
        client_file,
        render_ts_api_client(name, fields, layout, client_file, backend.mount_prefix, id_type),
    )
    hooks_spec_client = layout.import_path(hooks_file, client_file)
    plan.create(hooks_file, render_tanstack_hooks(name, hooks_spec_client, id_type))
    hooks_spec = layout.import_path(component_file, hooks_file)
    plan.create(
        component_file,
        render_list_component(
            name, fields, hooks_spec, layout.router == "nextjs", layout.camel_case_keys
        ),
    )

    if layout.router == "nextjs" and layout.app_dir is not None:
        segments = [*groups, ui_plural]
        page = layout.app_dir.joinpath(*segments, "page.tsx")
        content = render_list_page(name, layout.import_path(page, component_file))
        plan_nextjs_page(plan, layout, segments, content)
    elif layout.router == "tanstack":

        def render(target: TanStackTarget) -> str:
            return render_list_page(
                name,
                layout.import_path(target.file, component_file),
                target,
                options,
                hooks_spec=layout.import_path(target.file, hooks_file),
            )

        plan_tanstack_page(plan, layout, f"/{ui_plural}/", render, options)
    elif layout.router == "react-router":
        page = (layout.pages_dir or src / "pages") / f"{name}sPage.tsx"
        error_package = react_router_package(layout) if options.error else None
        content = render_list_page(
            name, layout.import_path(page, component_file), error_package=error_package
        )
        plan_react_router_page(
            plan,
            layout,
            page,
            content,
            f"/{ui_plural}",
            group,
            replace_existing=replace_existing,
            options=options,
        )
    else:
        warnings.append(
            f"No route generated: the frontend router is {layout.router}. "
            f"Render <{name}List /> from your own route."
        )

    if with_tests:
        if layout.has_vitest:
            test_file = component_file.parent / f"{name}List.test.tsx"
            plan.create(test_file, render_vitest(name, layout.import_path(test_file, hooks_file)))
        else:
            warnings.append(
                "No frontend test generated: vitest and @testing-library/react "
                "are not dependencies."
            )
    return warnings, router_next_steps(layout, group, options)
