"""Render Django API controllers and their tests for `generate`."""

from __future__ import annotations

import re

from mattstack.commands.codegen.backend_layout import DJANGO_MATT, BackendLayout
from mattstack.commands.codegen.fields import FieldSpec, search_field, to_snake

# Key type -> (annotation, django-matt path converter, an id no row has, import).
KEY_BITS: dict[str, tuple[str, str, str, list[str]]] = {
    "uuid": ("UUID", "uuid", "00000000-0000-0000-0000-000000000000", ["from uuid import UUID", ""]),
    "int": ("int", "int", "2147483647", []),
    "str": ("str", "str", "missing-id", []),
}


def resource_path(name: str) -> str:
    """Collection path segment shared by the backend prefix and frontend client."""
    return f"{to_snake(name)}s"


def _schema_imports(name: str, layout: BackendLayout) -> list[str]:
    return [
        f"from {layout.app_module}.models.{to_snake(name)} import {name}",
        f"from {layout.app_module}.schemas.{to_snake(name)} import (",
        f"    {name}CreateSchema,",
        f"    {name}ResponseSchema,",
        f"    {name}UpdateSchema,",
        ")",
    ]


def _search(fields: list[FieldSpec], queryset: str, indent: str) -> list[str]:
    field = search_field(fields)
    if not field:
        return []
    return [
        f"{indent}if search:",
        f"{indent}    {queryset} = {queryset}.filter({field}__icontains=search)",
    ]


def _relations(fields: list[FieldSpec]) -> list[str]:
    return [f.name for f in fields if f.is_fk]


def _relations_helper(name: str, fields: list[FieldSpec], *, is_async: bool) -> list[str]:
    """Module-level check that every referenced row exists.

    A missing related row is a 404 for the client, not an IntegrityError (500)
    from the database. The related model comes from the FK at runtime, so a
    swapped user model or lazy reference needs no import here.
    """
    relations = _relations(fields)
    if not relations:
        return []
    head = "async def" if is_async else "def"
    lines = [
        "",
        f"RELATIONS = ({', '.join(repr(r) for r in relations)},)",
        "",
        "",
        f"{head} _require_relations(data: dict[str, object]) -> None:",
        '    """Answer 404 for a referenced row that does not exist."""',
        "    for relation in RELATIONS:",
        '        key = f"{relation}_id"',
        "        if key not in data:",
        "            continue",
        f"        related = {name}._meta.get_field(relation).related_model",
    ]
    if is_async:
        lines += [
            "        if not await related._default_manager.filter(pk=data[key]).aexists():",
            '            raise NotFoundAPIError(f"{relation} {data[key]} not found.")',
        ]
    else:
        lines.append("        get_object_or_404(related, pk=data[key])")
    return lines


def render_ninja_controller(name: str, fields: list[FieldSpec], layout: BackendLayout) -> str:
    """Render a ninja-extra controller with paginated list and JWT-protected writes."""
    snake, plural = to_snake(name), resource_path(name)
    auth = ", auth=JWTAuth()" if layout.has_jwt else ""
    lines = [
        f'"""API controller for {name}."""',
        "",
        # No `from __future__ import annotations`: Ninja and django-matt read
        # handler annotations at runtime, and string annotations break them.
        *KEY_BITS[layout.pk_key][3],
        "from django.shortcuts import get_object_or_404",
        "from ninja_extra import api_controller, http_delete, http_get, http_post, http_put",
        "from ninja_extra.pagination import PageNumberPaginationExtra, paginate",
        "from ninja_extra.schemas import PaginatedResponseSchema",
    ]
    if layout.has_jwt:
        lines.append("from ninja_jwt.authentication import JWTAuth")
    lines += [
        "",
        *_schema_imports(name, layout),
        *_relations_helper(name, fields, is_async=False),
        "",
        "",
        f'@api_controller("/{plural}", tags=["{name}"])',
        f"class {name}Controller:",
        f'    @http_get("/", response=PaginatedResponseSchema[{name}ResponseSchema])',
        "    @paginate(PageNumberPaginationExtra, page_size=20)",
        f"    def list_{plural}(self, search: str | None = None):",
        f'        """List {name} records, newest first."""',
        f"        queryset = {name}.objects.all()",
        *_search(fields, "queryset", "        "),
        "        return queryset",
        "",
        f'    @http_get("/{{{snake}_id}}", response={name}ResponseSchema)',
        f"    def get_{snake}(self, {snake}_id: {KEY_BITS[layout.pk_key][0]}):",
        f'        """Return one {name}."""',
        f"        return get_object_or_404({name}, id={snake}_id)",
        "",
        f'    @http_post("/", response={{201: {name}ResponseSchema}}{auth})',
        f"    def create_{snake}(self, payload: {name}CreateSchema):",
        f'        """Create a {name}."""',
        "        data = payload.model_dump()",
        *(["        _require_relations(data)"] if _relations(fields) else []),
        f"        return 201, {name}.objects.create(**data)",
        "",
        f'    @http_put("/{{{snake}_id}}", response={name}ResponseSchema{auth})',
        f"    def update_{snake}(",
        f"        self, {snake}_id: {KEY_BITS[layout.pk_key][0]}, payload: {name}UpdateSchema",
        "    ):",
        '        """Update the fields sent in the payload."""',
        f"        obj = get_object_or_404({name}, id={snake}_id)",
        "        data = payload.model_dump(exclude_unset=True)",
        *(["        _require_relations(data)"] if _relations(fields) else []),
        "        for attr, value in data.items():",
        "            setattr(obj, attr, value)",
        "        obj.save()",
        "        return obj",
        "",
        f'    @http_delete("/{{{snake}_id}}", response={{204: None}}{auth})',
        f"    def delete_{snake}(self, {snake}_id: {KEY_BITS[layout.pk_key][0]}):",
        f'        """Delete a {name}."""',
        f"        get_object_or_404({name}, id={snake}_id).delete()",
        "        return 204, None",
        "",
    ]
    return "\n".join(lines)


def render_matt_controller(name: str, fields: list[FieldSpec], layout: BackendLayout) -> str:
    """Render a django-matt APIController with the same contract as the Ninja one."""
    snake, plural = to_snake(name), resource_path(name)
    guard = ["    @jwt_required"] if layout.has_jwt else []
    key, conv = KEY_BITS[layout.pk_key][:2]
    lines = [
        f'"""API controller for {name}."""',
        "",
        *KEY_BITS[layout.pk_key][3],
    ]
    if layout.has_jwt:
        lines.append("from django_matt.auth import jwt_required")
    lines += [
        "from django_matt.core import APIController",
        "from django_matt.core.errors import NotFoundAPIError",
        "from django_matt.core.router import delete, get, post, put",
        "",
        *_schema_imports(name, layout),
        *_relations_helper(name, fields, is_async=True),
        "",
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
        '    @get("/")',
        f"    async def list_{plural}(self, request) -> dict:",
        '        """List records as {"count", "results"}, newest first."""',
        '        page = _positive_int(request.GET.get("page"), 1)',
        '        page_size = min(_positive_int(request.GET.get("page_size"), 20), MAX_PAGE_SIZE)',
        f"        queryset = {name}.objects.all()",
        '        search = request.GET.get("search")',
        *_search(fields, "queryset", "        "),
        "        start = (page - 1) * page_size",
        "        results = [",
        f'            {name}ResponseSchema.model_validate(item).model_dump(mode="json")',
        "            async for item in queryset[start : start + page_size]",
        "        ]",
        '        return {"count": await queryset.acount(), "results": results}',
        "",
        f'    @get("/<{conv}:{snake}_id>")',
        f"    async def get_{snake}(self, request, {snake}_id: {key}) -> {name}ResponseSchema:",
        f'        """Return one {name}."""',
        f"        obj = await {name}.objects.filter(id={snake}_id).afirst()",
        "        if obj is None:",
        f'            raise NotFoundAPIError("{name} not found.")',
        f"        return {name}ResponseSchema.model_validate(obj)",
        "",
        '    @post("/")',
        *guard,
        f"    async def create_{snake}(self, request, body: {name}CreateSchema)"
        f" -> {name}ResponseSchema:",
        f'        """Create a {name}."""',
        "        data = body.model_dump()",
        *(["        await _require_relations(data)"] if _relations(fields) else []),
        f"        obj = await {name}.objects.acreate(**data)",
        f"        return {name}ResponseSchema.model_validate(obj)",
        "",
        f'    @put("/<{conv}:{snake}_id>")',
        *guard,
        f"    async def update_{snake}(",
        f"        self, request, {snake}_id: {key}, body: {name}UpdateSchema",
        f"    ) -> {name}ResponseSchema:",
        '        """Update the fields sent in the body."""',
        f"        obj = await {name}.objects.filter(id={snake}_id).afirst()",
        "        if obj is None:",
        f'            raise NotFoundAPIError("{name} not found.")',
        "        data = body.model_dump(exclude_unset=True)",
        *(["        await _require_relations(data)"] if _relations(fields) else []),
        "        for attr, value in data.items():",
        "            setattr(obj, attr, value)",
        "        await obj.asave()",
        f"        return {name}ResponseSchema.model_validate(obj)",
        "",
        f'    @delete("/<{conv}:{snake}_id>")',
        *guard,
        f"    async def delete_{snake}(self, request, {snake}_id: {key}) -> None:",
        f'        """Delete a {name}."""',
        f"        obj = await {name}.objects.filter(id={snake}_id).afirst()",
        "        if obj is None:",
        f'            raise NotFoundAPIError("{name} not found.")',
        "        await obj.adelete()",
        "",
    ]
    return "\n".join(lines)


def render_controller(name: str, fields: list[FieldSpec], layout: BackendLayout) -> str:
    if layout.framework == DJANGO_MATT:
        return render_matt_controller(name, fields, layout)
    return render_ninja_controller(name, fields, layout)


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
