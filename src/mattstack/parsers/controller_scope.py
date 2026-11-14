"""Resolve the `@api_controller` scope (URL prefix and class auth) of routes.

Django Ninja controllers declare their prefix and default auth on the class
decorator; the `@http_*` decorators inside the class body carry only the
sub-path. The route parser sees neither, so this module reads them from the
same file text.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from mattstack.parsers.django_routes import Route

API_CONTROLLER_RE = re.compile(r"^@api_controller\s*\(", re.MULTILINE)
STR_LITERAL_RE = re.compile(r"'([^'\n]*)'|\"([^\"\n]*)\"")
KEYWORD_RE = re.compile(r"(\w+)\s*=(?!=)\s*(.*)", re.DOTALL)


@dataclass(frozen=True)
class _Scope:
    start: int  # offset of the `@api_controller` line
    end: int  # offset where the class body ends
    prefix: str | None  # first positional string literal, if any
    auth: bool  # top-level `auth=` that is not None or False


def _string_end(text: str, start: int) -> int:
    """Return the index just past the string literal that opens at `start`."""
    quote = text[start]
    delim = quote * 3 if text.startswith(quote * 3, start) else quote
    i = start + len(delim)
    while i < len(text):
        if text[i] == "\\":
            i += 2
        elif text.startswith(delim, i):
            return i + len(delim)
        elif len(delim) == 1 and text[i] == "\n":
            return i
        else:
            i += 1
    return len(text)


def _code_chars(text: str, start: int) -> Iterator[tuple[int, str]]:
    """Yield (index, char) for every character outside string literals."""
    i = start
    while i < len(text):
        if text[i] in "'\"":
            i = _string_end(text, i)
        else:
            yield i, text[i]
            i += 1


def _call_args(text: str, open_at: int) -> tuple[list[str], int]:
    """Split call arguments at `open_at`; return them and the `)` index."""
    args: list[str] = []
    depth = 0
    piece = open_at + 1
    end = len(text)
    for i, ch in _code_chars(text, open_at):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                end = i
                break
        elif ch == "," and depth == 1:
            args.append(text[piece:i].strip())
            piece = i + 1
    args.append(text[piece:end].strip())
    return [arg for arg in args if arg], end


def _body_end(text: str, close: int) -> int:
    """Offset where the class body whose decorator closes at `close` ends.

    The class header and any stacked decorators sit at column 0 before the
    body, so they are skipped; the body ends at the next column-0 code line.
    """
    seen_class = False
    pos = text.find("\n", close) + 1
    if pos == 0:
        return len(text)
    while pos < len(text):
        eol = text.find("\n", pos)
        line_end = len(text) if eol == -1 else eol
        line = text[pos:line_end]
        if line.strip() and not line[0].isspace() and not line.startswith("#"):
            if seen_class or not line.startswith(("class ", "@")):
                return pos
            seen_class = line.startswith("class ")
        pos = line_end + 1
    return len(text)


def _literal(arg: str) -> str | None:
    match = STR_LITERAL_RE.fullmatch(arg)
    if match is None:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def _keyword(arg: str) -> tuple[str, str] | None:
    match = KEYWORD_RE.fullmatch(arg)
    if match is None:
        return None
    return match.group(1), match.group(2).strip()


def _has_auth_keyword(args: list[str]) -> bool:
    return any(kw is not None and kw[0] == "auth" for kw in map(_keyword, args))


class ControllerIndex:
    """Controller scopes of one route file, used to judge its routes."""

    def __init__(self, text: str) -> None:
        self._text = text
        self._line_starts = [0, *(m.end() for m in re.finditer("\n", text))]
        self._scopes = [
            self._scope(m.start(), m.end() - 1) for m in API_CONTROLLER_RE.finditer(text)
        ]

    def _scope(self, start: int, open_at: int) -> _Scope:
        args, close = _call_args(self._text, open_at)
        prefix = _literal(args[0]) if args else None
        auth = False
        for arg in args:
            kw = _keyword(arg)
            if kw is not None and kw[0] == "auth":
                auth = kw[1] not in ("None", "False")
        return _Scope(start=start, end=_body_end(self._text, close), prefix=prefix, auth=auth)

    def _scope_for(self, route: Route) -> _Scope | None:
        """Scope whose class body contains the route; indented decorators only."""
        line_start = self._line_starts[route.line - 1]
        if not self._text[line_start : line_start + 1].isspace():
            return None
        return next((s for s in self._scopes if s.start <= line_start < s.end), None)

    def _own_args(self, route: Route) -> list[str]:
        line_start = self._line_starts[route.line - 1]
        open_at = self._text.find("(", line_start)
        return _call_args(self._text, open_at)[0] if open_at != -1 else []

    def full_path(self, route: Route) -> str:
        scope = self._scope_for(route)
        if scope is None or scope.prefix is None:
            return route.path
        return scope.prefix.rstrip("/") + "/" + route.path.lstrip("/")

    def has_auth(self, route: Route) -> bool:
        if route.has_auth:
            return True
        scope = self._scope_for(route)
        if scope is None or not scope.auth:
            return False
        return not _has_auth_keyword(self._own_args(route))
