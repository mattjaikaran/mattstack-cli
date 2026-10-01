"""`generate model` and `generate crud`: backend resources and their frontend client."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated, NamedTuple

import typer

from mattstack.commands.codegen.backend_layout import BackendLayout, GenerateError
from mattstack.commands.codegen.crud_backend import plan_backend
from mattstack.commands.codegen.crud_frontend import plan_frontend
from mattstack.commands.codegen.django_api import resource_path
from mattstack.commands.codegen.fields import (
    FieldSpec,
    FieldSpecError,
    parse_fields,
    to_pascal,
    to_snake,
    validate_model_name,
)
from mattstack.commands.codegen.plan import FilePlan
from mattstack.commands.codegen.react_router import RouteGroup
from mattstack.commands.codegen.resource_policy import (
    Lifecycle,
    ResourcePolicy,
    Scope,
    api_fields,
    policy_context,
)
from mattstack.commands.codegen.route_options import RouteOptions
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
ScopeOption = Annotated[
    Scope,
    typer.Option(
        "--scope",
        help="global: public reads, writes follow configured JWT; owned: authenticated ownership",
    ),
]
OwnerFieldOption = Annotated[
    str | None,
    typer.Option("--owner-field", help="Required for owned scope: a name:fk:User field"),
]
LifecycleOption = Annotated[
    Lifecycle,
    typer.Option("--lifecycle", help="Use the base, timestamped, or soft-delete model tier"),
]
ServiceOption = Annotated[
    bool, typer.Option("--with-service", help="Generate and export the resource service layer")
]
GuardOption = Annotated[
    bool, typer.Option("--guard", help="TanStack: require client auth, not backend authorization")
]
PendingOption = Annotated[
    bool, typer.Option("--pending", help="TanStack: generate the pending/loading component")
]
ErrorOption = Annotated[
    bool, typer.Option("--error", help="Generate a TanStack or React Router data error component")
]
LazyOption = Annotated[
    bool, typer.Option("--lazy", help="React Router data routes: load the page module lazily")
]
AppGroupOption = Annotated[
    str | None, typer.Option("--app-group", help="Next.js: place the CRUD page in a route group")
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


def report_policy(layout: BackendLayout, policy: ResourcePolicy) -> None:
    """Report effective access and lifecycle decisions, including unsafe prerequisites."""
    if policy.scope is Scope.OWNED:
        print_info(
            f"Policy: owned by {policy.owner_field}; every route requires JWT; "
            "cross-user access returns 404."
        )
    elif layout.has_jwt:
        print_info("Policy: global public reads; JWT-authenticated callers can change any row.")
    else:
        print_warning(
            "Policy: global public reads AND writes because this backend has no JWT provider. "
            "Install an auth provider and use --scope owned --owner-field <user-fk> "
            "before exposing private resources."
        )
    print_info(f"Lifecycle: {policy.lifecycle.value}; service layer: {policy.with_service}.")


def _report_public_review(layout: BackendLayout, policy: ResourcePolicy, name: str) -> None:
    """Keep deliberate public reads subject to the backend's security review."""
    contract = layout.backend_dir / "core/tests/test_route_auth.py"
    if policy.scope is not Scope.GLOBAL or not contract.is_file():
        return
    path = f"{layout.mount_prefix}{resource_path(name)}"
    print_warning(
        f"Security review required: global reads expose GET {path}/ and "
        f"GET {path}/{{{to_snake(name)}_id}} anonymously. Confirm this policy, then "
        "add only these GET operations to PUBLIC_OPERATIONS in "
        "backend/core/tests/test_route_auth.py. The generator does not waive this gate. "
        "For private data, use --scope owned --owner-field <user-fk>. "
        "Verify: cd backend && just gauntlet-quick."
    )


def model(
    name: Annotated[str, typer.Argument(help="Model name in PascalCase (e.g. Product)")],
    fields: FieldsOption = None,
    app: AppOption = None,
    path: PathOption = None,
    empty: Annotated[bool, typer.Option("--empty", help="Allow a model with no fields")] = False,
    dry_run: DryRunOption = False,
    force: ForceOption = False,
    scope: ScopeOption = Scope.GLOBAL,
    owner_field: OwnerFieldOption = None,
    lifecycle: LifecycleOption = Lifecycle.BASE,
    with_service: ServiceOption = False,
) -> None:
    """Generate a model, schemas, registered controller, and admin."""
    start = time.monotonic()
    try:
        pascal, parsed = parse_model_spec(name, fields, allow_empty=empty)
        root, backend_dir = resolve_dirs(path)[:2]
        policy = ResourcePolicy(scope, lifecycle, owner_field, with_service)
        layout, parsed = policy_context(backend_dir, app, parsed, policy)
        plan = FilePlan(root)
        plan_backend(plan, layout, pascal, parsed, with_tests=False, policy=policy)
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
    report_policy(layout, policy)
    _report_public_review(layout, policy, pascal)
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
    scope: ScopeOption = Scope.GLOBAL,
    owner_field: OwnerFieldOption = None,
    lifecycle: LifecycleOption = Lifecycle.BASE,
    with_service: ServiceOption = False,
    guard: GuardOption = False,
    pending: PendingOption = False,
    error: ErrorOption = False,
    lazy: LazyOption = False,
    app_group: AppGroupOption = None,
) -> None:
    """Scaffold a full-stack CRUD feature wired from model to list page."""
    start = time.monotonic()
    warnings: list[str] = []
    next_steps: list[str] = []
    try:
        pascal, parsed = parse_model_spec(name, fields, allow_empty=False)
        dirs = resolve_dirs(path)
        root = dirs.root
        policy = ResourcePolicy(scope, lifecycle, owner_field, with_service)
        layout, parsed = policy_context(dirs.backend_dir, app, parsed, policy)
        plan = FilePlan(root)
        plan_backend(plan, layout, pascal, parsed, with_tests=with_tests, policy=policy)
        if (dirs.frontend_dir / "package.json").is_file():
            warnings, next_steps = plan_frontend(
                plan,
                dirs.frontend_dir,
                pascal,
                api_fields(parsed, policy),
                layout,
                with_tests=with_tests,
                api_env_var=dirs.api_env_var,
                route_group=route_group,
                replace_existing=force,
                options=RouteOptions(guard, pending, error, lazy),
                app_group=app_group,
            )
        elif route_group is not None or app_group is not None or any((guard, pending, error, lazy)):
            raise GenerateError(f"Routing options need a frontend; none at {dirs.frontend_dir}.")
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
    report_policy(layout, policy)
    _report_public_review(layout, policy, pascal)
    console.print(NEXT_STEPS, markup=False)
    for step in next_steps:
        print_info(step)
    console.print(f"[dim]Completed in {time.monotonic() - start:.2f}s[/dim]")
