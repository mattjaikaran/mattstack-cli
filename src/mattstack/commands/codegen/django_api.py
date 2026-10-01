"""Render Django Ninja API controllers and endpoint stubs for `generate`."""

from __future__ import annotations

import re

from mattstack.commands.codegen.backend_layout import DJANGO_MATT, BackendLayout
from mattstack.commands.codegen.django_ops import (
    BODY,
    Resource,
    list_rows,
    model_import,
    ninja_create,
    ninja_delete,
    ninja_lookup,
    ninja_update,
    relations_helper,
    schema_imports,
    search_filter,
    service_module,
)
from mattstack.commands.codegen.fields import FieldSpec, to_snake
from mattstack.commands.codegen.py_lines import bracketed, from_import
from mattstack.commands.codegen.resource_policy import (
    DEFAULT_POLICY,
    ResourcePolicy,
    policy_doc,
)

# Key type -> (annotation, django-matt path converter, an id no row has, import).
KEY_BITS: dict[str, tuple[str, str, str, list[str]]] = {
    "uuid": ("UUID", "uuid", "00000000-0000-0000-0000-000000000000", ["from uuid import UUID", ""]),
    "int": ("int", "int", "2147483647", []),
    "str": ("str", "str", "missing-id", []),
}
HANDLER_SCHEMAS = ["CreateSchema", "ResponseSchema", "UpdateSchema"]


def resource_path(name: str) -> str:
    """Collection path segment shared by the backend prefix and frontend client."""
    return f"{to_snake(name)}s"


def module_docstring(title: str, res: Resource, *, holds_list_query: bool) -> list[str]:
    """Module docstring stating the resource policy the code below enforces."""
    waives = holds_list_query and res.waives_gate
    doc = policy_doc(res.name, res.layout, res.policy, waives_gate=waives)
    return [f'"""{title}', "", *doc, '"""', ""]


def service_init(res: Resource) -> list[str]:
    """Controller `__init__` holding the service, as in the boilerplate's TodoController."""
    if not res.policy.with_service:
        return []
    parent = ["        super().__init__()"] if res.is_async else []
    return [
        "    def __init__(self) -> None:",
        *parent,
        f"        self.service = {res.name}Service()",
        "",
    ]


def service_call(res: Resource, op: str, method: str, *args: str, prefix: str = "") -> list[str]:
    """`<prefix>self.service.<method>(...)`, passing the request user when *op* uses it."""
    user = ["request.user"] if res.uses_user(op) else []
    params = [*user, *args] if op == "list" else [*args, *user]
    return bracketed(BODY, f"{prefix}self.service.{method}", params)


def _handler(res: Resource, op: str, method: str, *params: str) -> list[str]:
    """Handler `def`; `request` comes first when the operation reads the user."""
    request = ["request"] if res.uses_user(op) else []
    return bracketed("    ", f"def {method}", ["self", *request, *params], ":")


def _route(verb: str, path: str, response: str, *options: str) -> list[str]:
    return bracketed("    ", f"@http_{verb}", [f'"{path}"', f"response={response}", *options])


def render_ninja_controller(
    name: str,
    fields: list[FieldSpec],
    layout: BackendLayout,
    policy: ResourcePolicy = DEFAULT_POLICY,
) -> str:
    """Render a ninja-extra controller enforcing *policy* over a paginated CRUD API.

    *fields* are wire fields (`api_fields`). ORM kwargs come from validated
    field attributes, not `model_dump()`: a CamelCaseSchema dumps by alias,
    and `unitPrice=` is no model field. With CamelCaseSchema, routes
    serialize by alias, because Ninja dumps the response through its own
    wrapper model and never calls the schema's `model_dump` override. An owned
    resource authenticates the whole controller, so anonymous requests get 401.
    """
    res = Resource(name, fields, layout, policy)
    snake, plural = res.snake, resource_path(name)
    key = KEY_BITS[layout.pk_key][0]
    owned, service = policy.owned, policy.with_service
    route_auth = ["auth=JWTAuth()"] if layout.has_jwt and not owned else []
    class_auth = ["auth=JWTAuth()"] if owned else []
    alias = ["by_alias=True"] if layout.camel_schema_module else []
    user = "request.user"
    item = f"/{{{snake}_id}}"
    lines = [
        *module_docstring(f"API controller for {name}.", res, holds_list_query=not service),
        # No `from __future__ import annotations`: Ninja and django-matt read
        # handler annotations at runtime, and string annotations break them.
        *KEY_BITS[layout.pk_key][3],
        *([] if service else ["from django.shortcuts import get_object_or_404"]),
        "from ninja_extra import api_controller, http_delete, http_get, http_post, http_put",
        "from ninja_extra.pagination import PageNumberPaginationExtra, paginate",
        "from ninja_extra.schemas import PaginatedResponseSchema",
        *(["from ninja_jwt.authentication import JWTAuth"] if layout.has_jwt else []),
        "",
        *([] if service else [model_import(res)]),
        *schema_imports(res, HANDLER_SCHEMAS),
        *(from_import(service_module(res), [f"{name}Service"]) if service else []),
        *([] if service else relations_helper(res)),
        "",
        "",
        *bracketed("", "@api_controller", [f'"/{plural}"', f'tags=["{name}"]', *class_auth]),
        f"class {name}Controller:",
        *service_init(res),
        *_route("get", "/", f"PaginatedResponseSchema[{name}ResponseSchema]", *alias),
        "    @paginate(PageNumberPaginationExtra, page_size=20)",
        *_handler(res, "list", f"list_{plural}", "search: str | None = None"),
        f'        """List {name} records, newest first."""',
        *(
            service_call(res, "list", f"list_{plural}", "search", prefix="return ")
            if service
            else [*list_rows(res, user), *search_filter(res), f"{BODY}return queryset"]
        ),
        "",
        *_route("get", item, f"{name}ResponseSchema", *alias),
        *_handler(res, "get", f"get_{snake}", f"{snake}_id: {key}"),
        f'        """Return one {name}."""',
        *(
            service_call(res, "get", f"get_{snake}", f"{snake}_id", prefix="return ")
            if service
            else ninja_lookup(res, user, "return ")
        ),
        "",
        *_route("post", "/", f"{{201: {name}ResponseSchema}}", *alias, *route_auth),
        *_handler(res, "create", f"create_{snake}", f"payload: {name}CreateSchema"),
        f'        """Create a {name}."""',
        *(
            service_call(res, "create", f"create_{snake}", "payload", prefix="return 201, ")
            if service
            else ninja_create(res, user, ret="return 201, ")
        ),
        "",
        *_route("put", item, f"{name}ResponseSchema", *alias, *route_auth),
        *_handler(
            res, "update", f"update_{snake}", f"{snake}_id: {key}", f"payload: {name}UpdateSchema"
        ),
        '        """Update the fields sent in the payload."""',
        *(
            service_call(
                res, "update", f"update_{snake}", f"{snake}_id", "payload", prefix="return "
            )
            if service
            else ninja_update(res, user)
        ),
        "",
        *_route("delete", item, "{204: None}", *route_auth),
        *_handler(res, "delete", f"delete_{snake}", f"{snake}_id: {key}"),
        f'        """Delete a {name}."""',
        *(
            service_call(res, "delete", f"delete_{snake}", f"{snake}_id")
            if service
            else ninja_delete(res, user)
        ),
        "        return 204, None",
        "",
    ]
    return "\n".join(lines)


def endpoint_function_name(method: str, relative_path: str) -> str:
    stem = re.sub(r"[{}<>]|\w+:", "", relative_path).strip("/")
    stem = re.sub(r"\W+", "_", stem).strip("_")
    return f"{method.lower()}_{stem}" if stem else f"{method.lower()}_root"


def endpoint_imports(method: str, auth: bool, layout: BackendLayout) -> list[str]:
    """Import lines one endpoint method needs, one imported name per line."""
    verb = method.lower()
    if layout.framework == DJANGO_MATT:
        lines = [
            "from django.http import JsonResponse",
            f"from django_matt.core.router import {verb}",
        ]
        return lines + (["from django_matt.auth import jwt_required"] if auth else [])
    lines = [f"from ninja_extra import http_{verb}"]
    return lines + (["from ninja_jwt.authentication import JWTAuth"] if auth else [])


def render_endpoint_method(
    method: str, relative_path: str, auth: bool, layout: BackendLayout
) -> str:
    """Render one controller method stub that answers 501 until implemented."""
    func = endpoint_function_name(method, relative_path)
    params = re.findall(r"[{<](?:\w+:)?(\w+)[}>]", relative_path)
    detail = f"{method} {relative_path} is not implemented."
    if layout.framework == DJANGO_MATT:
        path = re.sub(r"\{(\w+)\}", r"<str:\1>", relative_path)
        sig = ", ".join(["self", "request", *(f"{p}: str" for p in params)])
        lines = [f'    @{method.lower()}("{path}")']
        if auth:
            lines.append("    @jwt_required")
        lines += [
            f"    async def {func}({sig}) -> JsonResponse:",
            f'        """Handle {method} {relative_path}."""',
            f'        return JsonResponse({{"detail": "{detail}"}}, status=501)',
        ]
    else:
        path = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", relative_path)
        auth_arg = ", auth=JWTAuth()" if auth else ""
        sig = ", ".join(["self", *(f"{p}: str" for p in params)])
        lines = [
            f'    @http_{method.lower()}("{path}", response={{501: dict}}{auth_arg})',
            f"    def {func}({sig}):",
            f'        """Handle {method} {relative_path}."""',
            f'        return 501, {{"detail": "{detail}"}}',
        ]
    return "\n".join(lines) + "\n"


def render_endpoint_controller(
    name: str, prefix: str, method_source: str, imports: list[str], layout: BackendLayout
) -> str:
    """Render a new controller file holding one endpoint method."""
    if layout.framework == DJANGO_MATT:
        imports = [*imports, "from django_matt.core import APIController"]
        header = [
            f"class {name}Controller(APIController):",
            f'    prefix = "{prefix}"',
            f'    tags = ["{name}"]',
            "",
        ]
    else:
        imports = [*imports, "from ninja_extra import api_controller"]
        header = [f'@api_controller("{prefix}", tags=["{name}"])', f"class {name}Controller:"]
    return "\n".join(
        [
            f'"""API controller for {prefix}."""',
            "",
            *sorted(imports),
            "",
            "",
            *header,
            method_source,
        ]
    )
