"""`generate model` and `generate crud`: backend resources and their frontend client."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Annotated, NamedTuple

import typer

from mattstack.commands.codegen.api_tests import render_api_tests
from mattstack.commands.codegen.backend_layout import (
    BackendLayout,
    GenerateError,
    detect_backend_layout,
    register_controller,
)
from mattstack.commands.codegen.django_api import render_controller, resource_path
from mattstack.commands.codegen.django_models import (
    render_admin,
    render_model,
    render_schemas,
    schema_class_names,
)
from mattstack.commands.codegen.fields import (
    FK_KEY_TYPES,
    FieldSpec,
    FieldSpecError,
    parse_fields,
    to_pascal,
    to_snake,
    validate_model_name,
)
from mattstack.commands.codegen.model_pk import resolve_fields, with_model_key
from mattstack.commands.codegen.package_exports import plan_exports
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
)
from mattstack.commands.codegen.tanstack_routes import TANSTACK_NEXT_STEPS, plan_tanstack_route
from mattstack.parsers.frontend_layout import FrontendLayout, detect_frontend_layout
from mattstack.utils.console import console, print_error, print_info, print_success, print_warning

FieldsOption = Annotated[
    list[str] | None,
    typer.Option(
        "--fields",
        "-f",
        help="Fields as name:type or name:fk:Model. Repeat -f "
        'or quote a list: "title:str price:decimal"',
    ),
]
AppOption = Annotated[
    str | None, typer.Option("--app", "-a", help="Django app (default: auto-detect)")
]
PathOption = Annotated[Path | None, typer.Option("--path", "-p", help="Project root path")]
DryRunOption = Annotated[bool, typer.Option("--dry-run", help="Preview without creating files")]
ForceOption = Annotated[
    bool, typer.Option("--force", help="Overwrite generated files that already exist")
]
RouteGroupOption = Annotated[
    RouteGroup | None,
    typer.Option(
        "--route-group",
        help="React Router only: register under public routes (default) or the "
        "ProtectedRoute group (a client-side redirect, not authorization)",
    ),
]
NEXT_STEPS = "Next: mattstack db makemigrations && mattstack db migrate"


class ProjectDirs(NamedTuple):
    root: Path
    backend_dir: Path
    frontend_dir: Path
    api_env_var: str | None  # browser env var holding the API base URL


def resolve_dirs(path: Path | None) -> ProjectDirs:
    """Resolve the project at *path* (or an ancestor of it)."""
    from mattstack.project import resolve_project
    from mattstack.templates.frontend_runtime import api_base_env_var

    try:
        project = resolve_project((path or Path.cwd()).resolve())
    except ValueError as exc:
        raise GenerateError(str(exc)) from exc
    env_var = None
    if project.frontend_framework is not None:
        env_var = api_base_env_var(project.config)
    return ProjectDirs(project.root, project.backend_dir, project.frontend_dir, env_var)


def finish(plan: FilePlan, *, dry_run: bool, force: bool) -> None:
    """Refuse to overwrite existing files unless forced, then apply the plan."""
    conflicts = plan.conflicts()
    if conflicts and not force:
        listed = "\n".join(f"  {p.relative_to(plan.root)}" for p in conflicts)
        raise GenerateError(
            f"These files already exist; rerun with --force to overwrite:\n{listed}"
        )
    plan.apply(dry_run=dry_run)


def ui_segment(name: str) -> str:
    """Return the kebab-case URL segment for *name* (`ProductItem` -> `product-item`)."""
    return to_snake(name).replace("_", "-")


def route_group_for(layout: FrontendLayout, group: RouteGroup | None) -> RouteGroup:
    """Validate `--route-group` against the router; default to public routes."""
    if group is not None and layout.router != "react-router":
        raise GenerateError(f"--route-group applies to React Router, not {layout.router}.")
    return group or RouteGroup.public


def router_next_steps(layout: FrontendLayout, group: RouteGroup) -> list[str]:
    if layout.router == "tanstack":
        return [TANSTACK_NEXT_STEPS]
    if layout.router == "react-router" and group is RouteGroup.protected:
        return [PROTECTED_NOTICE]
    return []


def parse_model_spec(
    name: str, fields: list[str] | None, *, allow_empty: bool
) -> tuple[str, list[FieldSpec]]:
    pascal = to_pascal(name)
    validate_model_name(pascal)
    parsed = parse_fields(fields or [])
    if not parsed and not allow_empty:
        raise FieldSpecError(
            'No --fields given. Pass fields, e.g. --fields "title:str price:decimal", or --empty.'
        )
    return pascal, parsed


def backend_context(
    backend_dir: Path, app: str | None, fields: list[FieldSpec]
) -> tuple[BackendLayout, list[FieldSpec]]:
    """Inspect the backend and resolve generated and FK primary key types."""
    layout = with_model_key(detect_backend_layout(backend_dir, app))
    return layout, resolve_fields(layout, fields)


def plan_backend(
    plan: FilePlan, layout: BackendLayout, name: str, fields: list[FieldSpec], *, with_tests: bool
) -> None:
    """Add model, schemas, controller, admin, registration, and tests to *plan*.

    *layout* and *fields* come from `backend_context`, with key types resolved.
    """
    snake = to_snake(name)

    plan.ensure_package(layout.models_dir)
    plan.create(layout.models_dir / f"{snake}.py", render_model(name, fields, layout))
    plan_exports(plan, layout.models_dir / "__init__.py", f".{snake}", [name])

    plan.ensure_package(layout.schemas_dir)
    plan.create(layout.schemas_dir / f"{snake}.py", render_schemas(name, fields, layout))
    plan_exports(plan, layout.schemas_dir / "__init__.py", f".{snake}", schema_class_names(name))

    controller_file = layout.controllers_dir / f"{snake}.py"
    plan.ensure_package(layout.controllers_dir)
    plan.create(controller_file, render_controller(name, fields, layout))
    plan_exports(plan, layout.controllers_dir / "__init__.py", f".{snake}", [f"{name}Controller"])

    admin_source = render_admin(name, fields, layout)
    if layout.admin_package:
        admin_dir = layout.app_dir / "admin"
        plan.ensure_package(admin_dir)
        plan.create(admin_dir / f"{snake}_admin.py", admin_source)
        plan.append_import(admin_dir / "__init__.py", f"from .{snake}_admin import {name}Admin")
    else:
        plan.create(layout.app_dir / f"{snake}_admin.py", admin_source)
        plan.append_import(
            layout.app_dir / "admin.py",
            f"from .{snake}_admin import {name}Admin  # noqa: E402, F401",
        )

    api_text = plan.updates.get(layout.api_file) or layout.api_file.read_text(encoding="utf-8")
    import_line = f"from {layout.module_of(controller_file)} import {name}Controller"
    registered = register_controller(api_text, layout.api_var, import_line, f"{name}Controller")
    if registered != api_text:
        plan.update(layout.api_file, registered)

    if with_tests:
        tests_dir = layout.app_dir / "tests"
        plan.ensure_package(tests_dir)
        plan.create(tests_dir / f"test_{snake}_api.py", render_api_tests(name, fields, layout))


def plan_frontend(
    plan: FilePlan,
    dirs: ProjectDirs,
    name: str,
    fields: list[FieldSpec],
    backend: BackendLayout,
    *,
    with_tests: bool,
    route_group: RouteGroup | None = None,
    replace_existing: bool = False,
) -> tuple[list[str], list[str]]:
    """Add the API client, hooks, list component, route, and test.

    Return (warnings, router next steps). API paths stay snake_case like the
    backend prefix; UI routes use kebab-case segments.
    """
    frontend_dir = dirs.frontend_dir
    layout = detect_frontend_layout(frontend_dir, dirs.api_env_var)
    if backend.camel_schema_module is not None:  # CamelCaseSchema serializes camelCase keys
        layout = replace(layout, camel_case_keys=True)
    group = route_group_for(layout, route_group)
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
        page = layout.app_dir / ui_plural / "page.tsx"
        plan.create(page, render_list_page(name, layout.import_path(page, component_file), None))
    elif layout.router == "tanstack" and layout.routes_dir is not None:
        page = layout.routes_dir / ui_plural / "index.tsx"
        page_spec = layout.import_path(page, component_file)
        plan_tanstack_route(
            plan,
            layout.routes_dir,
            page,
            lambda route_id: render_list_page(name, page_spec, route_id),
        )
    elif layout.router == "react-router":
        page = (layout.pages_dir or src / "pages") / f"{name}sPage.tsx"
        content = render_list_page(name, layout.import_path(page, component_file), None)
        plan_react_router_page(
            plan,
            layout,
            page,
            content,
            f"/{ui_plural}",
            group,
            replace_existing=replace_existing,
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
    return warnings, router_next_steps(layout, group)


def model(
    name: Annotated[str, typer.Argument(help="Model name in PascalCase (e.g. Product)")],
    fields: FieldsOption = None,
    app: AppOption = None,
    path: PathOption = None,
    empty: Annotated[bool, typer.Option("--empty", help="Allow a model with no fields")] = False,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
) -> None:
    """Generate a model, schemas, registered controller, and admin."""
    start = time.monotonic()
    try:
        pascal, parsed = parse_model_spec(name, fields, allow_empty=empty)
        root, backend_dir = resolve_dirs(path)[:2]
        layout, parsed = backend_context(backend_dir, app, parsed)
        plan = FilePlan(root)
        plan_backend(plan, layout, pascal, parsed, with_tests=False)
        if dry_run:
            print_info(
                f"[dry-run] Model '{pascal}' in app '{layout.app_module}' ({layout.framework})"
            )
        finish(plan, dry_run=dry_run, force=force)
    except (GenerateError, FieldSpecError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    if not dry_run:
        print_success(
            f"Generated {pascal}; {pascal}Controller registered in {layout.api_file.name}"
        )
    console.print(NEXT_STEPS, markup=False)
    console.print(f"[dim]Completed in {time.monotonic() - start:.2f}s[/dim]")


def crud(
    name: Annotated[str, typer.Argument(help="Model name in PascalCase (e.g. Product)")],
    fields: FieldsOption = None,
    app: AppOption = None,
    path: PathOption = None,
    with_tests: Annotated[
        bool, typer.Option("--with-tests", help="Also generate pytest + Vitest tests")
    ] = False,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
    route_group: RouteGroupOption = None,
) -> None:
    """Scaffold a full-stack CRUD feature wired from model to list page."""
    start = time.monotonic()
    warnings: list[str] = []
    next_steps: list[str] = []
    try:
        pascal, parsed = parse_model_spec(name, fields, allow_empty=False)
        dirs = resolve_dirs(path)
        root = dirs.root
        layout, parsed = backend_context(dirs.backend_dir, app, parsed)
        plan = FilePlan(root)
        plan_backend(plan, layout, pascal, parsed, with_tests=with_tests)
        if (dirs.frontend_dir / "package.json").is_file():
            warnings, next_steps = plan_frontend(
                plan,
                dirs,
                pascal,
                parsed,
                layout,
                with_tests=with_tests,
                route_group=route_group,
                replace_existing=force,
            )
        elif route_group is not None:
            raise GenerateError(f"--route-group needs a frontend; none at {dirs.frontend_dir}.")
        else:
            warnings.append(f"No frontend at {dirs.frontend_dir}; generated the backend only.")
        if dry_run:
            print_info(f"[dry-run] CRUD feature '{pascal}' in app '{layout.app_module}'")
        finish(plan, dry_run=dry_run, force=force)
    except (GenerateError, FieldSpecError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    for warning in warnings:
        print_warning(warning)
    if not dry_run:
        print_success(
            f"Generated CRUD for {pascal}: {layout.mount_prefix}{resource_path(pascal)}/ "
            f"registered in {layout.api_file.relative_to(root)}"
        )
    console.print(NEXT_STEPS, markup=False)
    for step in next_steps:
        print_info(step)
    console.print(f"[dim]Completed in {time.monotonic() - start:.2f}s[/dim]")
