"""Register generated pages in a React Router route tree.

JSX apps: one `<Routes>` block of literal `<Route>` elements, an optional
pathless `<Route element={<ProtectedRoute />}>` group, and a `path="*"`
splat. Data routers (`createBrowserRouter`/`useRoutes` route objects) are
edited by `react_router_objects`. Anything else (computed or mapped routes,
both styles at once, several declarations) is refused before any write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from mattstack.commands.codegen.backend_layout import GenerateError
from mattstack.commands.codegen.plan import FilePlan
from mattstack.commands.codegen.react_router_objects import register_object_route
from mattstack.commands.codegen.react_router_text import (
    has_import,
    import_insertion,
    indent_at,
    line_start,
    normalize_url,
)
from mattstack.commands.codegen.route_options import (
    DEFAULT_ROUTE_OPTIONS,
    RouteOptions,
    is_data_router,
)
from mattstack.parsers.frontend_layout import FrontendLayout, package_dependencies


class RouteGroup(StrEnum):
    """Where a React Router page is registered."""

    public = "public"
    protected = "protected"  # client-side redirect only; never authorization


PROTECTED_NOTICE = (
    "ProtectedRoute only redirects signed-out users in the browser. "
    "It is not authorization: the API must enforce access to the data."
)
URL_RE = re.compile(r"/|(?:/(?:[a-z0-9][a-z0-9-]*|:[A-Za-z_]\w*))+")
ROUTES_OPEN_RE = re.compile(r"<Routes\b[^>]*>")
ROUTES_CLOSE_RE = re.compile(r"</Routes\s*>")
# A `<Route ...>` opener or self-closing tag (attribute values may hold JSX), or `</Route>`.
ROUTE_TAG_RE = re.compile(
    r"<Route\b((?:[^>{}\"']|\"[^\"]*\"|'[^']*'|\{(?:[^{}]|\{[^{}]*\})*\})*)>|</Route\s*>"
)
JSX_COMMENT_RE = re.compile(r"\{\s*/\*.*?\*/\s*\}", re.S)
PATH_ATTR_RE = re.compile(r"(?<![\w-])path\s*=")
PATH_LITERAL_RE = re.compile(
    r"(?<![\w-])path\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|\{\s*([\"'`])([^\"'`{}$]*)\3\s*\})"
)
INDEX_ATTR_RE = re.compile(r"(?<![\w-])index(?:\s*=\s*\{\s*true\s*\})?(?=[\s/]|$)")
ELEMENT_RE = re.compile(r"(?<![\w-])element\s*=\s*\{\s*<([A-Za-z_$][\w$.]*)")


@dataclass
class _Route:
    start: int
    end: int  # end of the opening or self-closing tag
    url: str | None  # absolute URL, or None for a pathless layout route
    prefix: str  # URL prefix inherited by children
    element: str | None
    parent: int | None
    self_closing: bool
    protected: bool  # inside a ProtectedRoute group
    close_start: int | None = None
    children: list[int] = field(default_factory=list)


def _join(prefix: str, path: str) -> str:
    if path.startswith("/"):
        return path
    return (prefix.rstrip("/") + "/" + path) if path else (prefix or "/")


def _parse_routes(text: str, start: int, stop: int) -> list[_Route]:
    routes: list[_Route] = []
    stack: list[int] = []
    pos = start
    leftover: list[str] = []
    for match in ROUTE_TAG_RE.finditer(text, start, stop):
        leftover.append(text[pos : match.start()])
        pos = match.end()
        if match.group(1) is None:  # </Route>
            if not stack:
                raise GenerateError("App routes have an unmatched </Route>.")
            routes[stack.pop()].close_start = match.start()
            continue
        attrs = match.group(1)
        parent = stack[-1] if stack else None
        prefix = routes[parent].prefix if parent is not None else ""
        protected = parent is not None and routes[parent].protected
        if re.search(r"\{\s*\.\.\.", attrs):
            raise GenerateError("App routes spread props into <Route>; register the page by hand.")
        literal = PATH_LITERAL_RE.search(attrs)
        if PATH_ATTR_RE.search(attrs) and literal is None:
            raise GenerateError("App routes use a computed path; register the page by hand.")
        element = ELEMENT_RE.search(attrs)
        path: str | None = None
        if literal is not None:
            path = next(g for g in literal.group(1, 2, 4) if g is not None)
        if path is not None:
            url: str | None = _join(prefix, path)
        elif INDEX_ATTR_RE.search(attrs):
            url = prefix or "/"
        else:
            url = None
        name = element.group(1) if element else None
        route = _Route(
            start=match.start(),
            end=match.end(),
            url=url,
            prefix=url if url is not None and path is not None else prefix,
            element=name,
            parent=parent,
            self_closing=attrs.rstrip().endswith("/"),
            protected=protected or name == "ProtectedRoute",
        )
        if parent is not None:
            routes[parent].children.append(len(routes))
        routes.append(route)
        if not route.self_closing:
            stack.append(len(routes) - 1)
    leftover.append(text[pos:stop])
    if stack:
        raise GenerateError("App routes have an unclosed <Route>.")
    if "{" in JSX_COMMENT_RE.sub("", "".join(leftover)):
        raise GenerateError(
            "App routes contain JSX expressions (mapped or conditional routes); "
            "register the page by hand."
        )
    return routes


def _insertion_point(text: str, routes: list[_Route], group: RouteGroup) -> tuple[int, str]:
    """Return (offset, indent) for a new line inside the selected group."""
    if group is RouteGroup.protected:
        guards = [r for r in routes if r.element == "ProtectedRoute" and not r.self_closing]
        if len(guards) != 1:
            raise GenerateError(
                f"Expected one <Route element={{<ProtectedRoute />}}> group in App.tsx, "
                f"found {len(guards)}."
            )
        guard = guards[0]
        if guard.prefix or guard.url is not None:
            raise GenerateError("The ProtectedRoute group is nested under a path; not supported.")
        if guard.close_start is None:
            raise GenerateError("The ProtectedRoute group is not closed.")
        if guard.children:
            indent = indent_at(text, routes[guard.children[-1]].start)
        else:
            indent = indent_at(text, guard.start) + "  "
        return line_start(text, guard.close_start), indent

    splats = [r for r in routes if r.url is not None and r.url.endswith("*") and not r.protected]
    if len(splats) != 1:
        raise GenerateError(
            f'Expected one public <Route path="*"> in App.tsx to anchor public routes, '
            f"found {len(splats)}."
        )
    splat = splats[0]
    if splat.parent is not None and routes[splat.parent].prefix:
        raise GenerateError("The public routes are nested under a path; not supported.")
    if splat.parent is not None:
        siblings = [routes[i] for i in routes[splat.parent].children]
    else:
        siblings = [r for r in routes if r.parent is None]
    leaves = [
        r
        for r in siblings
        if r.self_closing and r.url is not None and r.start < splat.start and not r.protected
    ]
    if leaves:
        last = max(leaves, key=lambda r: r.end)
        line_end = text.find("\n", last.end)
        return (len(text) if line_end == -1 else line_end + 1), indent_at(text, last.start)
    offset = line_start(text, splat.start)
    while offset > 0:  # keep a `{/* 404 */}` comment attached to the splat
        previous = line_start(text, offset - 1)
        if not JSX_COMMENT_RE.fullmatch(text[previous : offset - 1].strip()):
            break
        offset = previous
    return offset, indent_at(text, splat.start)


def register_route(
    text: str,
    url: str,
    component: str,
    spec: str,
    group: RouteGroup,
    *,
    replace_existing: bool = False,
    module: str = "App.tsx",
) -> str:
    """Return *text* with `<Route path=url element={<component />} />` added in *group*.

    An existing route at *url* is refused, except that *replace_existing*
    (`--force`) accepts one identical registration (same component, import,
    and group) and returns *text* unchanged.
    """
    opens, closes = list(ROUTES_OPEN_RE.finditer(text)), list(ROUTES_CLOSE_RE.finditer(text))
    if len(opens) != 1 or len(closes) != 1:
        raise GenerateError(
            f"Expected exactly one <Routes> block in {module}, found {len(opens)}; "
            "register the page by hand."
        )
    if re.search(r"\{\s*\.\.\.", opens[0].group()):
        raise GenerateError(f"{module} spreads props into <Routes>; register the page by hand.")
    block = opens[0]
    routes = _parse_routes(text, block.end(), closes[0].start())
    target = normalize_url(url)
    existing = [
        r
        for r in routes
        if r.url is not None and not r.url.endswith("*") and normalize_url(r.url) == target
    ]
    if existing:
        route = existing[0]
        identical = (
            len(existing) == 1
            and route.self_closing
            and route.element == component
            and route.protected == (group is RouteGroup.protected)
            and has_import(text, component, spec)
        )
        if replace_existing and identical:
            return text
        raise GenerateError(f"{module} already routes {url}; pick another page name.")

    offset, indent = _insertion_point(text, routes, group)
    import_edit = import_insertion(text, component, spec, module=module)
    quote = "'" if re.search(r"(?<![\w-])path\s*=\s*'", text) else '"'
    text = (
        text[:offset]
        + f"{indent}<Route path={quote}{url}{quote} element={{<{component} />}} />\n"
        + text[offset:]
    )
    if import_edit is not None:
        at, line = import_edit
        if at > offset:
            raise GenerateError(f"{module} imports follow its routes; register the page by hand.")
        text = text[:at] + line + text[at:]
    return text


def react_router_package(layout: FrontendLayout) -> str:
    """Return the package the app imports React Router from."""
    deps = package_dependencies(layout.frontend_dir)
    return "react-router-dom" if "react-router-dom" in deps else "react-router"


def check_react_router_url(url: str) -> None:
    if not URL_RE.fullmatch(url):
        raise GenerateError(
            f"React Router path {url!r} is not supported. Use an absolute path of "
            "lowercase-kebab segments and :params, e.g. /reports/:reportId."
        )


def plan_react_router_page(
    plan: FilePlan,
    layout: FrontendLayout,
    page_file: Path,
    content: str,
    url: str,
    group: RouteGroup,
    *,
    replace_existing: bool = False,
    options: RouteOptions = DEFAULT_ROUTE_OPTIONS,
) -> None:
    """Create *page_file* and register it at *url* in the app's route tree.

    JSX `<Routes>` and data-router route objects are both edited in place;
    every check runs before the plan changes. With `options.error`, *content*
    must export `<component>Error` (see `render_default_page`). *replace_existing*
    (`--force`) keeps an identical existing registration so the page file can
    be regenerated; it never accepts a different route.
    """
    check_react_router_url(url)
    if layout.router_issue:
        raise GenerateError(layout.router_issue)
    source = layout.route_source
    if layout.pages_dir is None or source is None:
        raise GenerateError(
            "React Router generation needs src/pages and either a JSX <Routes> block or one "
            "createBrowserRouter/useRoutes route array under src/."
        )
    component = page_file.stem
    if options.error and f"export function {component}Error(" not in content:
        raise GenerateError(f"--error needs {page_file.name} to export {component}Error.")
    entry = source.entry
    current = plan.updates.get(entry) or entry.read_text(encoding="utf-8")
    spec = layout.import_path(entry, page_file)
    if source.style == "data":
        updated = register_object_route(
            current,
            source,
            url,
            component,
            spec,
            protected=group is RouteGroup.protected,
            replace_existing=replace_existing,
            lazy=options.lazy and is_data_router(layout),
            error=options.error,
        )
    else:
        updated = register_route(
            current,
            url,
            component,
            spec,
            group,
            replace_existing=replace_existing,
            module=entry.name,
        )
    plan.create(page_file, content)
    if updated != current:
        plan.update(entry, updated)
