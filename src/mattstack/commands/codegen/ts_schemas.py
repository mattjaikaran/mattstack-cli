"""Collect backend schemas and render them as TypeScript and Zod.

Schemas inherit fields and alias generators from their bases, clashing names
from different modules are qualified rather than silently dropped, and every
type resolves to an emitted name or `unknown`, so the output type-checks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from mattstack.commands.codegen.fields import to_pascal, ts_key
from mattstack.parsers.api_routes import split_args
from mattstack.parsers.python_enums import PythonEnum, parse_enums_file
from mattstack.parsers.python_schemas import (
    PydanticField,
    PydanticSchema,
    find_schema_files,
    parse_pydantic_file,
    resolve_schema_inheritance,
    split_top_level_union,
)
from mattstack.parsers.utils import find_files

SCALAR_TS: dict[str, str] = {
    **dict.fromkeys(
        [
            "str",
            "bytes",
            "date",
            "datetime",
            "time",
            "timedelta",
            "UUID",
            "EmailStr",
            "AnyUrl",
            "HttpUrl",
            "FileUrl",
            "PostgresDsn",
            "RedisDsn",
            "SecretStr",
            "SecretBytes",
            "IPvAnyAddress",
            "StrictStr",
        ],
        "string",
    ),
    **dict.fromkeys(
        [
            "int",
            "float",
            "PositiveInt",
            "NegativeInt",
            "NonNegativeInt",
            "NonPositiveInt",
            "StrictInt",
            "StrictFloat",
            "PositiveFloat",
            "NonNegativeFloat",
        ],
        "number",
    ),
    "bool": "boolean",
    "StrictBool": "boolean",
    "Any": "unknown",
    "Json": "unknown",
    "object": "Record<string, unknown>",
    # The wire form of Decimal depends on the project's renderer: Ninja's
    # JSONRenderer writes a string, an orjson renderer usually a float. Only a
    # `@field_serializer` (see `wire_type`) settles it for a field.
    "Decimal": "number | string",
}
SEQUENCE_RE = re.compile(
    r"^(?:list|List|set|Set|frozenset|FrozenSet|Sequence|Iterable|tuple|Tuple)\[(.+)\]$"
)
MAPPING_RE = re.compile(r"^(?:dict|Dict|Mapping)\[(.+?),\s*(.+)\]$")
LITERAL_RE = re.compile(r"^(?:typing\.)?Literal\[(.+)\]$")
OPTIONAL_RE = re.compile(r"^(?:typing\.)?Optional\[(.+)\]$")
BARE_SEQUENCES = frozenset(
    ["list", "List", "set", "Set", "tuple", "Tuple", "Sequence", "Iterable", "frozenset"]
)
BARE_MAPPINGS = frozenset(["dict", "Dict", "Mapping"])
NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")
CAMEL_GENERATORS = frozenset({"to_camel", "to_lower_camel"})


@dataclass
class SchemaSet:
    schemas: list[PydanticSchema]
    enums: list[PythonEnum]
    warnings: list[str] = field(default_factory=list)

    @property
    def names(self) -> set[str]:
        return {s.name for s in self.schemas}

    @property
    def enum_names(self) -> set[str]:
        return {e.name for e in self.enums}

    @property
    def request_names(self) -> dict[str, str]:
        """Schema name -> request interface name; see `request_variants`."""
        return request_variants(self.schemas, self.names | self.enum_names)


def _app_of(path: Path, backend_dir: Path) -> str:
    parts = [p for p in path.relative_to(backend_dir).parts if p not in ("apps", "src")]
    return parts[0] if len(parts) > 1 else ""


def _signature(schema: PydanticSchema) -> tuple[object, ...]:
    fields = tuple((f.api_name, f.type_str, f.optional, f.has_default) for f in schema.fields)
    camel = schema.alias_generator in CAMEL_GENERATORS
    return (fields, camel, tuple(sorted(schema.serializers.items())))


def collect_schema_set(backend_dir: Path) -> SchemaSet:
    """Parse, inherit, de-duplicate, and qualify every schema under *backend_dir*."""
    raw = [s for f in find_schema_files(backend_dir) for s in parse_pydantic_file(f)]
    resolved = resolve_schema_inheritance(raw)
    parents = {(s.parent or "").rsplit(".", 1)[-1] for s in resolved}
    kept = [s for s in resolved if s.fields or s.name not in parents]

    enums: dict[str, PythonEnum] = {}
    for f in find_files(backend_dir, ["**/*.py"]):
        for enum in parse_enums_file(f):
            enums.setdefault(enum.name, enum)

    groups: dict[str, list[PydanticSchema]] = {}
    for schema in kept:
        groups.setdefault(schema.name, []).append(schema)
    result = SchemaSet(schemas=[], enums=list(enums.values()))
    # (file, original name) -> emitted name; references resolve within a file.
    renames: dict[tuple[Path, str], str] = {}
    for name, members in groups.items():
        distinct: dict[tuple[object, ...], PydanticSchema] = {}
        for schema in members:
            distinct.setdefault(_signature(schema), schema)
        if len(distinct) == 1:
            result.schemas.append(members[0])
            continue
        apps = [_app_of(s.file, backend_dir) for s in distinct.values()]
        unique_apps = len(set(apps)) == len(apps) and all(apps)
        for schema, app in zip(distinct.values(), apps, strict=True):
            if unique_apps:
                qualifier = to_pascal(app)
            else:
                parts = schema.file.relative_to(backend_dir).with_suffix("").parts
                qualifier = "".join(to_pascal(p) for p in parts if p not in ("apps", "schemas"))
            for member in members:
                if _signature(member) == _signature(schema):
                    renames[(member.file, name)] = qualifier + name
            schema.name = qualifier + name
            result.schemas.append(schema)
        result.warnings.append(
            f"{name} has {len(distinct)} different definitions; emitted as "
            + ", ".join(s.name for s in distinct.values())
        )
    if renames:
        for schema in result.schemas:
            fields = []
            for field in schema.fields:
                type_str = field.type_str
                for (file, original), qualified in renames.items():
                    if file == schema.file:
                        type_str = re.sub(rf"\b{original}\b", qualified, type_str)
                fields.append(replace(field, type_str=type_str))
            schema.fields = fields
    return result


LITERAL_KEYWORDS = {"None": "null", "True": "true", "False": "false"}


def _literal_ts(value: str) -> str:
    """One `Literal[...]` member as a TypeScript literal type."""
    if value[:1] in "\"'" and value[-1:] == value[:1]:
        return json.dumps(value[1:-1])
    if value in LITERAL_KEYWORDS:
        return LITERAL_KEYWORDS[value]
    return value if NUMERIC_RE.match(value) else "unknown"


def resolve_ts_type(type_str: str, known: set[str] | None = None) -> str:
    """Map a Python annotation to TypeScript; unknown names become `unknown`."""
    t = (
        type_str.strip().replace('"', "").replace("'", "")
        if "Literal" not in type_str
        else type_str.strip()
    )
    members = split_top_level_union(t)
    if len(members) > 1:
        out: list[str] = []
        for member in members:
            mapped = resolve_ts_type(member, known)
            if mapped not in out:
                out.append(mapped)
        return " | ".join(out)
    if optional := OPTIONAL_RE.match(t):
        return f"{resolve_ts_type(optional.group(1), known)} | null"
    if literal := LITERAL_RE.match(t):
        return " | ".join(_literal_ts(v) for v in split_args(literal.group(1)))
    if seq := SEQUENCE_RE.match(t):
        inner = resolve_ts_type(split_args(seq.group(1))[0], known)
        return f"({inner})[]" if " | " in inner else f"{inner}[]"
    if mapping := MAPPING_RE.match(t):
        return (
            f"Record<{resolve_ts_type(mapping.group(1), known)}, "
            f"{resolve_ts_type(mapping.group(2), known)}>"
        )
    if t in BARE_SEQUENCES:
        return "unknown[]"
    if t in BARE_MAPPINGS:
        return "Record<string, unknown>"
    short = t.rsplit(".", 1)[-1]
    if short in ("None", "NoneType"):
        return "null"
    if short in SCALAR_TS:
        return SCALAR_TS[short]
    if known is None or short in known:
        return short
    return "unknown"


def key_for(f: PydanticField, camel: bool, *, request: bool = False) -> str:
    """JSON key: an explicit alias wins; otherwise the alias generator applies."""
    explicit = (f.validation_alias or f.alias) if request else (f.serialization_alias or f.alias)
    key = explicit or ts_key(f.name, camel)
    return key if re.match(r"^[A-Za-z_$][\w$]*$", key) else f'"{key}"'


def uses_camel(schema: PydanticSchema, force_camel: bool) -> bool:
    return force_camel or schema.alias_generator in CAMEL_GENERATORS


def request_variants(schemas: list[PydanticSchema], reserved: set[str]) -> dict[str, str]:
    """Schema name -> request interface name, for schemas whose input keys differ.

    A schema differs when one of its own (or inherited) fields has a
    validation alias unlike its serialization alias, or when it references a
    schema that differs: a nested body must use the nested input keys too.
    Names avoid *reserved* (every exported schema and enum name), so a real
    `FooInput` schema never merges with the request variant of `Foo`.
    """
    taken = set(reserved)

    def allocate(name: str) -> str:
        candidate, suffix = f"{name}Input", 2
        while candidate in taken:
            candidate, suffix = f"{name}Input{suffix}", suffix + 1
        taken.add(candidate)
        return candidate

    variants: dict[str, str] = {}
    for s in schemas:
        if any(f.input_name != f.api_name for f in s.fields):
            variants[s.name] = allocate(s.name)
    changed = True
    while changed:
        changed = False
        for s in schemas:
            if s.name in variants:
                continue
            refs = {ref for f in s.fields for ref in re.findall(r"\b[A-Z]\w*", f.type_str)}
            if refs & variants.keys():
                variants[s.name] = allocate(s.name)
                changed = True
    return variants


def _to_request_type(type_str: str, variants: dict[str, str]) -> str:
    for name, request_name in variants.items():
        type_str = re.sub(rf"\b{name}\b", request_name, type_str)
    return type_str


def wire_type(schema: PydanticSchema, f: PydanticField) -> str:
    """Python type a response field is written as: a field_serializer's return wins."""
    returns = schema.serializers.get(f.name)
    return returns if returns and returns not in ("Any", "object") else f.type_str


def render_interface(
    schema: PydanticSchema,
    known: set[str],
    force_camel: bool,
    *,
    variants: dict[str, str] | None = None,
) -> str:
    """Render the response shape, or with *variants* the shape Pydantic validates."""
    request = variants is not None
    name = variants.get(schema.name, schema.name) if variants is not None else schema.name
    if not schema.fields:
        return f"export type {name} = Record<string, never>;"
    camel = uses_camel(schema, force_camel)
    lines = [f"export interface {name} {{"]
    for f in schema.fields:
        type_str = _to_request_type(f.type_str, variants) if variants else wire_type(schema, f)
        ts = resolve_ts_type(type_str, known | set((variants or {}).values()))
        if f.optional and "null" not in ts.split(" | "):
            ts = f"{ts} | null"
        key = key_for(f, camel, request=request)
        lines.append(f"  {key}{'?' if f.has_default else ''}: {ts};")
    lines.append("}")
    return "\n".join(lines)


def render_enum_union(enum: PythonEnum) -> str:
    if not enum.values:
        return f"export type {enum.name} = string;"
    return f"export type {enum.name} = {' | '.join(json.dumps(v) for v in enum.values)};"


def render_types_file(schema_set: SchemaSet, header: str, force_camel: bool) -> str:
    known = schema_set.names | schema_set.enum_names
    blocks = [render_enum_union(e) for e in schema_set.enums]
    blocks += [render_interface(s, known, force_camel) for s in schema_set.schemas]
    variants = schema_set.request_names
    blocks += [
        render_interface(s, known, force_camel, variants=variants)
        for s in schema_set.schemas
        if s.name in variants
    ]
    return header + "\n" + "\n\n".join(blocks) + "\n"
