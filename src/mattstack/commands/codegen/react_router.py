"""Register generated pages in a React Router `<Routes>` tree in `App.tsx`.

Only the boilerplate shape is edited: one JSX `<Routes>` block of literal
`<Route>` elements, an optional pathless `<Route element={<ProtectedRoute />}>`
group, and a `path="*"` splat. Anything else (data routers, `useRoutes`,
lazy or mapped routes, several `<Routes>`) is refused before any write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from mattstack.commands.codegen.backend_layout import GenerateError
from mattstack.commands.codegen.plan import FilePlan
from mattstack.parsers.frontend_layout import FrontendLayout


class RouteGroup(StrEnum):
    """Where a React Router page is registered."""

    public = "public"
    protected = "protected"  # client-side redirect only; never authorization


PROTECTED_NOTICE = (
    "ProtectedRoute only redirects signed-out users in the browser. "
    "It is not authorization: the API must enforce access to the data."
)
UNSUPPORTED_ROUTER_RE = re.compile(
    r"\b(?:createBrowserRouter|createHashRouter|createMemoryRouter|RouterProvider|useRoutes)\b"
)
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
IMPORT_RE = re.compile(r"^import\b[\s\S]*?(['\"])[^'\"\n]+\1;?[ \t]*$", re.M)
SOURCE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx")
TEST_PARTS = frozenset({"node_modules", "test", "tests", "__tests__", "__mocks__"})


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


def _normalize(url: str) -> str:
    """React Router matches case-insensitively and ignores a trailing slash."""
    return (url.rstrip("/") or "/").lower()


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


def _line_start(text: str, index: int) -> int:
    return text.rfind("\n", 0, index) + 1


def _indent(text: str, index: int) -> str:
    line = text[_line_start(text, index) :]
    return line[: len(line) - len(line.lstrip(" \t"))]


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
            indent = _indent(text, routes[guard.children[-1]].start)
        else:
            indent = _indent(text, guard.start) + "  "
        return _line_start(text, guard.close_start), indent

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
        return (len(text) if line_end == -1 else line_end + 1), _indent(text, last.start)
    offset = _line_start(text, splat.start)
    while offset > 0:  # keep a `{/* 404 */}` comment attached to the splat
        previous = _line_start(text, offset - 1)
        if not JSX_COMMENT_RE.fullmatch(text[previous : offset - 1].strip()):
            break
        offset = previous
    return offset, _indent(text, splat.start)


def _imports(text: str, component: str, spec: str) -> bool:
    pattern = rf"^import\s+{re.escape(component)}\s+from\s+(['\"]){re.escape(spec)}\1"
    return re.search(pattern, text, re.M) is not None


def _import_insertion(text: str, component: str, spec: str) -> tuple[int, str] | None:
    """Return (offset, text) adding a default import of *spec*, or None if present."""
    if _imports(text, component, spec):
        return None
    if re.search(rf"(?<![\w$.]){re.escape(component)}(?![\w$])", text):
        raise GenerateError(
            f"App.tsx already uses the name {component}; rename the page or register it by hand."
        )
    imports = list(IMPORT_RE.finditer(text))
    if not imports:
        raise GenerateError("App.tsx has no import block to extend.")
    pages = [m for m in imports if "/pages/" in m.group(0)]
    anchor = (pages or imports)[-1]
    quote = anchor.group(1)
    semi = ";" if anchor.group(0).rstrip().endswith(";") else ""
    return anchor.end(), f"\nimport {component} from {quote}{spec}{quote}{semi}"


def register_route(
    text: str,
    url: str,
    component: str,
    spec: str,
    group: RouteGroup,
    *,
    replace_existing: bool = False,
) -> str:
    """Return *text* with `<Route path=url element={<component />} />` added in *group*.

    An existing route at *url* is refused, except that *replace_existing*
    (`--force`) accepts one identical registration (same component, import,
    and group) and returns *text* unchanged.
    """
    if UNSUPPORTED_ROUTER_RE.search(text):
        raise GenerateError("App.tsx uses a data router or useRoutes; register the page by hand.")
    opens, closes = list(ROUTES_OPEN_RE.finditer(text)), list(ROUTES_CLOSE_RE.finditer(text))
    if len(opens) != 1 or len(closes) != 1:
        raise GenerateError(
            f"Expected exactly one <Routes> block in App.tsx, found {len(opens)}; "
            "register the page by hand."
        )
    if re.search(r"\{\s*\.\.\.", opens[0].group()):
        raise GenerateError("App.tsx spreads props into <Routes>; register the page by hand.")
    block = opens[0]
    routes = _parse_routes(text, block.end(), closes[0].start())
    target = _normalize(url)
    existing = [
        r
        for r in routes
        if r.url is not None and not r.url.endswith("*") and _normalize(r.url) == target
    ]
    if existing:
        route = existing[0]
        identical = (
            len(existing) == 1
            and route.self_closing
            and route.element == component
            and route.protected == (group is RouteGroup.protected)
            and _imports(text, component, spec)
        )
        if replace_existing and identical:
            return text
        raise GenerateError(f"App.tsx already routes {url}; pick another page name.")

    offset, indent = _insertion_point(text, routes, group)
    import_edit = _import_insertion(text, component, spec)
    quote = "'" if re.search(r"(?<![\w-])path\s*=\s*'", text) else '"'
    text = (
        text[:offset]
        + f"{indent}<Route path={quote}{url}{quote} element={{<{component} />}} />\n"
        + text[offset:]
    )
    if import_edit is not None:
        at, line = import_edit
        if at > offset:
            raise GenerateError("App.tsx imports follow its routes; register the page by hand.")
        text = text[:at] + line + text[at:]
    return text


def _check_sources(src_dir: Path, app_entry: Path) -> None:
    """Refuse projects that declare routes outside JSX; test helpers do not count."""
    for path in sorted(src_dir.rglob("*")):
        if path.suffix not in SOURCE_SUFFIXES or not path.is_file():
            continue
        parts = path.relative_to(src_dir).parts
        if TEST_PARTS.intersection(parts) or re.search(r"\.(test|spec)\.", path.name):
            continue
        if UNSUPPORTED_ROUTER_RE.search(path.read_text(encoding="utf-8", errors="replace")):
            raise GenerateError(
                f"{path.relative_to(src_dir)} defines routes with a data router or useRoutes; "
                f"only JSX <Routes> in {app_entry.name} is supported."
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
) -> None:
    """Create *page_file* and register it at *url* in the app's `<Routes>`.

    *replace_existing* (`--force`) keeps an identical existing registration
    so the page file can be regenerated; it never accepts a different route.
    """
    if layout.pages_dir is None or layout.app_entry is None:
        raise GenerateError(
            "React Router generation needs src/pages and a JSX <Routes> block in src/App.tsx."
        )
    _check_sources(layout.src_dir, layout.app_entry)
    entry = layout.app_entry
    current = plan.updates.get(entry) or entry.read_text(encoding="utf-8")
    component = page_file.stem
    spec = layout.import_path(entry, page_file)
    updated = register_route(
        current, url, component, spec, group, replace_existing=replace_existing
    )
    plan.create(page_file, content)
    if updated != current:
        plan.update(entry, updated)
