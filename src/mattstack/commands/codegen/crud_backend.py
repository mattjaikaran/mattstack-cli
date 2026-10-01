"""Plan backend CRUD artifacts before any filesystem write."""

from __future__ import annotations

from mattstack.commands.codegen.api_tests import render_api_tests
from mattstack.commands.codegen.backend_layout import (
    DJANGO_MATT,
    BackendLayout,
    register_controller,
)
from mattstack.commands.codegen.django_api import render_ninja_controller
from mattstack.commands.codegen.django_matt_api import render_matt_controller
from mattstack.commands.codegen.django_models import (
    render_admin,
    render_model,
    render_schemas,
    schema_class_names,
)
from mattstack.commands.codegen.django_service import render_service
from mattstack.commands.codegen.fields import FieldSpec, to_snake
from mattstack.commands.codegen.package_exports import plan_exports
from mattstack.commands.codegen.plan import FilePlan
from mattstack.commands.codegen.py_lines import from_import
from mattstack.commands.codegen.resource_policy import (
    DEFAULT_POLICY,
    ResourcePolicy,
    api_fields,
)


def plan_backend(
    plan: FilePlan,
    layout: BackendLayout,
    name: str,
    fields: list[FieldSpec],
    *,
    with_tests: bool,
    policy: ResourcePolicy = DEFAULT_POLICY,
) -> None:
    """Add model, schemas, controller, service, admin, registration, and tests to *plan*.

    *layout* and *fields* come from `policy_context`, with key types resolved
    and *policy* verified against the project. The model gets every field;
    schemas, controller, service, and tests get the wire fields, so an owned
    resource's owner FK is never client-controlled.
    """
    snake = to_snake(name)
    wire = api_fields(fields, policy)

    plan.ensure_package(layout.models_dir)
    plan.create(layout.models_dir / f"{snake}.py", render_model(name, fields, layout, policy))
    plan_exports(plan, layout.models_dir / "__init__.py", f".{snake}", [name])

    plan.ensure_package(layout.schemas_dir)
    plan.create(layout.schemas_dir / f"{snake}.py", render_schemas(name, wire, layout))
    plan_exports(plan, layout.schemas_dir / "__init__.py", f".{snake}", schema_class_names(name))

    if policy.with_service:
        plan.ensure_package(layout.services_dir)
        plan.create(
            layout.services_dir / f"{snake}_service.py",
            render_service(name, wire, layout, policy),
        )
        plan_exports(
            plan, layout.services_dir / "__init__.py", f".{snake}_service", [f"{name}Service"]
        )

    controller_file = layout.controllers_dir / f"{snake}.py"
    render = render_matt_controller if layout.framework == DJANGO_MATT else render_ninja_controller
    plan.ensure_package(layout.controllers_dir)
    plan.create(controller_file, render(name, wire, layout, policy))
    plan_exports(plan, layout.controllers_dir / "__init__.py", f".{snake}", [f"{name}Controller"])

    admin_source = render_admin(name, fields, layout)
    if layout.admin_package:
        admin_dir = layout.app_dir / "admin"
        plan.ensure_package(admin_dir)
        plan.create(admin_dir / f"{snake}_admin.py", admin_source)
        plan_exports(plan, admin_dir / "__init__.py", f".{snake}_admin", [f"{name}Admin"])
    else:
        plan.create(layout.app_dir / f"{snake}_admin.py", admin_source)
        plan.append_import(
            layout.app_dir / "admin.py",
            f"from .{snake}_admin import {name}Admin  # noqa: E402, F401",
        )

    api_text = plan.updates.get(layout.api_file) or layout.api_file.read_text(encoding="utf-8")
    import_line = "\n".join(from_import(layout.module_of(controller_file), [f"{name}Controller"]))
    registered = register_controller(
        api_text, layout.api_var, import_line, f"{name}Controller", layout.first_party_packages
    )
    if registered != api_text:
        plan.update(layout.api_file, registered)

    if with_tests:
        tests_dir = layout.app_dir / "tests"
        plan.ensure_package(tests_dir)
        plan.create(
            tests_dir / f"test_{snake}_api.py", render_api_tests(name, wire, layout, policy)
        )
