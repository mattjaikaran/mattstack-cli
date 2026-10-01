"""Inventory the client-side UI routes a frontend declares.

These are browser routes: URLs the SPA or Next.js app renders. They are not
server endpoints, and a wrapper such as ``ProtectedRoute`` is a client-side
redirect, not authorization, so the inventory reports wrappers by name only.

Sources, all read with regular expressions:

- TanStack Router: files under ``routes_dir`` that call ``createFileRoute`` or
  ``createLazyFileRoute``. Generated route trees and ``-``-prefixed files are
  skipped.
- React Router: static JSX ``<Route>`` elements in the app entry module.
  A ``path`` that is not a string literal makes that route and its children
  unresolvable, so they are omitted. Data routers (``createBrowserRouter``),
  ``useRoutes`` objects, and descendant ``<Routes>`` in other modules are not
  read.
- Next.js: ``page`` files of the App Router directory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from mattstack.parsers.frontend_layout import FrontendLayout
from mattstack.parsers.nextjs_routes import parse_nextjs_routes

ROUTE_SUFFIXES = (".tsx", ".ts", ".jsx", ".js")

_SEGMENT_RE = re.compile(r"[\w$-]+")
_FILE_ROUTE_RE = re.compile(r"""\bcreate(?:Lazy)?FileRoute\(\s*(?:(['"`])([^'"`]*)\1)?""")
_JSX_ROUTE_TOKEN_RE = re.compile(r"<Route\b|</Route\s*>")
# Attributes are matched on the top level of the tag; each `{...}` value is
# replaced by `{#n}`, so props of the element JSX never look like Route props.
_PATH_ATTR_RE = re.compile(r"""(?<![\w-])path\s*=\s*(?:(['"])(.*?)\1|\{#(\d+)\})?""")
_ELEMENT_RE = re.compile(r"(?<![\w-])(?:element|Component)\s*=\s*\{#(\d+)\}")
_INDEX_RE = re.compile(r"(?<![\w-])index(?![\w-])(?:\s*=\s*\{#(\d+)\})?")
_STRING_EXPR_RE = re.compile(r"""\s*(['"`])(.*)\1\s*""", re.DOTALL)
_COMPONENT_RE = re.compile(r"\s*<?\s*([A-Z][\w.]*)")
# Block comments start after whitespace or `{`, so "/*" inside a splat path stays.
_BLOCK_COMMENT_RE = re.compile(r"(?<![^\s{(;,])/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"^\s*//.*$", re.MULTILINE)


@dataclass(frozen=True)
class UiRoute:
    router: str  # "tanstack" | "react-router" | "nextjs"
    path: str  # URL pattern; params ($id, :id, [id]) and splats stay verbatim
    file: Path  # module that declares the route
    kind: str = "page"  # "page" | "index" | "layout" | "splat"
    route_id: str | None = None  # TanStack route id
    element: str | None = None  # React Router element component
    layouts: tuple[str, ...] = ()  # enclosing React Router route elements, outermost first


def tanstack_route_id(routes_dir: Path, path: Path) -> str | None:
    """Return the route id TanStack's generator derives from *path*.

    ``about.tsx`` gives ``/about``, ``a.b.tsx`` and ``a/b.tsx`` give ``/a/b``,
    ``index.tsx`` gives ``/``, and ``reports/index.tsx`` or ``reports.index.tsx``
    give ``/reports/``. ``posts/route.tsx`` and ``posts.lazy.tsx`` share the
    ``/posts`` id. Return None for the ``__root`` file, generated trees,
    ``-``-prefixed (ignored) files and directories, files outside *routes_dir*,
    and names this mapping does not cover, such as ``(group)`` directories.
    """
    if path.suffix not in ROUTE_SUFFIXES:
        return None
    try:
        relative = path.relative_to(routes_dir).with_suffix("")
    except ValueError:
        return None
    parts = [segment for part in relative.parts for segment in part.split(".")]
    if parts[-1] == "lazy" and len(parts) > 1:
        parts = parts[:-1]
    if parts[-1] == "route" and len(parts) > 1:
        parts = parts[:-1]
    if parts == ["__root"] or parts[-1] == "gen":
        return None
    if not all(_SEGMENT_RE.fullmatch(part) and not part.startswith("-") for part in parts):
        return None
    if parts[-1] == "index":
        return "/" + "/".join(parts[:-1]) + ("/" if len(parts) > 1 else "")
    return "/" + "/".join(parts)


def _tanstack_url(route_id: str) -> str:
    """Drop pathless (``_x``) and group segments; ``posts_`` un-nests to ``posts``."""
    segments = [
        segment.removesuffix("_")
        for segment in route_id.strip("/").split("/")
        if segment and not segment.startswith("_") and not segment.startswith("(")
    ]
    return "/" + "/".join(segments)


def _tanstack_kind(route_id: str) -> str:
    last = route_id.rstrip("/").rsplit("/", 1)[-1]
    if route_id.endswith("/"):
        return "index"
    if last.startswith("_"):
        return "layout"
    if last == "$":
        return "splat"
    return "page"


def tanstack_routes(routes_dir: Path) -> list[UiRoute]:
    """Return the file routes under *routes_dir* that define a route."""
    routes: list[UiRoute] = []
    for path in sorted(routes_dir.rglob("*")):
        if path.suffix not in ROUTE_SUFFIXES or not path.is_file():
            continue
        relative = path.relative_to(routes_dir)
        if "node_modules" in relative.parts or ".gen." in path.name:
            continue
        if any(part.startswith("-") for part in relative.parts):
            continue
        match = _FILE_ROUTE_RE.search(path.read_text(encoding="utf-8", errors="replace"))
        if match is None:
            continue
        route_id = tanstack_route_id(routes_dir, path) or match.group(2)
        if not route_id:
            continue
        routes.append(
            UiRoute(
                router="tanstack",
                path=_tanstack_url(route_id),
                file=path,
                kind=_tanstack_kind(route_id),
                route_id=route_id,
            )
        )
    return routes


def _opening_tag(text: str, start: int) -> tuple[str, list[str], int, bool]:
    """Scan a tag opened before *start*.

    Return the top-level attribute text with each ``{...}`` value replaced by
    ``{#n}``, the brace contents, the end offset, and whether it self-closes.
    """
    depth = 0
    quote = ""
    top: list[str] = []
    values: list[str] = []
    value_start = start
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            top.append(char)
            if char == quote:
                quote = ""
        elif char == "{":
            if depth == 0:
                value_start = index + 1
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                top.append(f"{{#{len(values)}}}")
                values.append(text[value_start:index])
        elif depth == 0:
            if char == ">":
                attrs = "".join(top)
                return attrs, values, index + 1, attrs.rstrip().endswith("/")
            if char in "\"'":
                quote = char
            top.append(char)
    return "".join(top), values, len(text), True


def _join(parent: str, child: str) -> str:
    combined = child if child.startswith("/") else f"{parent.rstrip('/')}/{child}"
    return re.sub(r"/+", "/", combined).rstrip("/") or "/"


def _static_path(attrs: str, values: list[str]) -> tuple[bool, str | None]:
    """Return (has path attribute, literal path or None when not static)."""
    match = _PATH_ATTR_RE.search(attrs)
    if match is None:
        return False, None
    if match.group(1):
        return True, match.group(2)
    if match.group(3) is None:
        return True, None
    literal = _STRING_EXPR_RE.fullmatch(values[int(match.group(3))])
    if literal is None or (literal.group(1) == "`" and "${" in literal.group(2)):
        return True, None
    return True, literal.group(2)


def _element(attrs: str, values: list[str]) -> str | None:
    match = _ELEMENT_RE.search(attrs)
    component = _COMPONENT_RE.match(values[int(match.group(1))]) if match else None
    return component.group(1) if component else None


def _is_index(attrs: str, values: list[str]) -> bool:
    match = _INDEX_RE.search(attrs)
    if match is None:
        return False
    return match.group(1) is None or values[int(match.group(1))].strip() != "false"


def react_router_routes(entry: Path) -> list[UiRoute]:
    """Return the static JSX ``<Route>`` paths declared in *entry*."""
    text = entry.read_text(encoding="utf-8", errors="replace")
    text = _LINE_COMMENT_RE.sub("", _BLOCK_COMMENT_RE.sub("", text))
    # Each frame: (resolved URL or None when unresolvable, element, layouts above it).
    stack: list[tuple[str | None, str | None, tuple[str, ...]]] = []
    routes: list[UiRoute] = []
    position = 0
    for token in _JSX_ROUTE_TOKEN_RE.finditer(text):
        if token.start() < position:
            continue
        if token.group().startswith("</"):
            if stack:
                stack.pop()
            continue
        attrs, values, position, self_closing = _opening_tag(text, token.end())
        parent_url, parent_element, parent_layouts = stack[-1] if stack else ("/", None, ())
        layouts = (*parent_layouts, parent_element) if parent_element else parent_layouts
        has_path, literal = _static_path(attrs, values)
        element = _element(attrs, values)
        is_index = not has_path and _is_index(attrs, values)
        url: str | None = parent_url
        if parent_url is not None and has_path:
            url = _join(parent_url, literal) if literal is not None else None
        if url is not None and (literal is not None or is_index):
            if is_index:
                kind = "index"
            elif url.endswith("*"):
                kind = "splat"
            else:
                kind = "page" if self_closing else "layout"
            routes.append(
                UiRoute(
                    router="react-router",
                    path=url,
                    file=entry,
                    kind=kind,
                    element=element,
                    layouts=layouts,
                )
            )
        if not self_closing:
            stack.append((url, element, layouts))
    return routes


def find_ui_routes(layout: FrontendLayout) -> list[UiRoute]:
    """Return the UI routes of the router *layout* detected; [] when unknown."""
    if layout.router == "tanstack" and layout.routes_dir is not None:
        return tanstack_routes(layout.routes_dir)
    if layout.router == "react-router" and layout.app_entry is not None:
        return react_router_routes(layout.app_entry)
    if layout.router == "nextjs" and layout.app_dir is not None:
        pages = [r for r in parse_nextjs_routes(layout.app_dir) if r.route_type == "page"]
        return [
            UiRoute(router="nextjs", path=route.path, file=route.file)
            for route in sorted(pages, key=lambda r: r.file)
        ]
    return []
