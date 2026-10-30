"""Tests for Django route parser."""

from __future__ import annotations

from pathlib import Path

from mattstack.parsers.django_routes import parse_controller_file, parse_routes_file


def test_basic_routes(tmp_path: Path) -> None:
    f = tmp_path / "api.py"
    f.write_text(
        "from ninja import Router\n\n"
        "router = Router()\n\n"
        '@router.get("/users")\n'
        "def list_users(request):\n"
        "    return []\n\n"
        '@router.post("/users")\n'
        "def create_user(request):\n"
        "    return {}\n"
    )
    routes = parse_routes_file(f)
    assert len(routes) >= 2
    methods = {r.method for r in routes}
    assert "GET" in methods
    assert "POST" in methods


def test_auth_detection(tmp_path: Path) -> None:
    f = tmp_path / "api.py"
    f.write_text(
        "from ninja import Router\n\n"
        "router = Router()\n\n"
        '@router.post("/users", auth=Bearer)\n'
        "def create_user(request):\n"
        "    return {}\n\n"
        '@router.get("/public")\n'
        "def public_endpoint(request):\n"
        "    return {}\n"
    )
    routes = parse_routes_file(f)
    route_map = {r.path: r for r in routes}
    assert route_map["/users"].has_auth is True
    assert route_map["/public"].has_auth is False


def test_stub_detection(tmp_path: Path) -> None:
    f = tmp_path / "api.py"
    f.write_text(
        "from ninja import Router\n\n"
        "router = Router()\n\n"
        '@router.get("/stub")\n'
        "def stub_endpoint(request):\n"
        "    pass\n\n"
        '@router.get("/real")\n'
        "def real_endpoint(request):\n"
        '    return {"data": "real"}\n'
    )
    routes = parse_routes_file(f)
    route_map = {r.path: r for r in routes}
    assert route_map["/stub"].is_stub is True
    assert route_map["/real"].is_stub is False


def test_http_decorator(tmp_path: Path) -> None:
    f = tmp_path / "api.py"
    f.write_text('@http_get("/items")\ndef list_items(request):\n    return []\n')
    routes = parse_routes_file(f)
    assert len(routes) >= 1
    assert routes[0].method == "GET"
    assert routes[0].path == "/items"


def test_all_methods(tmp_path: Path) -> None:
    f = tmp_path / "api.py"
    f.write_text(
        "router = Router()\n\n"
        '@router.get("/a")\ndef a(r): return 1\n\n'
        '@router.post("/b")\ndef b(r): return 1\n\n'
        '@router.put("/c")\ndef c(r): return 1\n\n'
        '@router.delete("/d")\ndef d(r): return 1\n\n'
        '@router.patch("/e")\ndef e(r): return 1\n'
    )
    routes = parse_routes_file(f)
    methods = {r.method for r in routes}
    assert methods == {"GET", "POST", "PUT", "DELETE", "PATCH"}


def test_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "api.py"
    f.write_text("# no routes\n")
    routes = parse_routes_file(f)
    assert len(routes) == 0


def test_controller_class_auth_applies_to_endpoints(tmp_path: Path) -> None:
    f = tmp_path / "controllers.py"
    f.write_text(
        "from ninja_extra import api_controller, http_get\n\n"
        '@api_controller("/p", tags=["P"], auth=JWTAuth())\n'
        "class PController:\n"
        '    @http_get("/")\n'
        "    def list_items(self):\n"
        "        return []\n\n"
        '    @http_get("/open", auth=None)\n'
        "    def open_items(self):\n"
        "        return []\n"
    )
    controllers = parse_controller_file(f)
    assert len(controllers) == 1
    controller = controllers[0]
    assert controller.prefix == "/p"
    assert controller.tag == "P"
    assert controller.auth is True
    endpoints = {ep.path: ep for ep in controller.endpoints}
    assert endpoints["/"].auth is True
    assert endpoints["/open"].auth is False


def test_controller_without_class_auth_leaves_endpoints_public(tmp_path: Path) -> None:
    f = tmp_path / "controllers.py"
    f.write_text(
        "from ninja_extra import api_controller, http_get\n\n"
        '@api_controller("/p", tags=["P"])\n'
        "class PController(BaseController):\n"
        '    @http_get("/")\n'
        "    def list_items(self):\n"
        "        return []\n"
    )
    controllers = parse_controller_file(f)
    assert len(controllers) == 1
    assert controllers[0].auth is False
    assert controllers[0].endpoints[0].auth is False
