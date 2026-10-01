"""Scan JavaScript object and array literals without evaluating them.

The scanner skips strings, template literals, comments, nested brackets, and
JSX elements so a value ends at the first top-level ``,`` or closing bracket.
It does not understand every expression; callers treat any value they cannot
classify as computed and refuse to edit around it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")
_STRING_RE = re.compile(r"""(['"])((?:\\.|(?!\1)[^\\\n])*)\1""")
_TEMPLATE_RE = re.compile(r"`([^`$\\]*)`")
_OPENERS = {"{": "}", "[": "]", "(": ")"}
# A `<` starts JSX after these characters (or at the start of a value).
_JSX_PREV = set("(,:?=>{[&|!;")


class LiteralError(ValueError):
    """The text is not a literal this scanner can read safely."""


@dataclass
class JsProperty:
    key: str
    start: int  # start of the key
    value_start: int
    value_end: int  # exclusive; whitespace and comments trimmed
    value: str
    shorthand: bool = False  # `{ path }` or a method such as `loader() {}`


@dataclass
class JsObject:
    start: int  # offset of `{`
    end: int  # offset just past `}`
    props: dict[str, JsProperty] = field(default_factory=dict)
    spread: bool = False
    computed_key: bool = False
    duplicate_key: bool = False


@dataclass
class JsElement:
    start: int
    end: int
    obj: JsObject | None  # None when the element is not an object literal
    text: str


@dataclass
class JsArray:
    start: int  # offset of `[`
    end: int  # offset just past `]`
    elements: list[JsElement]
    trailing_comma: bool


def skip_space(text: str, i: int) -> int:
    """Return the first offset at or after *i* that is not whitespace or a comment."""
    n = len(text)
    while i < n:
        if text[i].isspace():
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end == -1 else end + 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                raise LiteralError("unterminated comment")
            i = end + 2
        else:
            break
    return i


def _skip_string(text: str, i: int) -> int:
    quote = text[i]
    i += 1
    while i < len(text):
        char = text[i]
        if char == "\\":
            i += 2
            continue
        if quote == "`" and text.startswith("${", i):
            i = scan_to(text, i + 2, "}") + 1
            continue
        if char == quote:
            return i + 1
        if char == "\n" and quote != "`":
            raise LiteralError("unterminated string")
        i += 1
    raise LiteralError("unterminated string")


def _skip_tag(text: str, i: int) -> tuple[int, bool]:
    """Skip a JSX tag starting at `<`; return (end, self-closing)."""
    i += 1
    while i < len(text):
        char = text[i]
        if char in "\"'":
            i = _skip_string(text, i)
        elif char == "{":
            i = scan_to(text, i + 1, "}") + 1
        elif text.startswith("/>", i):
            return i + 2, True
        elif char == ">":
            return i + 1, False
        else:
            i += 1
    raise LiteralError("unterminated JSX tag")


def skip_jsx(text: str, i: int) -> int:
    """Skip one JSX element (or fragment) starting at `<`; return the end offset."""
    depth = 0
    while i < len(text):
        if text.startswith("</", i):
            end = text.find(">", i)
            if end == -1:
                raise LiteralError("unterminated JSX closing tag")
            depth -= 1
            i = end + 1
            if depth == 0:
                return i
        elif text[i] == "<":
            i, self_closing = _skip_tag(text, i)
            if self_closing:
                if depth == 0:
                    return i
            else:
                depth += 1
        elif text[i] == "{":
            i = scan_to(text, i + 1, "}") + 1
        else:
            i += 1
    raise LiteralError("unterminated JSX element")


def _starts_jsx(text: str, i: int, prev: str) -> bool:
    if not re.match(r"<[A-Za-z>]", text[i : i + 2]):
        return False
    return prev in _JSX_PREV or re.search(r"\breturn\s*$", text[max(0, i - 12) : i]) is not None


def scan_to(text: str, i: int, stops: str) -> int:
    """Return the offset of the first top-level character of *stops* at or after *i*."""
    prev = "("
    while i < len(text):
        i = skip_space(text, i)
        if i >= len(text):
            break
        char = text[i]
        if char in stops:
            return i
        if char in "\"'`":
            i = _skip_string(text, i)
        elif char in _OPENERS:
            i = scan_to(text, i + 1, _OPENERS[char]) + 1
        elif char == "<" and _starts_jsx(text, i, prev):
            i = skip_jsx(text, i)
        elif char in ")]}":
            raise LiteralError(f"unbalanced {char!r}")
        else:
            i += 1
        prev = char if not char.isspace() else prev
    raise LiteralError(f"expected one of {stops!r}")


def _trim_end(text: str, start: int, end: int) -> int:
    """Trim whitespace and trailing comments from text[start:end]."""
    segment = text[start:end]
    while True:
        stripped = segment.rstrip()
        comment = re.search(r"//[^\n]*$|/\*.*?\*/$", stripped, re.S)
        if comment is None or _inside_string(stripped, comment.start()):
            return start + len(stripped)
        segment = stripped[: comment.start()]


def _inside_string(text: str, index: int) -> bool:
    return any(m.start() < index < m.end() for m in _STRING_RE.finditer(text))


def parse_object(text: str, i: int) -> JsObject:
    """Parse the object literal whose `{` is at *i*."""
    if text[i] != "{":
        raise LiteralError("expected an object literal")
    obj = JsObject(start=i, end=i)
    i += 1
    while True:
        i = skip_space(text, i)
        if i >= len(text):
            raise LiteralError("unterminated object literal")
        if text[i] == "}":
            obj.end = i + 1
            return obj
        key_start = i
        if text.startswith("...", i):
            obj.spread = True
            i = scan_to(text, i + 3, ",}")
        else:
            if text[i] == "[":
                obj.computed_key = True
                i = scan_to(text, i + 1, "]") + 1
                key = ""
            elif text[i] in "\"'":
                match = _STRING_RE.match(text, i)
                if match is None:
                    raise LiteralError("unterminated string key")
                key, i = match.group(2), match.end()
            else:
                match = _IDENT_RE.match(text, i) or re.compile(r"\d+").match(text, i)
                if match is None:
                    raise LiteralError(f"unexpected {text[i]!r} in object literal")
                key, i = match.group(), match.end()
            i = skip_space(text, i)
            shorthand = text[i] != ":"
            value_start = skip_space(text, i + 1) if not shorthand else key_start
            end = scan_to(text, value_start if not shorthand else i, ",}")
            value_end = _trim_end(text, value_start, end)
            if key in obj.props:
                obj.duplicate_key = True
            if key:
                obj.props[key] = JsProperty(
                    key, key_start, value_start, value_end, text[value_start:value_end], shorthand
                )
            i = end
        if text[i] == ",":
            i += 1


def parse_array(text: str, i: int) -> JsArray:
    """Parse the array literal whose `[` is at *i*; object elements are parsed too."""
    if text[i] != "[":
        raise LiteralError("expected an array literal")
    start, i = i, i + 1
    elements: list[JsElement] = []
    trailing = False
    while True:
        i = skip_space(text, i)
        if i >= len(text):
            raise LiteralError("unterminated array literal")
        if text[i] == "]":
            return JsArray(start, i + 1, elements, trailing)
        obj: JsObject | None = None
        if text[i] == "{":
            obj = parse_object(text, i)
            after = skip_space(text, obj.end)
            if after < len(text) and text[after] not in ",]":
                obj = None  # e.g. `{...} as RouteObject`
        end = obj.end if obj is not None else _trim_end(text, i, scan_to(text, i, ",]"))
        elements.append(JsElement(i, end, obj, text[i:end]))
        i = scan_to(text, end, ",]")
        trailing = text[i] == ","
        if trailing:
            i += 1


def string_value(value: str) -> str | None:
    """Return the content of a plain string literal, or None for anything else."""
    match = _STRING_RE.fullmatch(value.strip()) or _TEMPLATE_RE.fullmatch(value.strip())
    if match is None:
        return None
    content = match.group(match.lastindex or 1)
    return None if "\\" in content else content
