"""Parse Zod schemas from TypeScript, including `@hey-api/openapi-ts` output.

A small scanner tracks brackets, strings, regex literals, and comments, so
multi-line chains and nested calls parse without a TypeScript toolchain.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

# `export const zUser = z.object(...)`, `const userSchema = z...`, `const zA = zB;`
_DECL_RE = re.compile(r"^[ \t]*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?=z[.A-Z_])", re.M)
_CALL_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*(?:\((.*)\))?", re.S)
_BIGINT_RE = re.compile(r"BigInt\(\s*(['\"]?)(-?[\d.eE+]+)\1\s*\)")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
# A `/` after one of these starts a regex literal, not a division.
_REGEX_PREV = frozenset("(,=:[!&|?{};")
# Methods that change neither the wire shape nor validation constraints.
_IGNORED = frozenset({"describe", "meta", "readonly", "brand", "catch", "transform", "pipe"})
_OBJECT_BASES = frozenset({"object", "strictObject", "looseObject"})


@dataclass
class ZodType:
    """One Zod expression: a base constructor plus its method chain."""

    base: str  # "string", "int", "iso.datetime", "enum", "ref", "object", ...
    ref: str = ""  # referenced constant when base == "ref"
    optional: bool = False
    nullable: bool = False
    checks: list[tuple[str, str]] = field(default_factory=list)  # (method, first argument)
    items: list[ZodType] = field(default_factory=list)  # array/tuple/union/record members
    values: tuple[str, ...] = ()  # decoded enum or literal values
    fields: list[ZodField] = field(default_factory=list)  # z.object entries


@dataclass
class ZodField:
    name: str
    type: ZodType

    @property
    def type_str(self) -> str:
        return self.type.base

    @property
    def optional(self) -> bool:
        return self.type.optional

    @property
    def nullable(self) -> bool:
        return self.type.nullable

    @property
    def constraints(self) -> dict[str, str]:
        return {method: value or "true" for method, value in self.type.checks}


@dataclass
class ZodSchema:
    name: str
    file: Path
    line: int
    fields: list[ZodField] = field(default_factory=list)
    type: ZodType = field(default_factory=lambda: ZodType("unknown"))


def canonical_number(value: float | int) -> str:
    """Render a number the same way whether it came from JSON or JavaScript."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return repr(value) if isinstance(value, float) else str(value)


def js_value(token: str) -> str:
    """Decode a JavaScript literal (string, number, BigInt, keyword) to a comparable string."""
    token = token.strip()
    if len(token) >= 2 and token[0] in "'\"`" and token[-1] == token[0]:
        return re.sub(r"\\(u[0-9a-fA-F]{4}|.)", _unescape, token[1:-1], flags=re.S)
    if match := _BIGINT_RE.fullmatch(token):
        token = match.group(2)
    try:
        return canonical_number(int(token))
    except ValueError:
        pass
    try:
        return canonical_number(float(token))
    except ValueError:
        return token


def _unescape(match: re.Match[str]) -> str:
    code = match.group(1)
    if code.startswith("u") and len(code) == 5:
        return chr(int(code[1:], 16))
    return _ESCAPES.get(code, code)


def _skip_string(text: str, i: int) -> int:
    quote = text[i]
    i += 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return i


def _skip_regex(text: str, i: int) -> int:
    i += 1
    in_class = False
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if in_class:
            in_class = ch != "]"
        elif ch == "[":
            in_class = True
        elif ch == "/":
            i += 1
            while i < len(text) and text[i].isalpha():
                i += 1
            return i
        i += 1
    return i


def _structure(text: str, start: int = 0) -> Iterator[tuple[int, str, int]]:
    """Yield (index, char, depth) for code characters outside strings, regexes, and comments."""
    depth = 0
    prev = "("
    i = start
    while i < len(text):
        ch = text[i]
        if ch in "'\"`":
            i, prev = _skip_string(text, i), "a"
            continue
        if text.startswith("//", i):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
            continue
        if ch == "/" and prev in _REGEX_PREV:
            i, prev = _skip_regex(text, i), "a"
            continue
        if ch in ")]}":
            depth -= 1
        yield i, ch, depth
        if ch in "([{":
            depth += 1
        if not ch.isspace():
            prev = ch
        i += 1


def _split_top(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    last = 0
    for i, ch, depth in _structure(text):
        if ch == separator and depth == 0:
            parts.append(text[last:i])
            last = i + 1
    parts.append(text[last:])
    return [part.strip() for part in parts if part.strip()]


def _expression_end(text: str, start: int) -> int:
    for i, ch, depth in _structure(text, start):
        if depth < 0 or (ch == ";" and depth == 0):
            return i
        if ch == "\n" and depth == 0 and not text[i:].lstrip().startswith("."):
            return i
    return len(text)


def _call(segment: str) -> tuple[str, str | None]:
    match = _CALL_RE.fullmatch(segment.strip())
    if not match:
        return segment.strip(), None
    return match.group(1), match.group(2)


def _list_items(literal: str) -> list[str]:
    literal = literal.strip()
    if literal.startswith("[") and literal.endswith("]"):
        return _split_top(literal[1:-1], ",")
    return []


def _first_argument(method: str, args: str | None) -> str:
    first = _split_top(args or "", ",")
    if not first:
        return ""
    if method == "regex" and first[0].startswith("/"):
        source = first[0][1 : first[0].rstrip("dgimsuvy").rfind("/")]
        return source.replace("\\/", "/")
    return js_value(first[0])


def _object_fields(body: str) -> list[ZodField]:
    body = body.strip()
    if not (body.startswith("{") and body.endswith("}")):
        return []
    fields: list[ZodField] = []
    for entry in _split_top(body[1:-1], ","):
        if entry.startswith("..."):
            continue
        colon = next((i for i, ch, depth in _structure(entry) if ch == ":" and depth == 0), -1)
        if colon > 0:
            key = entry[:colon].strip()
            fields.append(ZodField(js_value(key), parse_zod_expression(entry[colon + 1 :])))
    return fields


def _fill_base(zod: ZodType, args: str) -> None:
    arguments = _split_top(args, ",")
    first = arguments[0] if arguments else ""
    if zod.base == "array":
        zod.items = [parse_zod_expression(first)]
    elif zod.base in ("tuple", "union"):
        zod.items = [parse_zod_expression(item) for item in _list_items(first)]
    elif zod.base == "record":
        zod.items = [parse_zod_expression(item) for item in arguments]
    elif zod.base == "enum":
        zod.values = tuple(js_value(item) for item in _list_items(first))
    elif zod.base == "literal":
        zod.values = (js_value(first),)
    elif zod.base in _OBJECT_BASES:
        zod.base = "object"
        zod.fields = _object_fields(first)
    elif zod.base == "lazy" and "=>" in first:
        zod.items = [parse_zod_expression(first.split("=>", 1)[1].strip().strip("{}"))]


def parse_zod_expression(expression: str) -> ZodType:
    """Parse one Zod expression such as ``z.string().max(50).nullish()``."""
    segments = _split_top(expression.strip().rstrip(";"), ".")
    if not segments:
        return ZodType("unknown")
    index = 1
    if segments[0] == "z":
        names: list[str] = []
        args = ""
        while index < len(segments):
            name, call_args = _call(segments[index])
            names.append(name)
            index += 1
            if call_args is not None:
                args = call_args
                break
        zod = ZodType(".".join(names))
        _fill_base(zod, args)
    elif re.fullmatch(r"[A-Za-z_$][\w$]*", segments[0]):
        zod = ZodType("ref", ref=segments[0])
    else:
        return ZodType("unknown")
    for segment in segments[index:]:
        method, method_args = _call(segment)
        if method in ("optional", "default"):
            zod.optional = True
        elif method == "nullable":
            zod.nullable = True
        elif method == "nullish":
            zod.optional = zod.nullable = True
        elif method == "int" and zod.base == "number":
            zod.base = "int"
        elif method not in _IGNORED:
            zod.checks.append((method, _first_argument(method, method_args)))
    return zod


def parse_zod_text(text: str, path: Path) -> list[ZodSchema]:
    """Parse every top-level Zod constant in *text*."""
    schemas: list[ZodSchema] = []
    for match in _DECL_RE.finditer(text):
        end = _expression_end(text, match.end())
        zod = parse_zod_expression(text[match.end() : end])
        line = text.count("\n", 0, match.start()) + 1
        schemas.append(ZodSchema(match.group(1), path, line, zod.fields, zod))
    return schemas


def parse_zod_file(path: Path) -> list[ZodSchema]:
    """Parse every top-level Zod constant in a TypeScript file."""
    return parse_zod_text(path.read_text(encoding="utf-8", errors="replace"), path)


def find_zod_files(project_path: Path) -> list[Path]:
    """Find hand-written TypeScript files likely containing Zod schemas."""
    from mattstack.parsers.utils import find_files

    patterns = [
        "**/schemas.ts",
        "**/schemas/*.ts",
        "**/forms/**/*.tsx",
        "**/forms/**/*.ts",
        "**/validation.ts",
        "**/validators.ts",
    ]
    return find_files(project_path, patterns)
