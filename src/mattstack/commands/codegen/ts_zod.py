"""Render backend schemas and enums as Zod schemas (`sync zod`)."""

from __future__ import annotations

import json
import re

from mattstack.commands.codegen.ts_schemas import (
    BARE_MAPPINGS,
    BARE_SEQUENCES,
    LITERAL_RE,
    MAPPING_RE,
    NUMERIC_RE,
    OPTIONAL_RE,
    SCALAR_TS,
    SEQUENCE_RE,
    SchemaSet,
    key_for,
    uses_camel,
    wire_type,
)
from mattstack.parsers.api_routes import split_args
from mattstack.parsers.python_enums import PythonEnum
from mattstack.parsers.python_schemas import PydanticSchema, split_top_level_union

SCALAR_ZOD: dict[str, str] = {
    "str": "z.string()",
    "UUID": "z.string().uuid()",
    "EmailStr": "z.string().email()",
    "HttpUrl": "z.string().url()",
    "AnyUrl": "z.string().url()",
    # Decimal is a JSON number or string depending on the renderer; see SCALAR_TS.
    "Decimal": "z.union([z.number(), z.string().regex(/^-?\\d+(\\.\\d+)?$/)])",
    "int": "z.number().int()",
    "StrictInt": "z.number().int()",
    "PositiveInt": "z.number().int().positive()",
    "NegativeInt": "z.number().int().negative()",
    "NonNegativeInt": "z.number().int().nonnegative()",
    "NonPositiveInt": "z.number().int().nonpositive()",
}


def zod_var(name: str) -> str:
    return f"{name[:1].lower()}{name[1:]}Schema"


def resolve_zod_type(type_str: str, available: set[str]) -> str:
    """Map an annotation to Zod; only names in *available* are referenced."""
    t = type_str.strip()
    members = split_top_level_union(t)
    if len(members) > 1:
        non_null = [m for m in members if m not in ("None", "NoneType")]
        inner = [resolve_zod_type(m, available) for m in non_null]
        union = inner[0] if len(inner) == 1 else f"z.union([{', '.join(inner)}])"
        return f"{union}.nullable()" if len(non_null) < len(members) else union
    if optional := OPTIONAL_RE.match(t):
        return f"{resolve_zod_type(optional.group(1), available)}.nullable()"
    if literal := LITERAL_RE.match(t):
        values = split_args(literal.group(1))
        return (
            f"z.enum([{', '.join(values)}])"
            if all(v[:1] in "\"'" for v in values)
            else "z.unknown()"
        )
    if seq := SEQUENCE_RE.match(t):
        return f"z.array({resolve_zod_type(split_args(seq.group(1))[0], available)})"
    if mapping := MAPPING_RE.match(t):
        return f"z.record(z.string(), {resolve_zod_type(mapping.group(2), available)})"
    if t in BARE_SEQUENCES:
        return "z.array(z.unknown())"
    if t in BARE_MAPPINGS:
        return "z.record(z.string(), z.unknown())"
    short = t.replace('"', "").replace("'", "").rsplit(".", 1)[-1]
    if short in SCALAR_ZOD:
        return SCALAR_ZOD[short]
    ts = SCALAR_TS.get(short)
    if ts in ("string", "number", "boolean"):
        return f"z.{ts}()"
    if short in available:
        return zod_var(short)
    return "z.unknown()"


def _constraints(base: str, constraints: dict[str, str]) -> str:
    methods = {
        "min_length": "min",
        "max_length": "max",
        "gt": "gt",
        "ge": "gte",
        "lt": "lt",
        "le": "lte",
    }
    for key, value in constraints.items():
        if (
            key in methods
            and NUMERIC_RE.match(value)
            and not base.startswith(("z.enum", "z.union"))
        ):
            base += f".{methods[key]}({value})"
        elif key in ("pattern", "regex") and re.match(r"^r?(['\"]).*\1$", value):
            base += f".regex(new RegExp({value.lstrip('r')}))"
    return base


def render_zod(schema: PydanticSchema, available: set[str], force_camel: bool) -> str:
    camel = uses_camel(schema, force_camel)
    var = zod_var(schema.name)
    lines = [f"export const {var} = z.object({{"]
    for f in schema.fields:
        wire = wire_type(schema, f)
        zod = resolve_zod_type(wire, available)
        if wire == f.type_str:  # Field constraints describe the declared type only
            zod = _constraints(zod, f.constraints)
        if f.optional and not zod.endswith(".nullable()"):
            zod += ".nullable()"
        if f.has_default:
            zod += ".optional()"
        lines.append(f"  {key_for(f, camel)}: {zod},")
    lines += ["});", "", f"export type {schema.name} = z.infer<typeof {var}>;"]
    return "\n".join(lines)


def render_enum_zod(enum: PythonEnum) -> str:
    if not enum.values:
        return f"export const {zod_var(enum.name)} = z.string();"
    values = ", ".join(json.dumps(v) for v in enum.values)
    return f"export const {zod_var(enum.name)} = z.enum([{values}]);"


def _dependency_order(schemas: list[PydanticSchema]) -> list[PydanticSchema]:
    by_name = {s.name: s for s in schemas}
    ordered: list[PydanticSchema] = []
    state: dict[str, int] = {}

    def visit(schema: PydanticSchema) -> None:
        if state.get(schema.name):
            return
        state[schema.name] = 1
        for f in schema.fields:
            for ref in re.findall(r"\b[A-Z]\w*", f.type_str):
                if ref in by_name and ref != schema.name:
                    visit(by_name[ref])
        state[schema.name] = 2
        ordered.append(schema)

    for schema in schemas:
        visit(schema)
    return ordered


def render_zod_file(schema_set: SchemaSet, header: str, force_camel: bool) -> str:
    """Render Zod schemas in dependency order; a cyclic reference becomes z.unknown()."""
    blocks = [render_enum_zod(e) for e in schema_set.enums]
    available = set(schema_set.enum_names)
    for schema in _dependency_order(schema_set.schemas):
        blocks.append(render_zod(schema, available, force_camel))
        available.add(schema.name)
    return header + '\nimport { z } from "zod";\n\n' + "\n\n".join(blocks) + "\n"
