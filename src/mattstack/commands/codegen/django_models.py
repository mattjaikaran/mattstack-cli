"""Render Django models, API schemas, and admin classes for `generate`."""

from __future__ import annotations

from mattstack.commands.codegen.backend_layout import DJANGO_MATT, BackendLayout
from mattstack.commands.codegen.fields import (
    DJANGO_FIELD_MAP,
    FK_KEY_TYPES,
    FieldSpec,
    search_field,
    to_snake,
)


def render_model(name: str, fields: list[FieldSpec], layout: BackendLayout) -> str:
    """Render a model. FKs carry resolved lazy references, so no model imports."""
    snake = to_snake(name)
    base = layout.base_model_module
    needs_uuid = base is None or any(f.type == "uuid" for f in fields)
    lines = [f'"""Django model for {name}."""', "", "from __future__ import annotations", ""]
    if needs_uuid:
        lines += ["import uuid", ""]
    if any(f.fk_reference == "settings.AUTH_USER_MODEL" for f in fields):
        lines.append("from django.conf import settings")
    lines.append("from django.db import models")
    if base:
        lines += ["", f"from {base} import AbstractBaseModel"]
    lines += ["", "", f"class {name}({'AbstractBaseModel' if base else 'models.Model'}):"]
    if base is None:
        lines.append(
            "    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)"
        )

    targets = [f.fk_target for f in fields if f.is_fk]
    for field in fields:
        if field.is_fk:
            if not field.fk_reference:
                raise ValueError(f"FK field '{field.name}' has no resolved target")
            related = (
                f"{snake}s" if targets.count(field.fk_target) == 1 else f"{snake}_{field.name}s"
            )
            lines.append(
                f"    {field.name} = models.ForeignKey({field.fk_reference}, "
                f'on_delete=models.CASCADE, related_name="{related}")'
            )
        else:
            lines.append(f"    {field.name} = models.{DJANGO_FIELD_MAP[field.type]}")
    if base is None:
        lines += [
            "    created_at = models.DateTimeField(auto_now_add=True)",
            "    updated_at = models.DateTimeField(auto_now=True)",
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


def render_schemas(name: str, fields: list[FieldSpec], framework: str, pk_key: str) -> str:
    """Render Base/Create/Update/Response schemas matching the model's wire format.

    FK fields are `<name>_id` typed by the target's real primary key:
    `Model.objects.create(**payload)` accepts the column name, and responses
    read the raw id rather than a model object. Update fields may be omitted
    but not sent as null: every generated column is NOT NULL, so a null is a
    validation error instead of a silently dropped value.
    """
    id_type = FK_KEY_TYPES[pk_key][0]
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
    if framework == DJANGO_MATT:
        pydantic_names.insert(0, "BaseModel")
        base_class, third_party = "BaseModel", []
    else:
        base_class, third_party = "Schema", ["from ninja import Schema"]
    third_party.append(f"from pydantic import {', '.join(sorted(pydantic_names))}")

    def field_lines(optional: bool) -> list[str]:
        if not fields:
            return ["    pass"]
        out = []
        for field in fields:
            args = ", ".join(
                a for a in ("default=None" if optional else "", field.py_constraints) if a
            )
            suffix = f" = Field({args})" if args else ""
            out.append(f"    {field.api_name}: {field.py_type}{suffix}")
        return out

    lines = [
        f'"""API schemas for {name}."""',
        "",
        *stdlib,
        "",
        *third_party,
        "",
        "",
        f"class {name}BaseSchema({base_class}):",
        *field_lines(optional=False),
        "",
        "",
        f"class {name}CreateSchema({name}BaseSchema):",
        "    pass",
        "",
        "",
        f"class {name}UpdateSchema({base_class}):",
        *field_lines(optional=True),
        "",
        "",
        f"class {name}ResponseSchema({name}BaseSchema):",
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
    targets = ", ".join(f'"{n}"' for n in names)
    return [
        "",
        f"    @field_serializer({targets})",
        "    def serialize_decimals(self, value: Decimal) -> str:",
        '        return str(value.quantize(Decimal("0.01")))',
    ]


def render_admin(name: str, fields: list[FieldSpec], layout: BackendLayout) -> str:
    """Render a ModelAdmin; unfold's when the project depends on django-unfold."""
    snake = to_snake(name)
    text_fields = [f.name for f in fields if f.type in ("str", "text", "email")][:3]
    display = ", ".join(f'"{f}"' for f in ["id", *text_fields, "created_at"])
    search = text_fields or ["id"]
    search_tuple = (
        "(" + ", ".join(f'"{f}"' for f in search) + ("," if len(search) == 1 else "") + ")"
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
            f"from {layout.app_module}.models.{snake} import {name}",
            "",
            "",
            f"@admin.register({name})",
            f"class {name}Admin({parent}):",
            f"    list_display = [{display}]",
            '    list_filter = ("created_at",)',
            f"    search_fields = {search_tuple}",
            '    readonly_fields = ("id", "created_at", "updated_at")',
            "",
        ]
    )
