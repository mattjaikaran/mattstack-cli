"""Render Django models, API schemas, and admin classes for `generate`."""

from __future__ import annotations

from mattstack.commands.codegen.backend_layout import DJANGO_MATT, BackendLayout
from mattstack.commands.codegen.fields import (
    DJANGO_FIELD_MAP,
    FIELD_VALUE_TYPES,
    FK_KEY_TYPES,
    FieldSpec,
    search_field,
    to_snake,
)
from mattstack.commands.codegen.py_lines import LINE_LIMIT, bracketed, from_import
from mattstack.commands.codegen.resource_policy import DEFAULT_POLICY, ResourcePolicy


def _field(name: str, column: str, value_type: str, args: str) -> list[str]:
    """A model field annotated `models.<column>[set, get]`.

    Without the django-stubs mypy plugin, mypy cannot infer a field's value
    types and reports `var-annotated`; the annotation states them. The value
    type is the instance attribute's type; FK targets resolve lazily, so FKs
    use Any.
    """
    target = f"{name}: models.{column}[{value_type}, {value_type}]"
    items = args.split(", ") if args else []
    if len(f"    {target} = models.{column}(") <= LINE_LIMIT:
        return bracketed("    ", f"{target} = models.{column}", items)
    # The call cannot open on the target's line: parenthesize the value.
    return [f"    {target} = (", *bracketed(" " * 8, f"models.{column}", items), "    )"]


def render_model(
    name: str,
    fields: list[FieldSpec],
    layout: BackendLayout,
    policy: ResourcePolicy = DEFAULT_POLICY,
) -> str:
    """Render a model. FKs carry resolved lazy references, so no model imports.

    The model inherits *policy*'s lifecycle base class from the project's base
    model module; without one it declares a UUID id and timestamps itself.
    """
    snake = to_snake(name)
    base = layout.base_model_module
    parent = policy.base_class if base else "models.Model"
    needs_uuid = base is None or any(f.type == "uuid" for f in fields)
    value_types = {FIELD_VALUE_TYPES[f.type] for f in fields if not f.is_fk}
    stdlib = ["import uuid"] if needs_uuid else []
    dates = sorted(value_types & {"date", "datetime"} | ({"datetime"} if base is None else set()))
    if dates:
        stdlib.append(f"from datetime import {', '.join(dates)}")
    if "Decimal" in value_types:
        stdlib.append("from decimal import Decimal")
    if any(f.is_fk for f in fields):
        stdlib.append("from typing import Any")
    lines = [f'"""Django model for {name}."""', "", "from __future__ import annotations", ""]
    if stdlib:
        lines += [*stdlib, ""]
    if any(f.fk_reference == "settings.AUTH_USER_MODEL" for f in fields):
        lines.append("from django.conf import settings")
    lines.append("from django.db import models")
    if base:
        lines += ["", f"from {base} import {parent}"]
    lines += ["", "", f"class {name}({parent}):"]
    if base is None:
        args = "primary_key=True, default=uuid.uuid4, editable=False"
        lines += _field("id", "UUIDField", "uuid.UUID", args)

    targets = [f.fk_target for f in fields if f.is_fk]
    for field in fields:
        if field.is_fk:
            if not field.fk_reference:
                raise ValueError(f"FK field '{field.name}' has no resolved target")
            related = (
                f"{snake}s" if targets.count(field.fk_target) == 1 else f"{snake}_{field.name}s"
            )
            args = f'{field.fk_reference}, on_delete=models.CASCADE, related_name="{related}"'
            lines += _field(field.name, "ForeignKey", "Any", args)
        else:
            column, args = DJANGO_FIELD_MAP[field.type].removesuffix(")").split("(", 1)
            lines += _field(field.name, column, FIELD_VALUE_TYPES[field.type], args)
    if base is None:
        lines += [
            *_field("created_at", "DateTimeField", "datetime", "auto_now_add=True"),
            *_field("updated_at", "DateTimeField", "datetime", "auto_now=True"),
        ]
    str_field = search_field(fields)
    lines += [
        "",
        "    class Meta:",
        f'        verbose_name = "{name}"',
        f'        verbose_name_plural = "{name}s"',
        '        ordering = ["-created_at"]',
        "",
        "    def __str__(self) -> str:",
        f"        return self.{str_field}" if str_field else "        return str(self.pk)",
        "",
    ]
    return "\n".join(lines)


SCHEMA_SUFFIXES = ("BaseSchema", "CreateSchema", "UpdateSchema", "ResponseSchema")


def schema_class_names(name: str) -> list[str]:
    """Classes `render_schemas` defines for *name*, in file order."""
    return [f"{name}{suffix}" for suffix in SCHEMA_SUFFIXES]


def render_schemas(name: str, fields: list[FieldSpec], layout: BackendLayout) -> str:
    """Render Base/Create/Update/Response schemas matching the model's wire format.

    FK fields are `<name>_id` typed by the target's real primary key, the
    column name the controller passes to the ORM, and responses read the raw
    id rather than a model object. Update fields may be omitted but not sent
    as null: every generated column is NOT NULL, so a null is a validation
    error instead of a silently dropped value. When the project defines
    CamelCaseSchema, every schema inherits it, so its camelCase aliases set the
    wire names; field names stay snake_case.
    """
    id_type = FK_KEY_TYPES[layout.pk_key][0]
    types = {f.py_type for f in fields} | {id_type}
    stdlib: list[str] = []
    dt = sorted(types & {"date"} | {"datetime"})
    stdlib.append(f"from datetime import {', '.join(dt)}")
    if "Decimal" in types:
        stdlib.append("from decimal import Decimal")
    if "UUID" in types:
        stdlib.append("from uuid import UUID")
    pydantic_names = ["ConfigDict", *sorted(types & {"EmailStr", "HttpUrl"})]
    if fields:
        pydantic_names.append("Field")
    decimals = [f.api_name for f in fields if f.type == "decimal"]
    if decimals:
        pydantic_names.append("field_serializer")
    first_party: list[str] = []
    third_party: list[str]
    if layout.framework == DJANGO_MATT:
        pydantic_names.insert(0, "BaseModel")
        base_class, third_party = "BaseModel", []
    elif layout.camel_schema_module:
        base_class, third_party = "CamelCaseSchema", []
        first_party = ["", f"from {layout.camel_schema_module} import CamelCaseSchema"]
    else:
        base_class, third_party = "Schema", ["from ninja import Schema"]
    third_party += from_import("pydantic", sorted(pydantic_names))

    def field_lines(optional: bool) -> list[str]:
        if not fields:
            return ["    pass"]
        out = []
        for field in fields:
            args = [a for a in ("default=None" if optional else "", field.py_constraints) if a]
            declared = f"{field.api_name}: {field.py_type}"
            if args:
                out += bracketed("    ", f"{declared} = Field", ", ".join(args).split(", "))
            else:
                out.append(f"    {declared}")
        return out

    lines = [
        f'"""API schemas for {name}."""',
        "",
        *stdlib,
        "",
        *third_party,
        *first_party,
        "",
        "",
        *bracketed("", f"class {name}BaseSchema", [base_class], ":"),
        *field_lines(optional=False),
        "",
        "",
        *bracketed("", f"class {name}CreateSchema", [f"{name}BaseSchema"], ":"),
        "    pass",
        "",
        "",
        *bracketed("", f"class {name}UpdateSchema", [base_class], ":"),
        *field_lines(optional=True),
        "",
        "",
        *bracketed("", f"class {name}ResponseSchema", [f"{name}BaseSchema"], ":"),
        "    model_config = ConfigDict(from_attributes=True)",
        "",
        f"    id: {id_type}",
        "    created_at: datetime",
        "    updated_at: datetime",
        *_decimal_serializer(decimals),
        "",
    ]
    return "\n".join(lines)


def _decimal_serializer(names: list[str]) -> list[str]:
    """Write Decimal columns as fixed-point strings ("12.50").

    Without this the wire format depends on the project's JSON renderer: an
    orjson renderer writes 12.5 as a float and loses the column's scale. Only
    the response schema has it, so create/update payloads keep their Decimals.
    The quantum matches DJANGO_FIELD_MAP["decimal"] (decimal_places=2).
    """
    if not names:
        return []
    return [
        "",
        *bracketed("    ", "@field_serializer", [f'"{n}"' for n in names]),
        "    def serialize_decimals(self, value: Decimal) -> str:",
        '        return str(value.quantize(Decimal("0.01")))',
    ]


def render_admin(name: str, fields: list[FieldSpec], layout: BackendLayout) -> str:
    """Render a ModelAdmin; unfold's when the project depends on django-unfold."""
    snake = to_snake(name)
    text_fields = [f.name for f in fields if f.type in ("str", "text", "email")][:3]
    display = [f'"{f}"' for f in ["id", *text_fields, "created_at"]]
    search = [f'"{f}"' for f in text_fields or ["id"]]
    search_lines = (
        [f"    search_fields = ({search[0]},)"]
        if len(search) == 1
        else bracketed("    ", "search_fields = ", search)
    )
    if layout.has_unfold:
        imports = ["from django.contrib import admin", "from unfold.admin import ModelAdmin"]
        parent = "ModelAdmin"
    else:
        imports = ["from django.contrib import admin"]
        parent = "admin.ModelAdmin"
    return "\n".join(
        [
            f'"""Admin configuration for {name}."""',
            "",
            *imports,
            "",
            *from_import(f"{layout.app_module}.models.{snake}", [name]),
            "",
            "",
            f"@admin.register({name})",
            f"class {name}Admin({parent}):",
            *bracketed("    ", "list_display = ", display, brackets="[]"),
            '    list_filter = ("created_at",)',
            *search_lines,
            '    readonly_fields = ("id", "created_at", "updated_at")',
            "",
        ]
    )
