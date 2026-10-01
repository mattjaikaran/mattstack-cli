"""Render the opt-in service class that holds a generated resource's ORM logic.

The class follows django-ninja-boilerplate's TodoService: the controller only
binds HTTP, and every method takes the authenticated user when the resource
policy needs it. A row outside the caller's scope raises the same 404 as a
missing row.
"""

from __future__ import annotations

from mattstack.commands.codegen.backend_layout import BackendLayout
from mattstack.commands.codegen.django_api import KEY_BITS, module_docstring, resource_path
from mattstack.commands.codegen.django_ops import (
    BODY,
    Resource,
    list_rows,
    matt_create,
    matt_delete,
    matt_lookup,
    matt_update,
    model_import,
    ninja_create,
    ninja_delete,
    ninja_lookup,
    ninja_update,
    relations_helper,
    schema_imports,
    search_filter,
)
from mattstack.commands.codegen.fields import FieldSpec
from mattstack.commands.codegen.py_lines import bracketed
from mattstack.commands.codegen.resource_policy import ResourcePolicy

OPERATIONS = ("list", "get", "create", "update", "delete")


def _method(res: Resource, op: str, head: str, *params: str, returns: str) -> list[str]:
    """Method `def`; `user` leads for list and trails otherwise, as in TodoService."""
    user = ["user: Any"] if res.uses_user(op) else []
    ordered = [*user, *params] if op == "list" else [*params, *user]
    return bracketed("    ", head, ["self", *ordered], f" -> {returns}:")


def _imports(res: Resource) -> list[str]:
    stdlib = []
    if any(res.uses_user(op) for op in OPERATIONS):
        stdlib.append("from typing import Any")
    if res.layout.pk_key == "uuid":
        stdlib.append("from uuid import UUID")
    third_party = []
    if res.is_async and res.policy.soft_delete:
        third_party.append("from asgiref.sync import sync_to_async")
    third_party.append("from django.db.models import QuerySet")
    if res.is_async:
        third_party.append("from django_matt.core.errors import NotFoundAPIError")
    else:
        third_party.append("from django.shortcuts import get_object_or_404")
    return [
        *([*stdlib, ""] if stdlib else []),
        *third_party,
        "",
        model_import(res),
        *schema_imports(res, ["CreateSchema", "UpdateSchema"]),
        *relations_helper(res),
    ]


def render_service(
    name: str, fields: list[FieldSpec], layout: BackendLayout, policy: ResourcePolicy
) -> str:
    """Render `<Name>Service` with list/get/create/update/delete under *policy*.

    *fields* are wire fields (`api_fields`). Ninja methods are sync and raise
    Http404 through get_object_or_404; django-matt methods are async (except
    the lazy list queryset) and raise NotFoundAPIError.
    """
    res = Resource(name, fields, layout, policy)
    snake, plural = res.snake, resource_path(name)
    key = KEY_BITS[layout.pk_key][0]
    head = "async def" if res.is_async else "def"
    if res.is_async:
        get_body = [*matt_lookup(res, "user"), f"{BODY}return obj"]
        create_body = [*matt_create(res, "user", "payload"), f"{BODY}return obj"]
        update_body = [*matt_update(res, "user", "payload"), f"{BODY}return obj"]
        delete_body = matt_delete(res, "user")
    else:
        get_body = ninja_lookup(res, "user", "return ")
        create_body = ninja_create(res, "user", ret="return ")
        update_body = ninja_update(res, "user")
        delete_body = ninja_delete(res, "user")
    lines = [
        *module_docstring(f"Business logic for {name}.", res, holds_list_query=True),
        *_imports(res),
        "",
        "",
        f"class {name}Service:",
        f'    """Create, read, update, and delete {name} rows under the resource policy."""',
        "",
        *_method(
            res,
            "list",
            f"def list_{plural}",
            "search: str | None = None",
            returns=f"QuerySet[{name}]",
        ),
        f'        """Return visible {name} rows matching *search*, newest first."""',
        *list_rows(res, "user"),
        *search_filter(res),
        f"{BODY}return queryset",
        "",
        *_method(res, "get", f"{head} get_{snake}", f"{snake}_id: {key}", returns=name),
        f'        """Return one visible {name}; 404 when no visible row has the id."""',
        *get_body,
        "",
        *_method(
            res, "create", f"{head} create_{snake}", f"payload: {name}CreateSchema", returns=name
        ),
        f'        """Create a {name} from a validated payload."""',
        *create_body,
        "",
        *_method(
            res,
            "update",
            f"{head} update_{snake}",
            f"{snake}_id: {key}",
            f"payload: {name}UpdateSchema",
            returns=name,
        ),
        '        """Apply the fields sent in the payload."""',
        *update_body,
        "",
        *_method(res, "delete", f"{head} delete_{snake}", f"{snake}_id: {key}", returns="None"),
        f'        """Delete one visible {name}."""',
        *delete_body,
        "",
    ]
    return "\n".join(lines)
