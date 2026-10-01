"""Locate where a React Router app declares its routes, and read route objects.

Two declaration styles are supported:

- ``jsx``: one module renders ``<Routes>`` with literal ``<Route>`` elements.
- ``data``: exactly one ``createBrowserRouter`` / ``createHashRouter`` /
  ``createMemoryRouter`` / ``useRoutes`` call whose argument is an array
  literal, a ``const`` array in the same module, or a ``const`` array imported
  by name from a relative or ``@/`` module.

Anything else (both styles at once, several data routers, computed route
arrays, ``createRoutesFromElements``) is reported as an issue, never guessed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from mattstack.parsers.js_literals import (
    JsArray,
    JsObject,
    LiteralError,
    parse_array,
    skip_space,
    string_value,
)

SOURCE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx")
TEST_PARTS = frozenset({"node_modules", "test", "tests", "__tests__", "__mocks__"})
DATA_CALL_RE = re.compile(
    r"(?<![\w$.])(createBrowserRouter|createHashRouter|createMemoryRouter|useRoutes)\s*\("
)
FROM_ELEMENTS_RE = re.compile(r"(?<![\w$.])createRoutesFrom(?:Elements|Children)\b")
ROUTES_JSX_RE = re.compile(r"<Routes\b")
_COMMENT_RE = re.compile(r"/\*.*?\*/|(?<![:\\])//[^\n]*", re.S)
_ELEMENT_NAME_RE = re.compile(r"<\s*([A-Za-z_$][\w$.]*)")
_LAZY_RE = re.compile(r"""import\(\s*(['"])([^'"]+)\1\s*\)""")
_IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")


class RouteShapeError(ValueError):
    """The route declarations use a shape that cannot be read or edited safely."""


@dataclass(frozen=True)
class RouteSource:
    style: str  # "jsx" | "data"
    entry: Path  # module whose text holds the route tree
    array_name: str | None = None  # const holding the routes; None for an inline argument
    call: str | None = None  # createBrowserRouter, useRoutes, ... for the data style


@dataclass
class ObjectRoute:
    obj: JsObject
    url: str | None  # absolute URL; None for a pathless layout route
    prefix: str  # URL prefix inherited by children
    element: str | None  # element tag or Component identifier
    lazy_spec: str | None  # module a `lazy: () => import(...)` route loads
    parent: int | None
    protected: bool  # inside a ProtectedRoute element group
    index: bool
    children: JsArray | None


def _blank_comments(text: str) -> str:
    return _COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), text)


def _sources(src_dir: Path) -> list[Path]:
    files = []
    for path in sorted(src_dir.rglob("*")):
        if path.suffix not in SOURCE_SUFFIXES or not path.is_file():
            continue
        if TEST_PARTS.intersection(path.relative_to(src_dir).parts):
            continue
        if re.search(r"\.(test|spec)\.", path.name) or ".gen." in path.name:
            continue
        files.append(path)
    return files


def _resolve_module(spec: str, from_file: Path, alias_root: Path | None) -> Path | None:
    if spec.startswith("@/") and alias_root is not None:
        base = alias_root / spec[2:]
    elif spec.startswith("."):
        base = Path(os.path.normpath(from_file.parent / spec))
    else:
        return None
    candidates = [base] if base.suffix in SOURCE_SUFFIXES else []
    candidates += [base.with_name(base.name + s) for s in SOURCE_SUFFIXES]
    candidates += [base / f"index{s}" for s in SOURCE_SUFFIXES]
    return next((c for c in candidates if c.is_file()), None)


def _const_array_re(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![\w$.])(?:export\s+)?(?:const|let|var)\s+{re.escape(name)}\s*(?::[^=\n]+)?=\s*\["
    )


def _data_source(
    path: Path, text: str, call: re.Match[str], alias_root: Path | None
) -> tuple[RouteSource | None, str | None]:
    start = skip_space(text, call.end())
    where = f"{path.name}: {call.group(1)}()"
    if text.startswith("[", start):
        return RouteSource("data", path, None, call.group(1)), None
    ident = _IDENT_RE.match(text, start)
    after = skip_space(text, ident.end()) if ident else start
    if ident is None or text[after] not in ",)":
        return None, f"{where} receives a computed route list; register the page by hand."
    name = ident.group()
    if _const_array_re(name).search(text):
        return RouteSource("data", path, name, call.group(1)), None
    imported = re.search(
        rf"""import\s*\{{[^}}]*?\b(?:([\w$]+)\s+as\s+)?{re.escape(name)}\b[^}}]*\}}\s*from\s*"""
        r"""(['"])([^'"]+)\2""",
        text,
    )
    if imported is None:
        return None, f"{where} uses {name}, which is not a const array literal or named import."
    module = _resolve_module(imported.group(3), path, alias_root)
    original = imported.group(1) or name
    if module is None:
        return None, f"{where} imports {name} from {imported.group(3)}, which cannot be resolved."
    module_text = module.read_text(encoding="utf-8", errors="replace")
    if not _const_array_re(original).search(_blank_comments(module_text)):
        return None, f"{module.name} does not declare `const {original} = [...]`."
    return RouteSource("data", module, original, call.group(1)), None


def locate_react_router(
    src_dir: Path, alias_root: Path | None = None
) -> tuple[RouteSource | None, str | None]:
    """Return (route source, issue). Both are None when no routes are declared."""
    jsx: list[Path] = []
    calls: list[tuple[Path, str, re.Match[str]]] = []
    for path in _sources(src_dir):
        text = _blank_comments(path.read_text(encoding="utf-8", errors="replace"))
        if FROM_ELEMENTS_RE.search(text):
            return None, (
                f"{path.relative_to(src_dir)} builds routes with createRoutesFromElements; "
                "register the page by hand."
            )
        if ROUTES_JSX_RE.search(text):
            jsx.append(path)
        calls.extend((path, text, m) for m in DATA_CALL_RE.finditer(text))
    if calls and jsx:
        return None, (
            f"{calls[0][0].relative_to(src_dir)} calls {calls[0][2].group(1)}() and "
            f"{jsx[0].relative_to(src_dir)} renders <Routes>; register the page by hand."
        )
    if len(calls) > 1:
        listed = ", ".join(f"{p.relative_to(src_dir)}:{m.group(1)}" for p, _, m in calls)
        return None, f"Several route declarations ({listed}); register the page by hand."
    if calls:
        path, text, call = calls[0]
        return _data_source(path, text, call, alias_root)
    app = [p for p in jsx if p.parent == src_dir and p.stem == "App"]
    if app or len(jsx) == 1:
        return RouteSource("jsx", (app or jsx)[0]), None
    if jsx:
        listed = ", ".join(str(p.relative_to(src_dir)) for p in jsx)
        return None, f"<Routes> is rendered in several modules ({listed}); register by hand."
    return None, None


def route_array_start(text: str, source: RouteSource) -> int:
    """Return the offset of the `[` that opens the route array of *source*."""
    blanked = _blank_comments(text)
    if source.array_name is not None:
        match = _const_array_re(source.array_name).search(blanked)
        if match is None:
            raise RouteShapeError(f"{source.entry.name} no longer declares {source.array_name}.")
        return match.end() - 1
    calls = list(DATA_CALL_RE.finditer(blanked))
    if len(calls) != 1:
        raise RouteShapeError(f"{source.entry.name} has {len(calls)} router calls; expected 1.")
    return skip_space(blanked, calls[0].end())


def _join(prefix: str, path: str) -> str:
    if path.startswith("/"):
        return path
    return (prefix.rstrip("/") + "/" + path) if path else (prefix or "/")


def _route(
    text: str, obj: JsObject, parent: ObjectRoute | None, index_of: int | None
) -> ObjectRoute:
    if obj.spread or obj.computed_key or obj.duplicate_key:
        raise RouteShapeError("a route object spreads, computes, or repeats keys")
    props = obj.props
    for key in ("path", "index", "element", "Component", "lazy", "children"):
        if key in props and props[key].shorthand:
            raise RouteShapeError(f"a route object uses shorthand `{key}`")
    prefix = parent.prefix if parent else ""
    path: str | None = None
    if "path" in props:
        path = string_value(props["path"].value)
        if path is None or "${" in props["path"].value:
            raise RouteShapeError(f"a route uses a computed path ({props['path'].value})")
    index_text = props["index"].value if "index" in props else "false"
    if index_text not in ("true", "false"):
        raise RouteShapeError(f"a route uses a computed index ({index_text})")
    is_index = index_text == "true"
    element: str | None = None
    if "element" in props:
        match = _ELEMENT_NAME_RE.match(props["element"].value)
        element = match.group(1) if match else None
    elif "Component" in props and _IDENT_RE.fullmatch(props["Component"].value):
        element = props["Component"].value
    lazy = _LAZY_RE.search(props["lazy"].value) if "lazy" in props else None
    children: JsArray | None = None
    if "children" in props:
        start, end = props["children"].value_start, props["children"].value_end
        children = parse_array(text, start) if text.startswith("[", start) else None
        if children is None or children.end != end:
            raise RouteShapeError(f"a route has computed children ({props['children'].value})")
    url = _join(prefix, path) if path is not None else (prefix or "/") if is_index else None
    return ObjectRoute(
        obj=obj,
        url=url,
        prefix=url if url is not None and path is not None else prefix,
        element=element,
        lazy_spec=lazy.group(2) if lazy else None,
        parent=index_of,
        protected=(parent.protected if parent else False) or element == "ProtectedRoute",
        index=is_index,
        children=children,
    )


def object_routes(text: str, start: int) -> tuple[JsArray, list[ObjectRoute]]:
    """Parse the route array at *start*; return it and every route, parents first."""
    routes: list[ObjectRoute] = []

    def walk(array: JsArray, parent: int | None) -> None:
        for element in array.elements:
            if element.obj is None:
                raise RouteShapeError(f"a route entry is not an object literal ({element.text})")
            above = routes[parent] if parent is not None else None
            route = _route(text, element.obj, above, parent)
            routes.append(route)
            if route.children is not None:
                walk(route.children, len(routes) - 1)

    try:
        root = parse_array(text, start)
        walk(root, None)
    except LiteralError as exc:
        raise RouteShapeError(f"the route array cannot be read ({exc})") from exc
    return root, routes
