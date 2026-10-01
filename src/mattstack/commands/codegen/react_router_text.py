"""Text helpers shared by the JSX and route-object React Router editors."""

from __future__ import annotations

import re

from mattstack.commands.codegen.backend_layout import GenerateError

IMPORT_RE = re.compile(r"^import\b[\s\S]*?(['\"])[^'\"\n]+\1;?[ \t]*$", re.M)


def normalize_url(url: str) -> str:
    """React Router matches case-insensitively and ignores a trailing slash."""
    return (url.rstrip("/") or "/").lower()


def line_start(text: str, index: int) -> int:
    return text.rfind("\n", 0, index) + 1


def indent_at(text: str, index: int) -> str:
    line = text[line_start(text, index) :]
    return line[: len(line) - len(line.lstrip(" \t"))]


def has_import(text: str, component: str, spec: str, named: tuple[str, ...] = ()) -> bool:
    """True when *text* default-imports *component* (and *named*) from *spec*."""
    pattern = (
        rf"^import\s+{re.escape(component)}\s*(?:,\s*\{{([^}}]*)\}})?\s+from\s+"
        rf"(['\"]){re.escape(spec)}\2"
    )
    match = re.search(pattern, text, re.M)
    if match is None:
        return False
    listed = {n.strip() for n in (match.group(1) or "").split(",")}
    return set(named) <= listed


def import_insertion(
    text: str, component: str, spec: str, named: tuple[str, ...] = (), module: str = "App.tsx"
) -> tuple[int, str] | None:
    """Return (offset, text) adding `import component, { named } from spec`, or None."""
    if has_import(text, component, spec, named):
        return None
    for name in (component, *named):
        if re.search(rf"(?<![\w$.]){re.escape(name)}(?![\w$])", text):
            raise GenerateError(
                f"{module} already uses the name {name}; rename the page or register it by hand."
            )
    imports = list(IMPORT_RE.finditer(text))
    if not imports:
        raise GenerateError(f"{module} has no import block to extend.")
    pages = [m for m in imports if "/pages/" in m.group(0)]
    anchor = (pages or imports)[-1]
    quote = anchor.group(1)
    semi = ";" if anchor.group(0).rstrip().endswith(";") else ""
    names = f"{component}, {{ {', '.join(named)} }}" if named else component
    return anchor.end(), f"\nimport {names} from {quote}{spec}{quote}{semi}"
