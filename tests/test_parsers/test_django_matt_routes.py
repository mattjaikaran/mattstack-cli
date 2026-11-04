"""Tests for django-matt APIController parser."""

from __future__ import annotations

from pathlib import Path

from mattstack.parsers.django_routes import (
    is_django_matt_project,
    parse_django_matt_controller_file,
)

SAMPLE_CONTROLLER = """\
from django_matt import APIController, get, post, put, delete
from django_matt.auth import JWTAuth, OptionalJWTAuth

from apps.core.models.product import Product
from apps.core.schemas.product import (
    ProductCreateSchema, ProductResponseSchema, ProductUpdateSchema
)
from apps.core.services.product import ProductService


class ProductController(APIController):
    prefix = "/products"
    tags = ["Products"]

    @get("/", response=list[ProductResponseSchema])
    def list_products(self, request, search: str | None = None):
        qs = Product.objects.all()
        if search:
            qs = qs.filter(title__icontains=search)
        return qs

    @get("/{product_id}", response=ProductResponseSchema, auth=OptionalJWTAuth())
    def get_product(self, request, product_id):
        return Product.objects.get(id=product_id)

    @post("/", response=ProductResponseSchema, auth=JWTAuth(), status=201)
    def create_product(self, request, payload: ProductCreateSchema):
        return ProductService().create(payload)

    @put("/{product_id}", response=ProductResponseSchema, auth=JWTAuth())
    def update_product(self, request, product_id, payload: ProductUpdateSchema):
        return ProductService().update(product_id, payload)

    @delete("/{product_id}", auth=JWTAuth(), status=204)
    def delete_product(self, request, product_id):
        ProductService().delete(product_id)
        return None
"""


def test_parse_controller_finds_class(tmp_path: Path) -> None:
    f = tmp_path / "controllers.py"
    f.write_text(SAMPLE_CONTROLLER)
    controllers = parse_django_matt_controller_file(f)
    assert len(controllers) == 1
    ctrl = controllers[0]
    assert ctrl.name == "ProductController"
    assert ctrl.prefix == "/products"
    assert "Products" in ctrl.tags


def test_parse_controller_finds_all_methods(tmp_path: Path) -> None:
    f = tmp_path / "controllers.py"
    f.write_text(SAMPLE_CONTROLLER)
    controllers = parse_django_matt_controller_file(f)
    ctrl = controllers[0]
    methods = {ep.method for ep in ctrl.endpoints}
    assert methods == {"GET", "POST", "PUT", "DELETE"}


def test_parse_controller_auth_detection(tmp_path: Path) -> None:
    f = tmp_path / "controllers.py"
    f.write_text(SAMPLE_CONTROLLER)
    controllers = parse_django_matt_controller_file(f)
    ctrl = controllers[0]
    ep_map = {ep.handler: ep for ep in ctrl.endpoints}
    assert ep_map["create_product"].auth is True
    assert ep_map["update_product"].auth is True
    assert ep_map["delete_product"].auth is True
    assert ep_map["list_products"].auth is False


JWT_DECORATOR_CONTROLLER = """\
from django_matt import APIController, get, post
from django_matt.auth import jwt_required


class OrderController(APIController):
    prefix = "/orders"
    tags = ["Orders"]

    @get("/")
    async def list_orders(self, request):
        return []

    @post("/")
    @jwt_required
    async def create_order(self, request, payload):
        return {}
"""


def test_parse_controller_jwt_required_decorator_sets_auth(tmp_path: Path) -> None:
    f = tmp_path / "controllers.py"
    f.write_text(JWT_DECORATOR_CONTROLLER)
    ctrl = parse_django_matt_controller_file(f)[0]
    ep_map = {ep.handler: ep for ep in ctrl.endpoints}
    assert ep_map["create_order"].auth is True


def test_parse_controller_without_auth_decorators_stays_public(tmp_path: Path) -> None:
    f = tmp_path / "controllers.py"
    f.write_text(JWT_DECORATOR_CONTROLLER)
    ctrl = parse_django_matt_controller_file(f)[0]
    ep_map = {ep.handler: ep for ep in ctrl.endpoints}
    assert ep_map["list_orders"].auth is False


def test_parse_controller_handlers(tmp_path: Path) -> None:
    f = tmp_path / "controllers.py"
    f.write_text(SAMPLE_CONTROLLER)
    controllers = parse_django_matt_controller_file(f)
    ctrl = controllers[0]
    handlers = {ep.handler for ep in ctrl.endpoints}
    assert "list_products" in handlers
    assert "get_product" in handlers
    assert "create_product" in handlers
    assert "update_product" in handlers
    assert "delete_product" in handlers


def test_parse_multiple_controllers(tmp_path: Path) -> None:
    content = """\
from django_matt import APIController, get, post


class FooController(APIController):
    prefix = "/foos"
    tags = ["Foo"]

    @get("/")
    def list_foos(self, request):
        return []


class BarController(APIController):
    prefix = "/bars"
    tags = ["Bar"]

    @post("/")
    def create_bar(self, request, payload):
        return {}
"""
    f = tmp_path / "controllers.py"
    f.write_text(content)
    controllers = parse_django_matt_controller_file(f)
    assert len(controllers) == 2
    names = {c.name for c in controllers}
    assert "FooController" in names
    assert "BarController" in names


def test_parse_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "api.py"
    f.write_text("# no controllers\n")
    controllers = parse_django_matt_controller_file(f)
    assert controllers == []


def test_is_django_matt_project_pyproject(tmp_path: Path) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text(
        '[project]\nname = "myapp"\ndependencies = ["django-matt>=0.9.0"]\n'
    )
    assert is_django_matt_project(tmp_path) is True


def test_is_django_matt_project_requirements(tmp_path: Path) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "requirements.txt").write_text("django-matt==0.9.0\ndjango>=4.2\n")
    assert is_django_matt_project(tmp_path) is True


def test_is_django_matt_project_false(tmp_path: Path) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text(
        '[project]\nname = "myapp"\ndependencies = ["django-ninja>=1.0"]\n'
    )
    assert is_django_matt_project(tmp_path) is False


def test_is_django_matt_project_no_files(tmp_path: Path) -> None:
    assert is_django_matt_project(tmp_path) is False
