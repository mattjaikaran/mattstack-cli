"""Render django-matt API controllers for `generate`."""

from __future__ import annotations

from mattstack.commands.codegen.backend_layout import BackendLayout
from mattstack.commands.codegen.django_api import (
    HANDLER_SCHEMAS,
    KEY_BITS,
    module_docstring,
    resource_path,
    service_call,
    service_init,
)
from mattstack.commands.codegen.django_ops import (
    Resource,
    list_rows,
    matt_create,
    matt_delete,
    matt_lookup,
    matt_update,
    model_import,
    relations,
    relations_helper,
    schema_imports,
    search_filter,
    service_module,
)
from mattstack.commands.codegen.fields import FieldSpec
from mattstack.commands.codegen.py_lines import bracketed, from_import
from mattstack.commands.codegen.resource_policy import DEFAULT_POLICY, ResourcePolicy


def _imports(res: Resource) -> list[str]:
    inline = not res.policy.with_service
    lines = list(KEY_BITS[res.layout.pk_key][3])
    if inline and res.policy.soft_delete:
        lines.append("from asgiref.sync import sync_to_async")
    if res.layout.has_jwt:
        lines.append("from django_matt.auth import jwt_required")
    lines += [
        "from django_matt.core import APIController",
        *(["from django_matt.core.errors import NotFoundAPIError"] if inline else []),
        "from django_matt.core.router import delete, get, post, put",
        "",
        *([model_import(res)] if inline else []),
        *schema_imports(res, HANDLER_SCHEMAS),
        *([] if inline else from_import(service_module(res), [f"{res.name}Service"])),
        *(relations_helper(res) if inline else []),
    ]
    return lines


def _lookup(res: Resource, op: str) -> list[str]:
    """Bind `obj` for get: inline query or the service's 404-raising getter."""
    if res.policy.with_service:
        method = f"get_{res.snake}"
        return service_call(res, op, method, f"{res.snake}_id", prefix="obj = await ")
    return matt_lookup(res, "request.user")


def _write(res: Resource, op: str, inline: list[str], *args: str) -> list[str]:
    """Statements of a write: inline ORM code or one awaited service call binding `obj`."""
    if not res.policy.with_service:
        return inline
    prefix = "await " if op == "delete" else "obj = await "
    return service_call(res, op, f"{op}_{res.snake}", *args, prefix=prefix)


def _def(method: str, *params: str, returns: str) -> list[str]:
    return bracketed("    ", f"async def {method}", ["self", "request", *params], f" -> {returns}:")


def render_matt_controller(
    name: str,
    fields: list[FieldSpec],
    layout: BackendLayout,
    policy: ResourcePolicy = DEFAULT_POLICY,
) -> str:
    """Render a django-matt APIController with the same contract as the Ninja one.

    Global resources guard writes with `@jwt_required` when the project has
    auth; owned resources guard every route, so anonymous requests get 401.
    """
    res = Resource(name, fields, layout, policy)
    snake, plural = res.snake, resource_path(name)
    write_guard = ["    @jwt_required"] if layout.has_jwt else []
    read_guard = write_guard if policy.owned else []
    key, conv = KEY_BITS[layout.pk_key][:2]
    user = "request.user"
    if policy.with_service:
        call = service_call(res, "list", f"list_{plural}", "search", prefix="queryset = ")
        rows = ['        search = request.GET.get("search")', *call]
    else:
        rows = [*list_rows(res, user), '        search = request.GET.get("search")']
        rows += search_filter(res)
    lines = [
        *module_docstring(f"API controller for {name}.", res, holds_list_query=False),
        *_imports(res),
        "",
        *([""] if not policy.with_service and relations(fields) else []),
        "MAX_PAGE_SIZE = 100",
        "",
        "",
        "def _positive_int(value: str | None, default: int) -> int:",
        "    try:",
        "        number = int(value) if value is not None else default",
        "    except ValueError:",
        "        return default",
        "    return number if number > 0 else default",
        "",
        "",
        f"class {name}Controller(APIController):",
        f'    prefix = "/{plural}"',
        f'    tags = ["{name}"]',
        "",
        *service_init(res),
        '    @get("/")',
        *read_guard,
        f"    async def list_{plural}(self, request) -> dict:",
        '        """List records as {"count", "results"}, newest first."""',
        '        page = _positive_int(request.GET.get("page"), 1)',
        '        page_size = min(_positive_int(request.GET.get("page_size"), 20), MAX_PAGE_SIZE)',
        *rows,
        "        start = (page - 1) * page_size",
        f"        schema = {name}ResponseSchema",
        "        results = [",
        '            schema.model_validate(item).model_dump(mode="json")',
        "            async for item in queryset[start : start + page_size]",
        "        ]",
        '        return {"count": await queryset.acount(), "results": results}',
        "",
        f'    @get("/<{conv}:{snake}_id>")',
        *read_guard,
        *_def(f"get_{snake}", f"{snake}_id: {key}", returns=f"{name}ResponseSchema"),
        f'        """Return one {name}."""',
        *_lookup(res, "get"),
        f"        return {name}ResponseSchema.model_validate(obj)",
        "",
        '    @post("/")',
        *write_guard,
        *_def(f"create_{snake}", f"body: {name}CreateSchema", returns=f"{name}ResponseSchema"),
        f'        """Create a {name}."""',
        *_write(res, "create", matt_create(res, user), "body"),
        f"        return {name}ResponseSchema.model_validate(obj)",
        "",
        f'    @put("/<{conv}:{snake}_id>")',
        *write_guard,
        *_def(
            f"update_{snake}",
            f"{snake}_id: {key}",
            f"body: {name}UpdateSchema",
            returns=f"{name}ResponseSchema",
        ),
        '        """Update the fields sent in the body."""',
        *_write(res, "update", matt_update(res, user), f"{snake}_id", "body"),
        f"        return {name}ResponseSchema.model_validate(obj)",
        "",
        f'    @delete("/<{conv}:{snake}_id>")',
        *write_guard,
        *_def(f"delete_{snake}", f"{snake}_id: {key}", returns="None"),
        f'        """Delete a {name}."""',
        *_write(res, "delete", matt_delete(res, user), f"{snake}_id"),
        "",
    ]
    return "\n".join(lines)
