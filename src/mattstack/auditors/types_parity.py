"""Compare OpenAPI component schemas with the Zod schemas generated from them.

The comparison follows the `@hey-api/openapi-ts` zod plugin mapping recorded in
docs/architecture.md: required → no `.optional()`, nullable → `.nullable()`
or `.nullish()`, `minLength`/`minimum`/`minItems` → `.min()`/`.gte()`, and so on.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from mattstack.parsers.zod_schemas import ZodSchema, ZodType, canonical_number

STRING_FORMATS = {
    "date-time": "iso.datetime",
    "date": "iso.date",
    "time": "iso.time",
    "email": "email",
    "uuid": "uuid",
    "uri": "url",
    "ipv4": "ipv4",
}
OTHER_STRING_BASES = frozenset({"string", "ipv6", "base64", "base64url", "hostname", "jwt"})
INT_BASES = frozenset({"int", "int32", "uint32", "int64", "uint64", "bigint", "coerce.bigint"})
NUMBER_BASES = frozenset({"number", "float32", "float64"}) | INT_BASES
# The zod plugin adds these range checks for integer formats on its own.
FORMAT_BOUNDS = {
    "int32": ("-2147483648", "2147483647"),
    "int64": ("-9223372036854775808", "9223372036854775807"),
}
_OPENAPI_BOUNDS = (
    ("minLength", "min"),
    ("minItems", "min"),
    ("minimum", "min"),
    ("maxLength", "max"),
    ("maxItems", "max"),
    ("maximum", "max"),
)
# (OpenAPI key, OpenAPI 3.0 inclusive partner, Zod check)
_EXCLUSIVE_BOUNDS = (("exclusiveMinimum", "minimum", "gt"), ("exclusiveMaximum", "maximum", "lt"))
_ZOD_BOUNDS = {"min": "min", "gte": "min", "max": "max", "lte": "max", "gt": "gt", "lt": "lt"}
_SIGN_BOUNDS = {
    "positive": ("gt", "0"),
    "nonnegative": ("min", "0"),
    "negative": ("lt", "0"),
    "nonpositive": ("max", "0"),
}


@dataclass(frozen=True)
class Drift:
    """One difference between an OpenAPI schema and its generated Zod schema."""

    schema: str
    zod: ZodSchema | None
    message: str


def schema_key(name: str) -> str:
    """Match `APIKey_Response-1` with the generator's `zApiKeyResponse1`."""
    return re.sub(r"[^0-9a-z]", "", name.lower())


def find_drift(components: dict[str, dict[str, Any]], zod_schemas: list[ZodSchema]) -> list[Drift]:
    """Return every OpenAPI component that its generated Zod schema does not match."""
    by_key: dict[str, ZodSchema] = {}
    for schema in zod_schemas:
        if schema.name.startswith("z"):
            by_key.setdefault(schema_key(schema.name[1:]), schema)
    drift: list[Drift] = []
    for name, node in components.items():
        zod = by_key.get(schema_key(name))
        if zod is None:
            drift.append(Drift(name, None, f"{name}: no generated Zod schema"))
            continue
        drift.extend(Drift(name, zod, message) for message in _compare(node, zod.type, name))
        # The plugin drops writeOnly fields from the read schema and emits
        # `<Name>Writable` without readOnly fields for request bodies.
        writable = by_key.get(schema_key(name) + "writable")
        if writable is not None and name + "Writable" not in components:
            drift.extend(
                Drift(name, writable, message)
                for message in _compare(node, writable.type, f"{name}Writable", "readOnly")
            )
    return drift


def _unwrap(node: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Strip null from a node; return the remaining schema and whether null is allowed."""
    nullable = node.get("nullable") is True
    kind = node.get("type")
    if isinstance(kind, list) and "null" in kind:
        rest = [k for k in kind if k != "null"]
        node = {**node, "type": rest[0] if len(rest) == 1 else rest}
        nullable = True
    for key in ("anyOf", "oneOf"):
        branches = node.get(key)
        if isinstance(branches, list) and any(b.get("type") == "null" for b in branches):
            rest = [b for b in branches if b.get("type") != "null"]
            node = rest[0] if len(rest) == 1 else {key: rest}
            nullable = True
    all_of = node.get("allOf")
    if isinstance(all_of, list) and len(all_of) == 1 and isinstance(all_of[0], dict):
        node = all_of[0]
    return node, nullable


def _describe(zod: ZodType) -> str:
    return zod.ref if zod.base == "ref" else f"z.{zod.base}()"


def _compare(
    node: dict[str, Any], zod: ZodType, path: str, skip: str = "writeOnly"
) -> Iterator[str]:
    node, nullable = _unwrap(node)
    while zod.base == "lazy" and zod.items:
        zod = zod.items[0]
    if nullable != zod.nullable:
        state = "nullable" if nullable else "not nullable"
        yield f"{path}: {state} in OpenAPI, {'nullable' if zod.nullable else 'not nullable'} in Zod"
    yield from _compare_shape(node, zod, path, skip)


def _compare_shape(node: dict[str, Any], zod: ZodType, path: str, skip: str) -> Iterator[str]:
    if isinstance(node.get("$ref"), str):
        target = node["$ref"].rsplit("/", 1)[-1]
        if zod.base != "ref" or schema_key(zod.ref[1:]) != schema_key(target):
            yield f"{path}: OpenAPI references {target}, Zod uses {_describe(zod)}"
        return
    if "const" in node or isinstance(node.get("enum"), list):
        yield from _compare_values(node, zod, path)
        return
    for key in ("anyOf", "oneOf"):
        branches = node.get(key)
        if isinstance(branches, list):
            if zod.base != "union" or len(zod.items) != len(branches):
                found = _describe(zod)
                yield f"{path}: OpenAPI {key} with {len(branches)} options, Zod uses {found}"
                return
            for index, (branch, item) in enumerate(zip(branches, zod.items, strict=True)):
                yield from _compare(branch, item, f"{path}[{index}]", skip)
            return
    kind = node.get("type")
    if kind == "object" or "properties" in node:
        yield from _compare_object(node, zod, path, skip)
    elif kind == "array":
        yield from _compare_array(node, zod, path, skip)
    elif kind in ("string", "integer", "number", "boolean"):
        expected = _expected_bases(node)
        if zod.base not in expected:
            yield f"{path}: OpenAPI {_type_label(node)}, Zod uses {_describe(zod)}"
            return
        yield from _compare_bounds(node, zod, path)


def _type_label(node: dict[str, Any]) -> str:
    fmt = node.get("format")
    return f"{node['type']} ({fmt})" if isinstance(fmt, str) else str(node["type"])


def _expected_bases(node: dict[str, Any]) -> frozenset[str]:
    kind = node["type"]
    if kind == "string":
        fmt = node.get("format")
        if isinstance(fmt, str) and fmt in STRING_FORMATS:
            return frozenset({STRING_FORMATS[fmt]})
        return OTHER_STRING_BASES
    if kind == "integer":
        return INT_BASES
    if kind == "number":
        return NUMBER_BASES
    return frozenset({"boolean"})


def _compare_values(node: dict[str, Any], zod: ZodType, path: str) -> Iterator[str]:
    raw = [node["const"]] if "const" in node else node["enum"]
    expected = sorted(_json_value(value) for value in raw)
    if zod.base in ("enum", "literal"):
        actual = sorted(zod.values)
    elif zod.base == "union" and all(item.base == "literal" for item in zod.items):
        actual = sorted(value for item in zod.items for value in item.values)
    else:
        yield f"{path}: OpenAPI enum {expected}, Zod uses {_describe(zod)}"
        return
    if actual != expected:
        yield f"{path}: allowed values differ (OpenAPI {expected}, Zod {actual})"


def _json_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return canonical_number(value)
    return "null" if value is None else str(value)


def _compare_object(node: dict[str, Any], zod: ZodType, path: str, skip: str) -> Iterator[str]:
    properties = node.get("properties")
    if not isinstance(properties, dict) or not properties:
        if zod.base not in ("record", "object", "unknown", "any"):
            yield f"{path}: OpenAPI object, Zod uses {_describe(zod)}"
        extra = node.get("additionalProperties")
        if isinstance(extra, dict) and zod.base == "record" and zod.items:
            yield from _compare(extra, zod.items[-1], f"{path}[*]", skip)
        return
    if zod.base != "object":
        yield f"{path}: OpenAPI object, Zod uses {_describe(zod)}"
        return
    required = set(node.get("required", []))
    remaining = {zod_field.name: zod_field.type for zod_field in zod.fields}
    for name, prop in properties.items():
        if not isinstance(prop, dict) or prop.get(skip) is True:
            continue
        child = f"{path}.{name}"
        member = remaining.pop(name, None)
        if member is None:
            alias = next((key for key in remaining if schema_key(key) == schema_key(name)), None)
            if alias is None:
                yield f"{child}: missing from Zod"
            else:
                remaining.pop(alias)
                yield f"{child}: OpenAPI key '{name}', Zod key '{alias}' (alias mismatch)"
            continue
        if (name in required) == member.optional:
            state = "required" if name in required else "optional"
            actual = "optional" if member.optional else "required"
            yield f"{child}: {state} in OpenAPI, {actual} in Zod"
        yield from _compare(prop, member, child, skip)
    for name in remaining:
        yield f"{path}.{name}: in Zod but not in OpenAPI"


def _compare_array(node: dict[str, Any], zod: ZodType, path: str, skip: str) -> Iterator[str]:
    items = node.get("items")
    if zod.base == "tuple":
        # The plugin emits a tuple when minItems == maxItems; its length is the bound.
        members = zod.items
    elif zod.base == "array":
        members = zod.items[:1]
        yield from _compare_bounds(node, zod, path)
    else:
        yield f"{path}: OpenAPI array, Zod uses {_describe(zod)}"
        return
    if isinstance(items, dict):
        for member in members:
            yield from _compare(items, member, f"{path}[]", skip)


def _openapi_bounds(node: dict[str, Any]) -> set[tuple[str, str]]:
    bounds: set[tuple[str, str]] = set()
    for key, op in _OPENAPI_BOUNDS:
        value = node.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            bounds.add((op, canonical_number(value)))
    for key, inclusive, op in _EXCLUSIVE_BOUNDS:
        value = node.get(key)
        if value is True and isinstance(node.get(inclusive), int | float):
            # OpenAPI 3.0 form: a boolean flag on the inclusive bound.
            limit = canonical_number(node[inclusive])
            bounds.discard(("min" if op == "gt" else "max", limit))
            bounds.add((op, limit))
        elif isinstance(value, int | float) and not isinstance(value, bool):
            bounds.add((op, canonical_number(value)))
    if isinstance(node.get("pattern"), str):
        bounds.add(("pattern", node["pattern"]))
    return bounds


def _zod_bounds(zod: ZodType) -> set[tuple[str, str]]:
    bounds: set[tuple[str, str]] = set()
    for method, value in zod.checks:
        if method == "length":
            bounds |= {("min", value), ("max", value)}
        elif method == "regex":
            bounds.add(("pattern", value))
        elif method in _ZOD_BOUNDS:
            bounds.add((_ZOD_BOUNDS[method], value))
        elif method in _SIGN_BOUNDS:
            bounds.add(_SIGN_BOUNDS[method])
    return bounds


def _compare_bounds(node: dict[str, Any], zod: ZodType, path: str) -> Iterator[str]:
    expected = _openapi_bounds(node)
    actual = _zod_bounds(zod)
    fmt = node.get("format")
    if node.get("type") == "integer" and isinstance(fmt, str) and fmt in FORMAT_BOUNDS:
        low, high = FORMAT_BOUNDS[fmt]
        actual -= {("min", low), ("max", high)} - expected
    for op, value in sorted(expected - actual):
        yield f"{path}: OpenAPI {op} {value!r} has no matching Zod check"
    for op, value in sorted(actual - expected):
        yield f"{path}: Zod {op} {value!r} is not in OpenAPI"
