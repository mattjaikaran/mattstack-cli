"""Generate command: scaffold models, endpoints, and frontend pieces into a project."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Annotated

import typer

from mattstack.commands.codegen.backend_layout import (
    GenerateError,
    detect_backend_layout,
    register_controller,
)
from mattstack.commands.codegen.django_api import (
    endpoint_function_name,
    endpoint_imports,
    render_endpoint_controller,
    render_endpoint_method,
)
from mattstack.commands.codegen.django_models import render_schemas, schema_class_names
from mattstack.commands.codegen.fields import FieldSpecError, to_pascal, to_snake
from mattstack.commands.codegen.package_exports import plan_exports
from mattstack.commands.codegen.plan import FilePlan
from mattstack.commands.codegen.react_basic import (
    render_component,
    render_component_test,
    render_default_page,
    render_hook,
    render_tanstack_page,
)
from mattstack.commands.codegen.react_router import plan_react_router_page
from mattstack.commands.codegen.tanstack_routes import plan_tanstack_route
from mattstack.commands.generate_crud import (
    AppOption,
    DryRunOption,
    FieldsOption,
    ForceOption,
    PathOption,
    RouteGroupOption,
    backend_context,
    crud,
    finish,
    model,
    parse_model_spec,
    resolve_dirs,
    route_group_for,
    router_next_steps,
    ui_segment,
)
from mattstack.parsers.frontend_layout import detect_frontend_layout
from mattstack.utils.console import console, print_error, print_info

generate_app = typer.Typer(
    name="generate",
    help="Scaffold models, endpoints, components, pages, hooks, and schemas.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
generate_app.command("model")(model)
generate_app.command("crud")(crud)

ProjectOption = Annotated[Path | None, typer.Option("--project", help="Project root path")]
SEGMENT_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
CONTROLLER_PREFIX_RE = re.compile(
    r"""^@api_controller\(\s*['"]([^'"]*)['"]|^\s+prefix\s*=\s*['"]([^'"]*)['"]""", re.MULTILINE
)


def _fail(exc: Exception) -> typer.Exit:
    print_error(str(exc))
    return typer.Exit(code=1)


def _done(start: float) -> None:
    console.print(f"[dim]Completed in {time.monotonic() - start:.2f}s[/dim]")


def _controller_prefix(text: str) -> str | None:
    found = CONTROLLER_PREFIX_RE.search(text)
    prefix = (found.group(1) or found.group(2)) if found else None
    return "/" + prefix.strip("/") if prefix is not None else None


def _controller_serving(controllers_dir: Path, prefix: str) -> Path | None:
    """Return the controller module whose prefix is *prefix*, if one exists."""
    if not controllers_dir.is_dir():
        return None
    for path in sorted(controllers_dir.glob("*.py")):
        if _controller_prefix(path.read_text(encoding="utf-8", errors="replace")) == prefix:
            return path
    return None


def _append_method(text: str, method_source: str, imports: list[str], func: str) -> str:
    """Append a method to the single controller class closing *text*."""
    if len(re.findall(r"^class\s+\w+", text, re.MULTILINE)) != 1:
        raise GenerateError("The controller file must hold exactly one class to append to.")
    if re.search(rf"^\s+(?:async\s+)?def\s+{func}\s*\(", text, re.MULTILINE):
        raise GenerateError(f"A method named {func} already exists in the controller.")
    lines = text.rstrip("\n").split("\n")
    missing = [
        line
        for line in imports
        if not re.search(rf"^(?:from|import)\s.*\b{line.rsplit(' ', 1)[-1]}\b", text, re.MULTILINE)
    ]
    last_import = max(
        (i for i, line in enumerate(lines) if line.startswith(("import ", "from "))), default=-1
    )
    lines[last_import + 1 : last_import + 1] = missing
    return "\n".join(lines) + "\n\n" + method_source


@generate_app.command("endpoint")
def endpoint(
    route_path: Annotated[
        str, typer.Argument(help="URL path under the API (e.g. /products/featured)")
    ],
    method: Annotated[
        str, typer.Option("--method", "-m", help="GET, POST, PUT, PATCH, DELETE")
    ] = "GET",
    auth: Annotated[bool, typer.Option("--auth", help="Require JWT authentication")] = False,
    app: AppOption = None,
    path: PathOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Add an endpoint stub (501 until implemented) to a registered controller."""
    start = time.monotonic()
    method = method.upper()
    try:
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            raise GenerateError(f"Invalid method '{method}'. Use GET, POST, PUT, PATCH, or DELETE.")
        segments = [s for s in route_path.strip("/").split("/") if s]
        if not segments or not SEGMENT_RE.match(segments[0]):
            raise GenerateError("The path needs a resource segment first, e.g. /products/featured.")
        root, backend_dir = resolve_dirs(path)[:2]
        layout = detect_backend_layout(backend_dir, app)
        if auth and not layout.has_jwt:
            raise GenerateError(
                "--auth needs django-ninja-jwt or django-matt[auth] in the backend."
            )
        prefix = f"/{segments[0]}"
        relative = "/" + "/".join(segments[1:]) if len(segments) > 1 else "/"
        module = segments[0].replace("-", "_")
        controller_file = _controller_serving(layout.controllers_dir, prefix) or (
            layout.controllers_dir / f"{module}.py"
        )
        imports = endpoint_imports(method, auth, layout)
        plan = FilePlan(root)
        if controller_file.exists():
            text = controller_file.read_text(encoding="utf-8")
            if _controller_prefix(text) != prefix:
                raise GenerateError(
                    f"{controller_file.name} does not serve {prefix}; cannot append."
                )
            relative = "/" + "/".join(segments[1:]) if len(segments) > 1 else "/"
            source = render_endpoint_method(method, relative, auth, layout)
            func = endpoint_function_name(method, relative)
            plan.update(controller_file, _append_method(text, source, imports, func))
        else:
            name = to_pascal(module)
            source = render_endpoint_method(method, relative, auth, layout)
            plan.ensure_package(layout.controllers_dir)
            plan.create(
                controller_file, render_endpoint_controller(name, prefix, source, imports, layout)
            )
            line = f"from {layout.module_of(controller_file)} import {name}Controller"
            api_text = layout.api_file.read_text(encoding="utf-8")
            plan.update(
                layout.api_file,
                register_controller(api_text, layout.api_var, line, f"{name}Controller"),
            )
        if dry_run:
            print_info(f"[dry-run] {method} {layout.mount_prefix}{route_path.strip('/')}")
            console.print(source, markup=False, highlight=False)
        finish(plan, dry_run=dry_run, force=False)
    except GenerateError as exc:
        raise _fail(exc) from exc
    _done(start)


def _frontend(project_path: Path | None) -> tuple[Path, Path]:
    dirs = resolve_dirs(project_path)
    root, frontend_dir = dirs.root, dirs.frontend_dir
    if not (frontend_dir / "package.json").is_file():
        raise GenerateError(f"No frontend package.json found at {frontend_dir}")
    return root, frontend_dir


@generate_app.command("component")
def component(
    name: Annotated[str, typer.Argument(help="Component name in PascalCase (e.g. ProductCard)")],
    comp_path: Annotated[
        str | None, typer.Option("--path", help="Directory relative to frontend/")
    ] = None,
    with_test: Annotated[
        bool, typer.Option("--with-test", help="Also create a Vitest test")
    ] = False,
    project_path: ProjectOption = None,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
) -> None:
    """Generate a React TypeScript component."""
    start = time.monotonic()
    pascal = to_pascal(name)
    try:
        root, frontend_dir = _frontend(project_path)
        layout = detect_frontend_layout(frontend_dir)
        base = frontend_dir / comp_path if comp_path else layout.src_dir / "components"
        plan = FilePlan(root)
        plan.create(base / pascal / "index.tsx", render_component(pascal))
        if with_test:
            if not layout.has_vitest:
                raise GenerateError("--with-test needs vitest and @testing-library/react.")
            plan.create(base / pascal / f"{pascal}.test.tsx", render_component_test(pascal))
        finish(plan, dry_run=dry_run, force=force)
    except GenerateError as exc:
        raise _fail(exc) from exc
    _done(start)


@generate_app.command("page")
def page(
    name: Annotated[str, typer.Argument(help="Page name (e.g. dashboard or user-settings)")],
    page_path: Annotated[
        str | None, typer.Option("--path", help="Directory relative to frontend/")
    ] = None,
    project_path: ProjectOption = None,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
    route_group: RouteGroupOption = None,
) -> None:
    """Generate a TanStack Router, React Router, or Next.js page at a kebab-case URL."""
    start = time.monotonic()
    segment, pascal = ui_segment(name), to_pascal(name)
    try:
        if not SEGMENT_RE.fullmatch(segment):
            raise GenerateError(f"Invalid page name {name!r}: use letters, digits, and dashes.")
        root, frontend_dir = _frontend(project_path)
        layout = detect_frontend_layout(frontend_dir)
        group = route_group_for(layout, route_group)
        base = frontend_dir / page_path if page_path else None
        plan = FilePlan(root)
        if layout.router == "nextjs" and layout.app_dir is not None:
            target = (base or layout.app_dir) / segment / "page.tsx"
            plan.create(target, render_default_page(pascal))
        elif layout.router == "tanstack" and layout.routes_dir is not None:
            plan_tanstack_route(
                plan,
                layout.routes_dir,
                (base or layout.routes_dir) / f"{segment}.tsx",
                lambda route_id: render_tanstack_page(route_id, pascal),
            )
        elif layout.router == "react-router":
            pages_dir = base or layout.pages_dir or layout.src_dir / "pages"
            plan_react_router_page(
                plan,
                layout,
                pages_dir / f"{pascal}Page.tsx",
                render_default_page(pascal),
                f"/{segment}",
                group,
                replace_existing=force,
            )
        else:
            raise GenerateError(
                "Page generation supports TanStack Router, React Router, and Next.js; "
                f"this frontend uses {layout.router}."
            )
        finish(plan, dry_run=dry_run, force=force)
    except GenerateError as exc:
        raise _fail(exc) from exc
    for step in router_next_steps(layout, group):
        print_info(step)
    _done(start)


@generate_app.command("hook")
def hook(
    name: Annotated[str, typer.Argument(help="Hook name (e.g. useProducts)")],
    hook_path: Annotated[
        str | None, typer.Option("--path", help="Directory relative to frontend/")
    ] = None,
    project_path: ProjectOption = None,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
) -> None:
    """Generate a React hook that runs an async function and tracks its state."""
    start = time.monotonic()
    hook_name = name if name.startswith("use") else f"use{to_pascal(name)}"
    try:
        root, frontend_dir = _frontend(project_path)
        base = (
            frontend_dir / hook_path
            if hook_path
            else detect_frontend_layout(frontend_dir).src_dir / "hooks"
        )
        plan = FilePlan(root)
        plan.create(base / f"{hook_name}.ts", render_hook(hook_name))
        finish(plan, dry_run=dry_run, force=force)
    except GenerateError as exc:
        raise _fail(exc) from exc
    _done(start)


@generate_app.command("schema")
def schema(
    name: Annotated[str, typer.Argument(help="Schema name in PascalCase (e.g. Product)")],
    fields: FieldsOption = None,
    app: AppOption = None,
    path: PathOption = None,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
) -> None:
    """Generate Base/Create/Update/Response schemas without a model."""
    start = time.monotonic()
    try:
        pascal, parsed = parse_model_spec(name, fields, allow_empty=True)
        root, backend_dir = resolve_dirs(path)[:2]
        layout, parsed = backend_context(backend_dir, app, parsed)
        plan = FilePlan(root)
        plan.ensure_package(layout.schemas_dir)
        snake = to_snake(pascal)
        plan.create(layout.schemas_dir / f"{snake}.py", render_schemas(pascal, parsed, layout))
        plan_exports(
            plan, layout.schemas_dir / "__init__.py", f".{snake}", schema_class_names(pascal)
        )
        finish(plan, dry_run=dry_run, force=force)
    except (GenerateError, FieldSpecError) as exc:
        raise _fail(exc) from exc
    _done(start)
