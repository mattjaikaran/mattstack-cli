"""Tests for the client-side UI route inventory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mattstack.parsers.frontend_layout import detect_frontend_layout
from mattstack.parsers.frontend_routes import (
    react_router_routes,
    tanstack_route_id,
    tanstack_routes,
)


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
    ],
)
def test_tanstack_route_id(tmp_path: Path, relative: str, expected: str | None) -> None:
    assert tanstack_route_id(tmp_path, tmp_path / relative) == expected


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
