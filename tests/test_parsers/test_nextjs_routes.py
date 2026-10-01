"""Tests for Next.js App Router route parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mattstack.auditors.base import AuditConfig
from mattstack.auditors.endpoints import EndpointAuditor
from mattstack.parsers.nextjs_routes import (
    find_nextjs_app_dirs,
    parse_nextjs_routes,
)


def _create_app_dir(tmp_path: Path) -> Path:
    """Create a minimal Next.js app directory structure."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    return app_dir


def test_parse_page_route(tmp_path: Path) -> None:
    app = _create_app_dir(tmp_path)
    (app / "page.tsx").write_text("export default function Home() { return <div/>; }")

    routes = parse_nextjs_routes(app)
    assert len(routes) == 1
    assert routes[0].route_type == "page"
    assert routes[0].path == "/"
    assert routes[0].methods == ["GET"]


def test_parse_nested_page(tmp_path: Path) -> None:
    app = _create_app_dir(tmp_path)
    dashboard = app / "dashboard"
    dashboard.mkdir()
    (dashboard / "page.tsx").write_text("export default function Dashboard() {}")

    routes = parse_nextjs_routes(app)
    assert len(routes) == 1
    assert routes[0].path == "/dashboard"


def test_parse_dynamic_route(tmp_path: Path) -> None:
    app = _create_app_dir(tmp_path)
    users_id = app / "users" / "[id]"
    users_id.mkdir(parents=True)
    (users_id / "page.tsx").write_text("export default function User() {}")

    routes = parse_nextjs_routes(app)
    assert len(routes) == 1
    assert routes[0].path == "/users/[id]"


def test_parse_route_group_stripped(tmp_path: Path) -> None:
    app = _create_app_dir(tmp_path)
    auth_group = app / "(auth)" / "login"
    auth_group.mkdir(parents=True)
    (auth_group / "page.tsx").write_text("export default function Login() {}")

    routes = parse_nextjs_routes(app)
    assert len(routes) == 1
    assert routes[0].path == "/login"


def test_parse_api_route_get(tmp_path: Path) -> None:
    app = _create_app_dir(tmp_path)
    api_users = app / "api" / "users"
    api_users.mkdir(parents=True)
    (api_users / "route.ts").write_text(
        "export async function GET(request: Request) {\n  return Response.json({ users: [] });\n}\n"
    )

    routes = parse_nextjs_routes(app)
    assert len(routes) == 1
    assert routes[0].route_type == "api"
    assert routes[0].path == "/api/users"
    assert "GET" in routes[0].methods


def test_parse_api_route_multiple_methods(tmp_path: Path) -> None:
    app = _create_app_dir(tmp_path)
    api_users = app / "api" / "users"
    api_users.mkdir(parents=True)
    (api_users / "route.ts").write_text(
        "export async function GET(req: Request) { return Response.json([]); }\n"
        "export async function POST(req: Request) { return Response.json({}); }\n"
    )

    routes = parse_nextjs_routes(app)
    assert len(routes) == 1
    assert "GET" in routes[0].methods
    assert "POST" in routes[0].methods


def test_parse_api_route_arrow_export(tmp_path: Path) -> None:
    app = _create_app_dir(tmp_path)
    api = app / "api" / "health"
    api.mkdir(parents=True)
    (api / "route.ts").write_text(
        "export const GET = async (req: Request) => {\n  return Response.json({ ok: true });\n}\n"
    )

    routes = parse_nextjs_routes(app)
    assert len(routes) == 1
    assert routes[0].methods == ["GET"]


def test_api_route_with_auth(tmp_path: Path) -> None:
    app = _create_app_dir(tmp_path)
    api = app / "api" / "secure"
    api.mkdir(parents=True)
    (api / "route.ts").write_text(
        'import { getServerSession } from "next-auth";\n'
        "export async function POST(req: Request) {\n"
        "  const session = getServerSession();\n"
        "  return Response.json({});\n"
        "}\n"
    )

    routes = parse_nextjs_routes(app)
    assert len(routes) == 1
    assert routes[0].has_auth is True


def test_api_route_stub_detected(tmp_path: Path) -> None:
    app = _create_app_dir(tmp_path)
    api = app / "api" / "stub"
    api.mkdir(parents=True)
    (api / "route.ts").write_text(
        "export async function GET(req: Request) {\n"
        "  // TODO: implement\n"
        "  return Response.json({});\n"
        "}\n"
    )

    routes = parse_nextjs_routes(app)
    assert len(routes) == 1
    assert routes[0].is_stub is True


def test_page_loading_and_error_detection(tmp_path: Path) -> None:
    app = _create_app_dir(tmp_path)
    dashboard = app / "dashboard"
    dashboard.mkdir()
    (dashboard / "page.tsx").write_text("export default function D() {}")
    (dashboard / "loading.tsx").write_text("export default function L() {}")
    (dashboard / "error.tsx").write_text("'use client'; export default function E() {}")
    (dashboard / "layout.tsx").write_text("export default function Layout() {}")

    routes = parse_nextjs_routes(app)
    assert len(routes) == 1
    assert routes[0].has_loading is True
    assert routes[0].has_error is True
    assert routes[0].has_layout is True


def test_empty_app_dir(tmp_path: Path) -> None:
    app = _create_app_dir(tmp_path)
    routes = parse_nextjs_routes(app)
    assert routes == []


def test_nonexistent_app_dir(tmp_path: Path) -> None:
    routes = parse_nextjs_routes(tmp_path / "nonexistent")
    assert routes == []


def _package(root: Path, deps: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(json.dumps({"dependencies": deps}))


def test_find_nextjs_app_dirs_frontend(tmp_path: Path) -> None:
    _package(tmp_path / "frontend", {"next": "^15"})
    (tmp_path / "frontend" / "app").mkdir(parents=True)
    dirs = find_nextjs_app_dirs(tmp_path)
    assert len(dirs) == 1
    assert dirs[0] == tmp_path / "frontend" / "app"


def test_find_nextjs_app_dirs_src(tmp_path: Path) -> None:
    _package(tmp_path / "frontend", {"next": "^15"})
    (tmp_path / "frontend" / "src" / "app").mkdir(parents=True)
    dirs = find_nextjs_app_dirs(tmp_path)
    assert len(dirs) == 1
    assert dirs[0] == tmp_path / "frontend" / "src" / "app"


def test_find_nextjs_app_dirs_standalone(tmp_path: Path) -> None:
    _package(tmp_path, {"next": "^15"})
    (tmp_path / "app").mkdir()
    dirs = find_nextjs_app_dirs(tmp_path)
    assert len(dirs) == 1


@pytest.mark.parametrize(
    ("deps", "audited"),
    [
        ({"next": "^15", "react": "^19"}, True),
        ({"@tanstack/react-router": "^1", "vite": "^6"}, False),
        ({"react-router-dom": "^7", "vite": "^6"}, False),
    ],
)
def test_src_app_route_handlers_audited_only_for_next(
    tmp_path: Path, deps: dict[str, str], audited: bool
) -> None:
    frontend = tmp_path / "frontend"
    _package(frontend, deps)
    handler = frontend / "src" / "app" / "upload" / "route.ts"
    handler.parent.mkdir(parents=True)
    handler.write_text("export async function POST() { return Response.json({}) }\n")
    findings = EndpointAuditor(AuditConfig(project_path=tmp_path)).run()
    assert any("No auth on write API route" in f.message for f in findings) is audited


def test_find_nextjs_app_dirs_none(tmp_path: Path) -> None:
    dirs = find_nextjs_app_dirs(tmp_path)
    assert dirs == []


def test_skips_node_modules(tmp_path: Path) -> None:
    app = _create_app_dir(tmp_path)
    nm = app / "node_modules" / "some-pkg" / "app"
    nm.mkdir(parents=True)
    (nm / "page.tsx").write_text("export default function X() {}")
    routes = parse_nextjs_routes(app)
    assert routes == []


def test_mixed_pages_and_api_routes(tmp_path: Path) -> None:
    app = _create_app_dir(tmp_path)
    (app / "page.tsx").write_text("export default function Home() {}")
    (app / "about").mkdir()
    (app / "about" / "page.tsx").write_text("export default function About() {}")
    api = app / "api" / "users"
    api.mkdir(parents=True)
    (api / "route.ts").write_text(
        "export async function GET() { return Response.json([]); }\n"
        "export async function POST() { return Response.json({}); }\n"
    )

    routes = parse_nextjs_routes(app)
    pages = [r for r in routes if r.route_type == "page"]
    apis = [r for r in routes if r.route_type == "api"]
    assert len(pages) == 2
    assert len(apis) == 1
    page_paths = {r.path for r in pages}
    assert "/" in page_paths
    assert "/about" in page_paths
