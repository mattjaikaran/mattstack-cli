"""Lay out generated Python the way Ruff and Black format it.

Generated files must pass the project's `ruff format --check` and isort rules
without running a formatter. A bracketed construct stays on one line when it
fits; otherwise each item goes on its own line with a trailing comma, a
layout both formatters keep (the "magic trailing comma").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LINE_LIMIT = 88
IMPORT_RE = re.compile(r"^(from|import)\s+(\.*[\w.]*)")


def bracketed(
    indent: str, head: str, items: list[str], tail: str = "", brackets: str = "()"
) -> list[str]:
    """`head(items)tail` on one line when it fits, else one item per line."""
    opener, closer = brackets[0], brackets[1]
    one_line = f"{indent}{head}{opener}{', '.join(items)}{closer}{tail}"
    if len(one_line) <= LINE_LIMIT or not items:
        return [one_line]
    inner = indent + "    "
    return [
        f"{indent}{head}{opener}",
        *(f"{inner}{item}," for item in items),
        f"{indent}{closer}{tail}",
    ]


def _member_key(name: str) -> tuple[int, str]:
    """isort's default member order: CONSTANTS, then Classes, then functions."""
    if name.isupper() and len(name) > 1:
        return 0, name
    return (1 if name[:1].isupper() else 2), name


def from_import(module: str, names: list[str]) -> list[str]:
    """`from module import names` with names in isort order, one per line when too long."""
    ordered = sorted(names, key=_member_key)
    one_line = f"from {module} import {', '.join(ordered)}"
    if len(one_line) <= LINE_LIMIT:
        return [one_line]
    return bracketed("", f"from {module} import ", ordered)


def py_literal(value: object) -> str:
    """A Python literal for JSON-like *value*, with double-quoted strings."""
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, dict):
        pairs = ", ".join(f"{py_literal(k)}: {py_literal(v)}" for k, v in value.items())
        return "{" + pairs + "}"
    return repr(value)


@dataclass(frozen=True)
class _Import:
    first: int  # first line, including comments directly above
    end: int  # line index just past the statement
    module: str
    is_from: bool

    @property
    def package(self) -> str:
        return "." if self.module.startswith(".") else self.module.split(".", 1)[0]


def _imports(lines: list[str]) -> list[_Import]:
    """Top-level import statements, in file order."""
    found = []
    index = 0
    while index < len(lines):
        match = IMPORT_RE.match(lines[index])
        if match:
            first = index
            while first > 0 and lines[first - 1].startswith("#"):
                first -= 1
            if "(" in lines[index] and ")" not in lines[index]:
                while index < len(lines) and ")" not in lines[index]:
                    index += 1
            found.append(_Import(first, index + 1, match.group(2), match.group(1) == "from"))
        index += 1
    return found


def insert_import(text: str, statement: str, section: frozenset[str] = frozenset()) -> str | None:
    """Return *text* with the `from` import *statement* where isort places it.

    The statement joins its isort section: imports from its own top-level
    package, from the packages in *section* (the project's first-party
    packages), or, for a relative import, the other relative imports. It goes
    after the section's `import` lines, sorted among its `from` lines. With no
    section yet, it opens one after the last import (relative) or the last
    absolute import (first-party). Returns None when *text* has no import.
    """
    lines = text.split("\n")
    imports = _imports(lines)
    match = IMPORT_RE.match(statement)
    if match is None or match.group(1) != "from":
        raise ValueError(f"Not a from-import statement: {statement!r}")
    if not imports:
        return None
    new = _Import(0, 0, match.group(2), True)
    body = statement.rstrip("\n").split("\n")
    packages = {new.package} if new.package == "." else {new.package, *section}
    same = [i for i in imports if i.package in packages]
    if not same:
        before = [i for i in imports if new.package == "." or i.package != "."]
        if not before:  # only relative imports: first-party goes ahead of them
            start = imports[0].first
            return "\n".join([*lines[:start], *body, "", *lines[start:]])
        end = before[-1].end
        return "\n".join([*lines[:end], "", *body, *lines[end:]])
    key = new.module.lower()
    position = next(
        (i.first for i in same if i.is_from and i.module.lower() > key),
        same[-1].end,
    )
    return "\n".join([*lines[:position], *body, *lines[position:]])
