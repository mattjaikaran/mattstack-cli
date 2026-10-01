"""Register generated pages in a data router's literal route objects.

Supported: the route array passed to `createBrowserRouter` (or
`createHashRouter`/`createMemoryRouter`/`useRoutes`) where every entry and
`children` list is an object literal with a literal `path`. Public pages go
before the one public `path: "*"` route, or into the single root layout when
there is no splat; protected pages go into the one route whose element is
`<ProtectedRoute />`. Spread, computed, or mapped routes are refused.
"""

from __future__ import annotations

import re

from mattstack.commands.codegen.backend_layout import GenerateError
from mattstack.commands.codegen.react_router_text import (
    has_import,
    import_insertion,
    indent_at,
    line_start,
    normalize_url,
)
from mattstack.parsers.js_literals import JsArray, scan_to
from mattstack.parsers.react_router_source import (
    ObjectRoute,
    RouteShapeError,
    RouteSource,
    object_routes,
    route_array_start,
)


def _route_entry(
    url: str, component: str, spec: str, quote: str, *, lazy: bool, error: bool, jsx: bool
) -> str:
    """Render a route object; `.ts`/`.js` modules get `Component` instead of JSX."""
    path = f"path: {quote}{url}{quote}"
    if lazy:
        props = "Component: m.default"
        if error:
            props += f", ErrorBoundary: m.{component}Error"
        load = f"import({quote}{spec}{quote}).then((m) => ({{ {props} }}))"
        return f"{{ {path}, lazy: () => {load} }}"
    if not jsx:
        boundary = f", ErrorBoundary: {component}Error" if error else ""
        return f"{{ {path}, Component: {component}{boundary} }}"
    boundary = f", errorElement: <{component}Error />" if error else ""
    return f"{{ {path}, element: <{component} />{boundary} }}"


def _own_line(text: str, start: int, module: str) -> None:
    if text[line_start(text, start) : start].strip():
        raise GenerateError(
            f"{module} writes several routes on one line; put one route object per line "
            "or register the page by hand."
        )


Edit = tuple[int, int, str]  # replace text[start:stop] with the string


def _append(text: str, array: JsArray, entry: str, module: str) -> Edit:
    """Return the edit appending *entry* to *array*."""
    if not array.elements:
        if text[array.start + 1 : array.end - 1].strip():
            raise GenerateError(f"{module} has comments in an empty route list; edit by hand.")
        outer = indent_at(text, array.start)
        return array.start + 1, array.end - 1, f"\n{outer}  {entry},\n{outer}"
    last = array.elements[-1]
    _own_line(text, last.start, module)
    indent = indent_at(text, last.start)
    if array.trailing_comma:
        comma = scan_to(text, last.end, ",]") + 1
        return comma, comma, f"\n{indent}{entry},"
    return last.end, last.end, f",\n{indent}{entry}"


def _before(text: str, route: ObjectRoute, entry: str, module: str) -> Edit:
    """Return the edit inserting *entry* on its own line above *route* and its comments."""
    _own_line(text, route.obj.start, module)
    offset = line_start(text, route.obj.start)
    while offset > 0:
        previous = line_start(text, offset - 1)
        if not re.fullmatch(r"\s*(//[^\n]*|/\*.*\*/)\s*", text[previous : offset - 1]):
            break
        offset = previous
    return offset, offset, f"{indent_at(text, route.obj.start)}{entry},\n"


def _edit(
    text: str, routes: list[ObjectRoute], root: JsArray, entry: str, protected: bool, module: str
) -> Edit:
    """Return the edit placing *entry* in the protected or public group."""
    if protected:
        guards = [r for r in routes if r.element == "ProtectedRoute" and r.children is not None]
        if len(guards) != 1 or guards[0].children is None:
            raise GenerateError(
                f"Expected one route with element <ProtectedRoute /> and children in {module}, "
                f"found {len(guards)}."
            )
        if guards[0].prefix not in ("", "/"):
            raise GenerateError("The ProtectedRoute group is nested under a path; not supported.")
        return _append(text, guards[0].children, entry, module)
    splats = [r for r in routes if r.url is not None and r.url.endswith("*") and not r.protected]
    if len(splats) > 1:
        raise GenerateError(f"{module} has {len(splats)} public splat routes; edit by hand.")
    if splats:
        splat = splats[0]
        parent = routes[splat.parent] if splat.parent is not None else None
        if parent is not None and parent.prefix not in ("", "/"):
            raise GenerateError("The public splat route is nested under a path; not supported.")
        return _before(text, splat, entry, module)
    layouts = [r for r in routes if r.parent is None and r.children is not None]
    if not layouts:
        return _append(text, root, entry, module)
    only = layouts[0]
    if len(layouts) == 1 and only.children and not only.protected and only.prefix in ("", "/"):
        return _append(text, only.children, entry, module)
    raise GenerateError(
        f'{module} has no public path: "*" route and {len(layouts)} top-level layouts; '
        "add a splat route to mark where public pages go, or register by hand."
    )


def register_object_route(
    text: str,
    source: RouteSource,
    url: str,
    component: str,
    spec: str,
    *,
    protected: bool,
    replace_existing: bool = False,
    lazy: bool = False,
    error: bool = False,
) -> str:
    """Return *text* with a route object for *url* added to the data router routes."""
    module = source.entry.name
    try:
        root, routes = object_routes(text, route_array_start(text, source))
    except RouteShapeError as exc:
        raise GenerateError(f"{module}: {exc}; register the page by hand.") from exc
    target = normalize_url(url)
    existing = [
        r
        for r in routes
        if r.url is not None and not r.url.endswith("*") and normalize_url(r.url) == target
    ]
    if existing:
        route = existing[0]
        same_target = (
            (route.lazy_spec == spec)
            if lazy
            else (route.element == component and has_import(text, component, spec))
        )
        identical = len(existing) == 1 and route.protected == protected and same_target
        if replace_existing and identical:
            return text
        raise GenerateError(f"{module} already routes {url}; pick another page name.")

    quote = "'" if re.search(r"(?<![\w$])path\s*:\s*'", text) else '"'
    jsx = source.entry.suffix in (".tsx", ".jsx")
    entry = _route_entry(url, component, spec, quote, lazy=lazy, error=error, jsx=jsx)
    start, stop, insertion = _edit(text, routes, root, entry, protected, module)
    import_edit = None
    if not lazy:
        named = (f"{component}Error",) if error else ()
        import_edit = import_insertion(text, component, spec, named, module=module)
    text = text[:start] + insertion + text[stop:]
    if import_edit is not None:
        at, line = import_edit
        if at > start:
            raise GenerateError(f"{module} imports follow its routes; register the page by hand.")
        text = text[:at] + line + text[at:]
    return text
