"""Plan TanStack Router file routes without breaking existing routes.

A new file can silently change the route tree: a flat `x.tsx` next to an
`x/` directory becomes the layout of every child, a layout without
`<Outlet />` hides the pages under it, and two files that resolve to the same
URL make the generator fail. Those cases are refused before anything is
planned. Paths follow the configured routesDirectory and index/route tokens.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from mattstack.commands.codegen.backend_layout import GenerateError
from mattstack.commands.codegen.plan import FilePlan
from mattstack.commands.codegen.route_options import DEFAULT_ROUTE_OPTIONS, RouteOptions
from mattstack.parsers.frontend_layout import FrontendLayout
from mattstack.parsers.frontend_routes import UiRoute, tanstack_route_id, tanstack_routes
from mattstack.parsers.react_router_source import SOURCE_SUFFIXES, TEST_PARTS
from mattstack.parsers.tanstack_config import RouteNaming

TANSTACK_NEXT_STEPS = (
    "Next: run `bun run dev` or `bun run build` to regenerate the route tree before you typecheck."
)
# One segment of a TanStack route path: (group), _pathless, $param, $ splat, or static.
_SEGMENT_RE = re.compile(r"\([a-z0-9-]+\)|_[A-Za-z][\w-]*|\$[A-Za-z_]\w*|\$|[a-z0-9][a-z0-9-]*")
_USE_STORE_RE = re.compile(r"^export\s+const\s+useStore\s*=\s*create\b", re.M)
_USE_AUTH_RE = re.compile(r"^export\s+(?:const\s+useAuth\s*=|function\s+useAuth\s*\()", re.M)
_QUERY_CONTEXT_RE = re.compile(r"\bqueryClient\s*:\s*QueryClient\b")
LOGIN_PATHS = ("/auth/login", "/login")


@dataclass(frozen=True)
class ClientAuth:
    """The app's own browser auth store, used by generated guards."""

    store_spec: str  # import of the module exporting zustand `useStore` with `isAuthenticated`
    login_path: str  # existing sign-in route the guard redirects to


@dataclass(frozen=True)
class TanStackTarget:
    file: Path
    route_id: str
    params: tuple[str, ...]  # dynamic parameter names, outermost first
    auth: ClientAuth | None  # set when the route is guarded


def _naming(layout: FrontendLayout) -> RouteNaming:
    return layout.tanstack.naming if layout.tanstack else RouteNaming()


def _is_layout(route: UiRoute, routes: list[UiRoute]) -> bool:
    own = route.route_id or ""
    if own.endswith("/"):
        return False  # index routes are leaves
    return any((r.route_id or "").startswith(own + "/") for r in routes if r is not route)


def _url_key(route_id: str) -> str:
    """URL pattern a leaf route id matches: no groups/pathless, params unnamed."""
    segments = [
        s.removesuffix("_")
        for s in route_id.strip("/").split("/")
        if s and not s.startswith(("_", "("))
    ]
    return "/" + "/".join("$param" if re.fullmatch(r"\$\w+", s) else s for s in segments)


def _tanstack_conflict(
    routes: list[UiRoute], routes_dir: Path, target: Path, route_id: str
) -> str | None:
    """Describe how *route_id* at *target* would clash with existing routes, if it would."""
    for route in routes:
        other = route.route_id
        if route.file == target or not other:
            continue
        rel = route.file.relative_to(routes_dir).as_posix()
        if other == route_id:
            return f"{rel} already defines route {route_id}."
        if not route_id.endswith("/") and other.startswith(route_id + "/"):
            return (
                f"{rel} is nested under {route_id}; a flat {target.name} would become its "
                "layout and hide it. Generate a section index instead."
            )
        is_parent_layout = (
            other != "/" and not other.endswith("/") and route_id.startswith(other + "/")
        )
        text = route.file.read_text(encoding="utf-8", errors="replace")
        if is_parent_layout:
            if "Outlet" not in text:
                return f"{rel} would be the layout of {route_id} but renders no <Outlet />."
            continue
        pathless = other.rstrip("/").rsplit("/", 1)[-1].startswith(("_", "("))
        same_url = _url_key(other) == _url_key(route_id)
        if same_url and not pathless and not _is_layout(route, routes):
            return f"{rel} ({other}) already renders the URL {_url_key(route_id)}."
    return None


def _segments(route: str) -> tuple[list[str], bool]:
    """Split a TanStack route path such as `/(app)/_authed/reports/$reportId`."""
    if not route.startswith("/"):
        raise GenerateError(f"Route {route!r} must start with '/', e.g. /reports or /reports/.")
    is_index = route.endswith("/")
    segments = [s for s in route.strip("/").split("/")]
    if segments == [""]:
        segments = []
    for segment in segments:
        if not _SEGMENT_RE.fullmatch(segment):
            raise GenerateError(
                f"Route segment {segment!r} is not supported. Use lowercase-kebab static "
                "segments, (group), _pathless, $param, or a final $ splat."
            )
    if not segments and not is_index:
        raise GenerateError("Route '/' is the root index; pass '/' with a trailing slash.")
    if segments and not is_index and segments[-1].startswith(("(", "_")):
        raise GenerateError(
            f"Route {route!r} ends in a group or pathless layout, which renders no page. "
            "Add a path segment, or end with '/' for an index page."
        )
    if "$" in segments[:-1] or (is_index and segments and segments[-1] == "$"):
        raise GenerateError("A $ splat must be the last segment of a page route.")
    return segments, is_index


def _store_module(layout: FrontendLayout) -> Path:
    matches = []
    for path in sorted(layout.src_dir.rglob("*")):
        if path.suffix not in SOURCE_SUFFIXES or not path.is_file():
            continue
        if TEST_PARTS.intersection(path.relative_to(layout.src_dir).parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _USE_STORE_RE.search(text) and _USE_AUTH_RE.search(text) and "isAuthenticated" in text:
            matches.append(path)
    if len(matches) != 1:
        found = ", ".join(str(p.relative_to(layout.src_dir)) for p in matches) or "none"
        raise GenerateError(
            "--guard reuses the app's auth store: one module exporting a zustand "
            f"`useStore` with `isAuthenticated` and `useAuth`. Found: {found}. "
            "Add the guard by hand with beforeLoad, or generate without --guard."
        )
    return matches[0]


def detect_client_auth(layout: FrontendLayout, routes: list[UiRoute], target: Path) -> ClientAuth:
    """Return the auth store and sign-in route a guard in *target* uses, or refuse."""
    store = _store_module(layout)
    logins = sorted({r.path for r in routes if r.path in LOGIN_PATHS and r.kind != "layout"})
    if len(logins) != 1:
        raise GenerateError(
            f"--guard redirects to the sign-in route; expected exactly one of "
            f"{', '.join(LOGIN_PATHS)} in the route tree, found {logins or 'none'}."
        )
    spec = layout.import_path(target, store)
    siblings = [store.parent.with_suffix(s) for s in SOURCE_SUFFIXES]
    if store.stem == "index" and not any(s.is_file() for s in siblings):
        spec = spec.removesuffix("/index")
    return ClientAuth(spec, logins[0])


def has_query_context(routes_dir: Path) -> bool:
    """True when `__root` declares a router context carrying the QueryClient."""
    for suffix in (".tsx", ".ts", ".jsx", ".js"):
        root = routes_dir / f"__root{suffix}"
        if root.is_file():
            text = root.read_text(encoding="utf-8", errors="replace")
            return "createRootRouteWithContext" in text and bool(_QUERY_CONTEXT_RE.search(text))
    return False


def render_pathless_layout(route_id: str) -> str:
    name = "".join(p.capitalize() for p in re.split(r"[^A-Za-z0-9]+", route_id) if p) + "Layout"
    return (
        'import { createFileRoute, Outlet } from "@tanstack/react-router";\n\n'
        f'export const Route = createFileRoute("{route_id}")({{\n'
        f"  component: {name},\n}});\n\n"
        f"function {name}() {{\n  return <Outlet />;\n}}\n"
    )


def plan_tanstack_page(
    plan: FilePlan,
    layout: FrontendLayout,
    route: str,
    render: Callable[[TanStackTarget], str],
    options: RouteOptions = DEFAULT_ROUTE_OPTIONS,
) -> TanStackTarget:
    """Validate *route* against the route tree, then plan its file and missing layouts.

    Every check runs before the first `plan.create`, so a refusal leaves the
    plan untouched. Missing `_pathless` layouts are created with `<Outlet />`;
    existing ones must already render one.
    """
    if layout.router_issue:
        raise GenerateError(layout.router_issue)
    if layout.routes_dir is None:
        where = layout.tanstack.routes_dir if layout.tanstack else "src/routes"
        raise GenerateError(f"TanStack routesDirectory {where} does not exist; create it first.")
    routes_dir, naming = layout.routes_dir, _naming(layout)
    segments, is_index = _segments(route)
    folder = routes_dir.joinpath(*segments) if is_index else routes_dir.joinpath(*segments[:-1])
    target = folder / (f"{naming.index_token}.tsx" if is_index else f"{segments[-1]}.tsx")
    routes = tanstack_routes(routes_dir, naming)
    layouts: list[tuple[Path, str]] = []
    for depth, segment in enumerate(segments[: None if is_index else -1]):
        if not segment.startswith("_"):
            continue
        layout_id = "/" + "/".join(segments[: depth + 1])
        if any(r.route_id == layout_id for r in routes):
            continue
        layout_file = routes_dir.joinpath(*segments[:depth], f"{segment}.tsx")
        if layout_file.exists():
            raise GenerateError(
                f"{layout_file.relative_to(routes_dir)} exists but defines no route "
                f"{layout_id}; fix or move it before generating under it."
            )
        layouts.append((layout_file, layout_id))
    route_id = tanstack_route_id(routes_dir, target, naming)
    rel = target.relative_to(routes_dir).as_posix()
    if route_id is None:
        raise GenerateError(f"{rel} is not a TanStack route file name.")
    conflict = _tanstack_conflict(routes, routes_dir, target, route_id)
    if conflict:
        raise GenerateError(f"Refusing to add {rel}: {conflict}")
    auth = detect_client_auth(layout, routes, target) if options.guard else None
    if options.pending and not has_query_context(routes_dir):
        raise GenerateError(
            "--pending prefetches the list in a route loader through the router context, "
            f"but {routes_dir.name}/__root does not declare `createRootRouteWithContext<"
            "{ queryClient: QueryClient }>()`. Add that context to __root and pass "
            "`context: { queryClient }` to createRouter, then rerun; or omit --pending."
        )
    params = tuple(s[1:] for s in segments if s.startswith("$") and len(s) > 1)
    resolved = TanStackTarget(target, route_id, params, auth)
    content = render(resolved)
    for layout_file, layout_id in layouts:
        plan.create(layout_file, render_pathless_layout(layout_id))
    plan.create(target, content)
    return resolved


def tanstack_route_for_dir(layout: FrontendLayout, directory: Path, segment: str) -> str:
    """Return the route path of page *segment* in *directory* (for `--path`)."""
    if layout.routes_dir is None:
        raise GenerateError("TanStack routesDirectory does not exist; create it first.")
    try:
        parts = directory.resolve().relative_to(layout.routes_dir).parts
    except ValueError as exc:
        raise GenerateError(
            f"--path {directory} is outside the TanStack routesDirectory {layout.routes_dir}; "
            "pass a directory under it, or use --route."
        ) from exc
    return "/" + "/".join([*parts, segment])
