"""Parse Python Enum classes so generated TypeScript can reference them."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Pattern: class Name(str, Enum): or class Name(StrEnum):
ENUM_RE = re.compile(
    r"^class\s+(\w+)\s*\(\s*(?:[\w.]+,\s*)*"
    r"(?:str\s*,\s*)?(?:IntEnum|StrEnum|Enum)\s*\)\s*:",
    re.MULTILINE,
)

# Pattern: MEMBER = "value"  # optional comment
ENUM_MEMBER_RE = re.compile(
    r"""^\s{4}(\w+)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""", re.MULTILINE
)
DOCSTRING_RE = re.compile(r'"""(?:.|\n)*?"""')


@dataclass
class PythonEnum:
    """A Python enum, emitted as a TypeScript union type."""

    name: str
    values: list[str] = field(default_factory=list)


def _unescape(value: str) -> str:
    return re.sub(r"\\(.)", r"\1", value)


def parse_enums_file(path: Path) -> list[PythonEnum]:
    """Parse every enum class with string values from a Python file.

    A schema field can reference an enum, and TypeScript cannot resolve a
    name that was never emitted, so the type-check fails.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    enums: list[PythonEnum] = []

    for match in ENUM_RE.finditer(text):
        start = text[: match.start()].count("\n") + 1
        body: list[str] = []
        for line in lines[start:]:
            if line.strip() == "" or line.startswith("    ") or line.strip().startswith("#"):
                body.append(line)
            elif body:
                break
        values = [
            _unescape(member.group(2) if member.group(2) is not None else member.group(3))
            for member in ENUM_MEMBER_RE.finditer(DOCSTRING_RE.sub("", "\n".join(body)))
            if not member.group(1).startswith("_")
        ]
        enums.append(PythonEnum(name=match.group(1), values=values))

    return enums
