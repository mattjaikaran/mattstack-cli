"""Route planners: custom TanStack trees, data routers, Next.js groups, atomic refusal."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mattstack.commands.codegen.backend_layout import GenerateError
from mattstack.commands.codegen.nextjs_pages import next_group_segments, plan_nextjs_page
from mattstack.commands.codegen.plan import FilePlan
from mattstack.commands.codegen.react_basic import render_default_page, render_tanstack_page
from mattstack.commands.codegen.react_crud import render_list_page
from mattstack.commands.codegen.react_router import RouteGroup, plan_react_router_page
from mattstack.commands.codegen.route_options import RouteOptions, check_route_options
from mattstack.commands.codegen.tanstack_routes import plan_tanstack_page
from mattstack.parsers.frontend_layout import FrontendLayout, detect_frontend_layout

STORE = """\
export const useStore = create<AppStore>()(devtools(() => ({ isAuthenticated: false })));
export const useAuth = () => useStore(state => ({ isAuthenticated: state.isAuthenticated }));
"""
ROOT_WITH_CONTEXT = """\
interface RouterContext {
  queryClient: QueryClient
}
export const Route = createRootRouteWithContext<RouterContext>()({})
"""


def frontend(root: Path, deps: dict[str, str], files: dict[str, str]) -> FrontendLayout:
    (root / "package.json").write_text(json.dumps({"dependencies": deps}))
    (root / "tsconfig.json").write_text('{"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}')
    for relative, text in files.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(text)
    return detect_frontend_layout(root)


def tanstack(root: Path, **files: str) -> FrontendLayout:
    base = {
        "vite.config.ts": (
            "import { tanstackRouter } from '@tanstack/router-plugin/vite'\n"
            "export default { plugins: [tanstackRouter({ routesDirectory: './src/pages', "
            "indexToken: 'home' })] }\n"
        ),
        "src/pages/__root.tsx": ROOT_WITH_CONTEXT,
        "src/pages/home.tsx": "export const Route = createFileRoute('/')({})\n",
        "src/pages/auth/login.tsx": "export const Route = createFileRoute('/auth/login')({})\n",
        "src/lib/store/index.ts": STORE,
    }
    return frontend(root, {"@tanstack/react-router": "1", "vite": "6"}, {**base, **files})


def test_tanstack_page_in_group_and_new_pathless_layout_is_guarded(tmp_path: Path) -> None:
    layout = tanstack(tmp_path)
    plan = FilePlan(tmp_path)
    options = RouteOptions(guard=True, error=True)

    target = plan_tanstack_page(
        plan,
        layout,
        "/(app)/_authed/reports/$reportId",
        lambda t: render_tanstack_page(t, "Reports", options),
        options,
    )

    pages = tmp_path.resolve() / "src" / "pages"
    assert target.route_id == "/(app)/_authed/reports/$reportId"
    assert sorted(plan.creates) == [
        pages / "(app)" / "_authed" / "reports" / "$reportId.tsx",
        pages / "(app)" / "_authed.tsx",
    ]
    assert "<Outlet />" in plan.creates[pages / "(app)" / "_authed.tsx"]
    page = plan.creates[target.file]
    assert 'import { useStore } from "@/lib/store";' in page
    assert 'throw redirect({ to: "/auth/login" });' in page
    assert "const { reportId } = Route.useParams();" in page
    assert "errorComponent: ReportsPageError" in page


def test_tanstack_index_uses_the_configured_index_token(tmp_path: Path) -> None:
    layout = tanstack(tmp_path)
    plan = FilePlan(tmp_path)

    target = plan_tanstack_page(plan, layout, "/reports/", lambda t: t.route_id)

    assert target.file.name == "home.tsx"
    assert plan.creates == {target.file: "/reports/"}


def test_tanstack_crud_pending_prefetches_through_router_context(tmp_path: Path) -> None:
    layout = tanstack(tmp_path)
    plan = FilePlan(tmp_path)
    options = RouteOptions(pending=True)

    target = plan_tanstack_page(
        plan,
        layout,
        "/products/",
        lambda t: render_list_page("Product", "@/x", t, options, hooks_spec="@/hooks/p"),
        options,
    )

    page = plan.creates[target.file]
    assert "context.queryClient.ensureQueryData(ProductListQuery())" in page
    assert "pendingComponent: ProductsPagePending" in page


GROUP_ABOUT = {"src/pages/(site)/about.tsx": "createFileRoute('/(site)/about')"}
FLAT_SETTINGS = {"src/pages/settings.tsx": "createFileRoute('/settings')"}


@pytest.mark.parametrize(
    ("route", "options", "files", "message"),
    [
        pytest.param("/about", RouteOptions(), GROUP_ABOUT, "renders the URL", id="same-url"),
        pytest.param("/settings/", RouteOptions(), FLAT_SETTINGS, "no <Outlet", id="no-outlet"),
        pytest.param(
            "/x", RouteOptions(guard=True), {"src/lib/store/index.ts": ""}, "auth store", id="store"
        ),
        pytest.param(
            "/x", RouteOptions(guard=True), {"src/pages/auth/login.tsx": ""}, "sign-in", id="login"
        ),
        pytest.param(
            "/x/", RouteOptions(pending=True), {"src/pages/__root.tsx": ""}, "queryClient", id="ctx"
        ),
        pytest.param("/(app)/_authed", RouteOptions(), {}, "renders no page", id="pathless-end"),
        pytest.param("/Reports", RouteOptions(), {}, "not supported", id="bad-segment"),
    ],
)
def test_tanstack_refusals_plan_nothing(
    tmp_path: Path, route: str, options: RouteOptions, files: dict[str, str], message: str
) -> None:
    layout = tanstack(tmp_path, **files)
    plan = FilePlan(tmp_path)

    with pytest.raises(GenerateError, match=message.replace("(", r"\(").replace(")", r"\)")):
        plan_tanstack_page(plan, layout, route, lambda t: "page", options)

    assert plan.creates == {} and plan.updates == {}


ROUTES = """\
import Layout from '@/components/Layout'
import ProtectedRoute from '@/components/ProtectedRoute'
import Home from '@/pages/Home'

export const routes = [
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Home /> },
      {
        element: <ProtectedRoute />,
        children: [
          { path: 'dashboard', element: <Home /> },
        ],
      },
      // 404
      { path: '*', element: <Home /> },
    ],
  },
]
"""


def data_router(root: Path, routes: str = ROUTES) -> FrontendLayout:
    return frontend(
        root,
        {"react-router-dom": "7", "vite": "6"},
        {
            "src/pages/Home.tsx": "",
            "src/main.tsx": "import { routes } from './routes'\ncreateBrowserRouter(routes)\n",
            "src/routes.tsx": routes,
        },
    )


def test_data_router_registers_public_protected_lazy_and_error_routes(tmp_path: Path) -> None:
    layout = data_router(tmp_path)
    assert layout.app_entry is not None
    pages = tmp_path.resolve() / "src" / "pages"
    plan = FilePlan(tmp_path)
    reports = render_default_page("Reports", "react-router-dom")
    billing_page = render_default_page("Billing")

    plan_react_router_page(
        plan,
        layout,
        pages / "ReportsPage.tsx",
        reports,
        "/reports/:reportId",
        RouteGroup.public,
        options=RouteOptions(error=True),
    )
    plan_react_router_page(
        plan,
        layout,
        pages / "BillingPage.tsx",
        billing_page,
        "/billing",
        RouteGroup.protected,
        options=RouteOptions(lazy=True),
    )

    text = plan.updates[layout.app_entry]
    assert "import ReportsPage, { ReportsPageError } from '@/pages/ReportsPage'" in text
    public = text.index(
        "{ path: '/reports/:reportId', element: <ReportsPage />, "
        "errorElement: <ReportsPageError /> },"
    )
    assert public < text.index("// 404") < text.index("path: '*'")
    billing = text.index(
        "{ path: '/billing', lazy: () => import('@/pages/BillingPage')"
        ".then((m) => ({ Component: m.default })) },"
    )
    assert text.index("path: 'dashboard'") < billing < public
    assert "export function ReportsPageError()" in plan.creates[pages / "ReportsPage.tsx"]


def test_data_router_force_keeps_an_identical_registration(tmp_path: Path) -> None:
    layout = data_router(tmp_path)
    assert layout.app_entry is not None
    page = tmp_path.resolve() / "src" / "pages" / "AboutPage.tsx"
    plan = FilePlan(tmp_path)
    plan_react_router_page(plan, layout, page, "", "/about", RouteGroup.public)
    layout.app_entry.write_text(plan.updates[layout.app_entry])

    again = FilePlan(tmp_path)
    public, protected = RouteGroup.public, RouteGroup.protected
    plan_react_router_page(again, layout, page, "", "/about", public, replace_existing=True)
    assert again.updates == {}
    with pytest.raises(GenerateError, match="already routes /about"):
        plan_react_router_page(again, layout, page, "", "/about", protected, replace_existing=True)


@pytest.mark.parametrize(
    "change",
    [
        ("{ index: true, element: <Home /> },", "...extraRoutes,"),
        ("path: 'dashboard'", "path: base"),
        ("[\n          { path: 'dashboard', element: <Home /> },\n        ]", "flags.map(toRoute)"),
        ("{ index: true, element: <Home /> },", "{ index, element: <Home /> },"),
    ],
    ids=["spread", "computed-path", "mapped-children", "shorthand-index"],
)
def test_data_router_dynamic_routes_are_refused_without_changes(
    tmp_path: Path, change: tuple[str, str]
) -> None:
    layout = data_router(tmp_path, ROUTES.replace(*change))
    plan = FilePlan(tmp_path)

    with pytest.raises(GenerateError, match="register the page by hand"):
        plan_react_router_page(
            plan, layout, tmp_path / "src" / "pages" / "XPage.tsx", "", "/x", RouteGroup.public
        )

    assert plan.creates == {} and plan.updates == {}


@pytest.mark.parametrize(
    ("call", "options", "message"),
    [
        ("useRoutes(routes)", RouteOptions(error=True), "ignores errorElement"),
        ("useRoutes(routes)", RouteOptions(lazy=True), "ignores route `lazy`"),
        ("createBrowserRouter(routes)", RouteOptions(guard=True), "--route-group protected"),
        ("createBrowserRouter(routes)", RouteOptions(pending=True), "useNavigation"),
    ],
)
def test_router_flags_the_router_cannot_honor_are_refused(
    tmp_path: Path, call: str, options: RouteOptions, message: str
) -> None:
    layout = data_router(tmp_path)
    (tmp_path / "src" / "main.tsx").write_text(f"import {{ routes }} from './routes'\n{call}\n")

    with pytest.raises(GenerateError, match=message):
        check_route_options(detect_frontend_layout(tmp_path), options, has_loader=True)
    assert layout.app_entry is not None


def next_app(root: Path, *, root_layout: bool = True) -> FrontendLayout:
    files = {"app/products/page.tsx": "export default function P() {}\n"}
    if root_layout:
        files["app/layout.tsx"] = "export default function L() {}\n"
    return frontend(root, {"next": "15"}, files)


def test_next_route_group_places_the_page_without_changing_its_url(tmp_path: Path) -> None:
    layout = next_app(tmp_path)
    plan = FilePlan(tmp_path)

    page = plan_nextjs_page(plan, layout, [*next_group_segments("dashboard"), "orders"], "x")

    assert page == tmp_path.resolve() / "app" / "(dashboard)" / "orders" / "page.tsx"
    assert plan.creates == {page: "x"}


@pytest.mark.parametrize(
    ("root_layout", "segments", "message"),
    [
        (True, ["(dashboard)", "products"], "same URL /products"),
        (False, ["(dashboard)", "orders"], "no root layout"),
    ],
    ids=["url-collision", "no-root-layout"],
)
def test_next_route_group_refusals_plan_nothing(
    tmp_path: Path, root_layout: bool, segments: list[str], message: str
) -> None:
    layout = next_app(tmp_path, root_layout=root_layout)
    plan = FilePlan(tmp_path)

    with pytest.raises(GenerateError, match=message):
        plan_nextjs_page(plan, layout, segments, "x")

    assert plan.creates == {}
