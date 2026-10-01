"""ORM statements shared by generated controllers and services.

Each renderer returns the statements of one CRUD operation, indented for a
method body, so an inline controller and the opt-in service class run the
same queries. *user* is the expression holding the authenticated user:
`request.user` in a controller, `user` in a service method.
"""

from __future__ import annotations

from dataclasses import dataclass

from mattstack.commands.codegen.backend_layout import DJANGO_MATT, BackendLayout
from mattstack.commands.codegen.fields import FieldSpec, search_field, to_snake
from mattstack.commands.codegen.py_lines import LINE_LIMIT, bracketed, from_import
from mattstack.commands.codegen.resource_policy import GLOBAL_QUERY_WAIVER, ResourcePolicy

BODY = " " * 8


@dataclass(frozen=True)
class Resource:
    """One generated resource: name, wire fields, project layout, and policy."""

    name: str
    fields: list[FieldSpec]  # wire fields: an owned resource's owner FK is not here
    layout: BackendLayout
    policy: ResourcePolicy

    @property
    def snake(self) -> str:
        return to_snake(self.name)

    @property
    def is_async(self) -> bool:
        return self.layout.framework == DJANGO_MATT

    @property
    def write_user(self) -> bool:
        """Writes run as an authenticated user (JWT-guarded or owned)."""
        return self.policy.owned or self.layout.has_jwt

    @property
    def waives_gate(self) -> bool:
        """The global list query is a Ninja `.objects.all()` carrying the gate waiver."""
        return not self.policy.owned and not self.is_async

    def uses_user(self, op: str) -> bool:
        """Whether *op* reads the authenticated user.

        Owned resources scope every operation by it; a global soft delete
        records it as `deleted_by` when writes are authenticated.
        """
        if self.policy.owned:
            return True
        return op == "delete" and self.policy.soft_delete and self.write_user


def relations(fields: list[FieldSpec]) -> list[str]:
    return [f.name for f in fields if f.is_fk]


def model_import(res: Resource) -> str:
    return "\n".join(from_import(f"{res.layout.app_module}.models.{res.snake}", [res.name]))


def schema_imports(res: Resource, suffixes: list[str]) -> list[str]:
    names = [f"    {res.name}{suffix}," for suffix in suffixes]
    return [f"from {res.layout.app_module}.schemas.{res.snake} import (", *names, ")"]


def service_module(res: Resource) -> str:
    return f"{res.layout.app_module}.services.{res.snake}_service"


def relations_helper(res: Resource) -> list[str]:
    """Module-level check that every referenced row exists.

    A missing related row is a 404 for the client, not an IntegrityError (500)
    from the database. The related model comes from the FK at runtime, so a
    swapped user model or lazy reference needs no import here.
    """
    if not relations(res.fields):
        return []
    head = "async def" if res.is_async else "def"
    quoted = [f'"{r}"' for r in relations(res.fields)]
    lines = [
        "",
        *(
            [f"RELATIONS = ({quoted[0]},)"]
            if len(quoted) == 1
            else bracketed("", "RELATIONS = ", quoted)
        ),
        "",
        "",
        f"{head} _require_relations(data: dict[str, object]) -> None:",
        '    """Answer 404 for a referenced row that does not exist."""',
        "    for relation in RELATIONS:",
        '        key = f"{relation}_id"',
        "        if key not in data:",
        "            continue",
        f"        field = {res.name}._meta.get_field(relation)",
        "        related = field.related_model",
    ]
    if res.is_async:
        lines += [
            "        if not await related._default_manager.filter(pk=data[key]).aexists():",
            '            raise NotFoundAPIError(f"{relation} {data[key]} not found.")',
        ]
    else:
        lines.append("        get_object_or_404(related, pk=data[key])")
    return lines


def _require_relations(res: Resource) -> list[str]:
    if not relations(res.fields):
        return []
    return [f"{BODY}{'await ' if res.is_async else ''}_require_relations(data)"]


def _owner_kwarg(res: Resource, user: str) -> list[str]:
    return [f"{res.policy.owner_field}={user}"] if res.policy.owned else []


def list_rows(res: Resource, user: str) -> list[str]:
    """`queryset = ...` for the list route: the caller's rows, or every row."""
    if res.policy.owned:
        return bracketed(BODY, f"queryset = {res.name}.objects.filter", _owner_kwarg(res, user))
    waiver = f"  {GLOBAL_QUERY_WAIVER}" if res.waives_gate else ""
    query = f"{res.name}.objects.all(){waiver}"
    if len(f"{BODY}queryset = {query}") <= LINE_LIMIT:
        return [f"{BODY}queryset = {query}"]
    # Formatters move a too-long line's trailing comment off the query; the
    # waiver must stay on the `.objects.all()` line, so parenthesize instead.
    return [f"{BODY}queryset = (", f"{BODY}    {query}", f"{BODY})"]


def search_filter(res: Resource) -> list[str]:
    field = search_field(res.fields)
    if not field:
        return []
    return [
        f"{BODY}if search:",
        *bracketed(f"{BODY}    ", "queryset = queryset.filter", [f"{field}__icontains=search"]),
    ]


def _soft_delete_args(res: Resource, user: str) -> str:
    return f"user={user}" if res.write_user else ""


# Django Ninja (sync) --------------------------------------------------------


def ninja_lookup(res: Resource, user: str, prefix: str) -> list[str]:
    """`<prefix>get_object_or_404(...)` for the row named by the path id, within scope."""
    rows = (
        f"{res.name}.objects.filter({res.policy.owner_field}={user})"
        if res.policy.owned
        else res.name
    )
    return bracketed(BODY, f"{prefix}get_object_or_404", [rows, f"id={res.snake}_id"])


def ninja_create(res: Resource, user: str, ret: str) -> list[str]:
    return [
        f"{BODY}data = {{field: getattr(payload, field) for field in type(payload).model_fields}}",
        *_require_relations(res),
        *bracketed(BODY, f"{ret}{res.name}.objects.create", ["**data", *_owner_kwarg(res, user)]),
    ]


def ninja_update(res: Resource, user: str) -> list[str]:
    return [
        *ninja_lookup(res, user, "obj = "),
        f"{BODY}data = {{field: getattr(payload, field) for field in payload.model_fields_set}}",
        *_require_relations(res),
        f"{BODY}for attr, value in data.items():",
        f"{BODY}    setattr(obj, attr, value)",
        f"{BODY}obj.save()",
        f"{BODY}return obj",
    ]


def ninja_delete(res: Resource, user: str) -> list[str]:
    call = f"soft_delete({_soft_delete_args(res, user)})" if res.policy.soft_delete else "delete()"
    return [*ninja_lookup(res, user, "obj = "), f"{BODY}obj.{call}"]


# django-matt (async) --------------------------------------------------------


def matt_lookup(res: Resource, user: str) -> list[str]:
    """Bind `obj` to the row named by the path id, within scope, or raise 404."""
    scope = [*_owner_kwarg(res, user), f"id={res.snake}_id"]
    return [
        *bracketed(BODY, f"obj = await {res.name}.objects.filter", scope, ".afirst()"),
        f"{BODY}if obj is None:",
        f'{BODY}    raise NotFoundAPIError("{res.name} not found.")',
    ]


def matt_create(res: Resource, user: str, payload: str = "body") -> list[str]:
    return [
        f"{BODY}data = {payload}.model_dump()",
        *_require_relations(res),
        *bracketed(
            BODY, f"obj = await {res.name}.objects.acreate", ["**data", *_owner_kwarg(res, user)]
        ),
    ]


def matt_update(res: Resource, user: str, payload: str = "body") -> list[str]:
    return [
        *matt_lookup(res, user),
        f"{BODY}data = {payload}.model_dump(exclude_unset=True)",
        *_require_relations(res),
        f"{BODY}for attr, value in data.items():",
        f"{BODY}    setattr(obj, attr, value)",
        f"{BODY}await obj.asave()",
    ]


def matt_delete(res: Resource, user: str) -> list[str]:
    if res.policy.soft_delete:
        call = f"await sync_to_async(obj.soft_delete)({_soft_delete_args(res, user)})"
    else:
        call = "await obj.adelete()"
    return [*matt_lookup(res, user), f"{BODY}{call}"]
