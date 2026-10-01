"""Tests for the client-side UI route inventory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mattstack.parsers.frontend_layout import detect_frontend_layout
from mattstack.parsers.frontend_routes import (
    find_ui_routes,
    react_router_routes,
    tanstack_route_id,
    tanstack_routes,
)
from mattstack.parsers.tanstack_config import RouteNaming


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("index.tsx", "/"),
        ("reports/index.tsx", "/reports/"),
        ("reports.index.tsx", "/reports/"),
        ("reports.monthly.tsx", "/reports/monthly"),
        ("reports/monthly.tsx", "/reports/monthly"),
        ("posts/route.tsx", "/posts"),
        ("posts.lazy.tsx", "/posts"),
        ("posts/$postId.tsx", "/posts/$postId"),
        ("__root.tsx", None),
        ("-components/Card.tsx", None),
        ("styles.css", None),
        ("(app)/_authed/reports/$id.tsx", "/(app)/_authed/reports/$id"),
        ("(app)/_authed.tsx", "/(app)/_authed"),
        ("(app).tsx", None),  # the generator rejects route files named like a group
        ("script[.]js.tsx", "/script.js"),
        ("posts_.$postId.edit.tsx", "/posts_/$postId/edit"),
    ],
)
def test_tanstack_route_id(tmp_path: Path, relative: str, expected: str | None) -> None:
    assert tanstack_route_id(tmp_path, tmp_path / relative) == expected


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("home.tsx", "/"),
        ("reports/home.tsx", "/reports/"),
        ("posts/layout.tsx", "/posts"),
        ("posts/route.tsx", "/posts/route"),
        ("index.tsx", "/index"),
        ("_private/x.tsx", None),
        ("-x.tsx", "/-x"),
    ],
)
def test_tanstack_route_id_follows_configured_tokens(
    tmp_path: Path, relative: str, expected: str | None
) -> None:
    naming = RouteNaming(index_token="home", route_token="layout", ignore_prefix="_private")
    assert tanstack_route_id(tmp_path, tmp_path / relative, naming) == expected


def test_tanstack_routes_skip_components_and_correct_cast_ids(tmp_path: Path) -> None:
    routes_dir = tmp_path / "routes"
    (routes_dir / "settings").mkdir(parents=True)
    (routes_dir / "__root.tsx").write_text("export const Route = createRootRoute({})\n")
    (routes_dir / "settings" / "index.tsx").write_text(
        "export const Route = createFileRoute('/settings' as any)({ component: S })\n"
    )
    (routes_dir / "settings" / "ProfileTab.tsx").write_text("export function ProfileTab() {}\n")
    (routes_dir / "_auth.tsx").write_text("export const Route = createFileRoute('/_auth')({})\n")

    routes = {r.route_id: (r.path, r.kind) for r in tanstack_routes(routes_dir)}

    assert routes == {"/settings/": ("/settings", "index"), "/_auth": ("/", "layout")}


def test_react_router_nesting_wrappers_and_dynamic_paths(tmp_path: Path) -> None:
    entry = tmp_path / "App.tsx"
    entry.write_text(
        """
<Routes>
  {/* <Route path="/old" element={<Old />} /> */}
  <Route element={<Layout />}>
    <Route path="/" element={<HomePage />} />
    <Route element={<ProtectedRoute />}>
      <Route path="/users" element={<Users tab="index" path="/fake" />}>
        <Route index element={<UserList />} />
        <Route path=":id" element={<UserPage />} />
        <Route path={base} element={<Dynamic />}>
          <Route path="child" element={<Child />} />
        </Route>
      </Route>
    </Route>
    <Route path="*" element={<NotFoundPage />} />
  </Route>
</Routes>
"""
    )

    routes = [(r.kind, r.path, r.element, r.layouts) for r in react_router_routes(entry)]

    assert routes == [
        ("page", "/", "HomePage", ("Layout",)),
        ("layout", "/users", "Users", ("Layout", "ProtectedRoute")),
        ("index", "/users", "UserList", ("Layout", "ProtectedRoute", "Users")),
        ("page", "/users/:id", "UserPage", ("Layout", "ProtectedRoute", "Users")),
        ("splat", "/*", "NotFoundPage", ("Layout",)),
    ]


def test_react_router_layout_ignores_stale_route_tree(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react-router-dom": "^7"}, "devDependencies": {"vite": "^6"}})
    )
    src = tmp_path / "src"
    (src / "pages").mkdir(parents=True)
    (src / "routes").mkdir()
    (src / "routeTree.gen.ts").write_text("import { Route } from './routes/index'\n")
    (src / "App.tsx").write_text("<Routes><Route path='/' element={<HomePage />} /></Routes>\n")

    layout = detect_frontend_layout(tmp_path)

    assert layout.router == "react-router"
    assert layout.routes_dir is None
    assert layout.pages_dir == src.resolve() / "pages"
    assert layout.app_entry == src.resolve() / "App.tsx"


def _frontend(root: Path, deps: dict[str, str], files: dict[str, str]) -> Path:
    (root / "package.json").write_text(json.dumps({"dependencies": deps}))
    for relative, text in files.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(text)
    return root


def test_tanstack_inline_plugin_options_override_tsr_config(tmp_path: Path) -> None:
    root = _frontend(
        tmp_path,
        {"@tanstack/react-router": "1", "vite": "6"},
        {
            "tsr.config.json": '{"routesDirectory": "./src/old", "indexToken": "home"}',
            "vite.config.ts": (
                "import { tanstackRouter as router } from '@tanstack/router-plugin/vite'\n"
                "export default { plugins: [router({ routesDirectory: './app/pages' })] }\n"
            ),
            "app/pages/home.tsx": "export const Route = createFileRoute('/')({})\n",
            "app/pages/(app)/_authed/billing.tsx": (
                "export const Route = createFileRoute('/(app)/_authed/billing')({})\n"
            ),
        },
    )

    layout = detect_frontend_layout(root)

    assert layout.router_issue is None
    assert layout.routes_dir == root.resolve() / "app" / "pages"
    assert [(r.route_id, r.path, r.kind) for r in find_ui_routes(layout)] == [
        ("/(app)/_authed/billing", "/billing", "page"),
        ("/", "/", "index"),
    ]


@pytest.mark.parametrize(
    "plugins",
    [
        "tanstackRouter({ routesDirectory: dir })",
        "tanstackRouter({ ...shared })",
        "tanstackRouter(options)",
        "tanstackRouter(), tanstackRouter()",
        "tanstackRouter({ virtualRouteConfig: './routes.ts' })",
    ],
    ids=["computed-value", "spread", "computed-options", "two-calls", "virtual-routes"],
)
def test_tanstack_unreadable_plugin_options_are_reported(tmp_path: Path, plugins: str) -> None:
    root = _frontend(
        tmp_path,
        {"@tanstack/react-router": "1"},
        {
            "vite.config.ts": (
                "import { tanstackRouter } from '@tanstack/router-plugin/vite'\n"
                f"export default {{ plugins: [{plugins}] }}\n"
            ),
            "src/routes/index.tsx": "export const Route = createFileRoute('/')({})\n",
        },
    )

    issue = detect_frontend_layout(root).router_issue

    assert issue is not None and issue.startswith("vite.config.ts:")


ROUTES_MODULE = """\
import Layout from '@/components/Layout'

export const appRoutes: RouteObject[] = [
  {
    path: '/',
    element: <Layout title={"Don't"} />,
    children: [
      { index: true, element: <Home /> },
      { path: 'about', lazy: () => import('./pages/About') },
      {
        element: <ProtectedRoute />,
        children: [{ path: 'users/:id', Component: UserPage }],
      },
      { path: '*', element: <NotFound /> },
    ],
  },
]
"""


def test_data_router_routes_resolve_an_imported_route_module(tmp_path: Path) -> None:
    root = _frontend(
        tmp_path,
        {"react-router": "7"},
        {
            "tsconfig.json": '{"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}',
            "src/main.tsx": (
                "import { appRoutes as routes } from '@/routes'\n"
                "// createBrowserRouter(old)\n"
                "const router = createBrowserRouter(routes, { basename: '/app' })\n"
            ),
            "src/routes.tsx": ROUTES_MODULE,
        },
    )

    layout = detect_frontend_layout(root)

    assert layout.router_issue is None
    assert layout.app_entry == root.resolve() / "src" / "routes.tsx"
    assert [(r.kind, r.path, r.element, r.layouts) for r in find_ui_routes(layout)] == [
        ("layout", "/", "Layout", ()),
        ("index", "/", "Home", ("Layout",)),
        ("page", "/about", None, ("Layout",)),
        ("page", "/users/:id", "UserPage", ("Layout", "ProtectedRoute")),
        ("splat", "/*", "NotFound", ("Layout",)),
    ]


@pytest.mark.parametrize(
    ("files", "issue"),
    [
        (
            {"src/App.tsx": "<Routes />", "src/main.tsx": "createBrowserRouter([])"},
            "renders <Routes>",
        ),
        (
            {"src/router.tsx": "createBrowserRouter(createRoutesFromElements(<Route />))"},
            "createRoutesFromElements",
        ),
        ({"src/main.tsx": "createBrowserRouter(buildRoutes())"}, "computed route list"),
        ({"src/a.tsx": "useRoutes([])", "src/b.tsx": "useRoutes([])"}, "Several route"),
    ],
    ids=["jsx-and-data", "from-elements", "computed", "two-declarations"],
)
def test_ambiguous_react_router_declarations_are_reported(
    tmp_path: Path, files: dict[str, str], issue: str
) -> None:
    root = _frontend(tmp_path, {"react-router-dom": "7"}, files)

    layout = detect_frontend_layout(root)

    assert layout.route_source is None
    assert layout.router_issue is not None and issue in layout.router_issue
    assert find_ui_routes(layout) == []
