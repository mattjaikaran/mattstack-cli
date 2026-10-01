"""Tests for Phase 18: context subcommands, parsers, and output formats."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mattstack.cli import app
from mattstack.commands.context_builders import (
    build_models_context,
    build_routes_context,
    build_types_context,
)
from mattstack.commands.context_format import (
    estimate_tokens,
    format_context_claude,
    format_context_markdown,
)
from mattstack.parsers.django_models import parse_models_file
from mattstack.parsers.django_routes import parse_controller_file

runner = CliRunner()


def test_invalid_environment_fails_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "1"\n')
    monkeypatch.delenv("MATTSTACK_TEST_MISSING", raising=False)
    (tmp_path / ".env").write_text("DUMMY=${MATTSTACK_TEST_MISSING}\n")
    result = runner.invoke(app, ["context", "stack", str(tmp_path), "--format", "json"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Traceback" not in result.stderr


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def model_file(tmp_path: Path) -> Path:
    f = tmp_path / "product.py"
    f.write_text(
        textwrap.dedent(
            """\
            from django.db import models
            from core.models.base import AbstractBaseModel

            class Product(AbstractBaseModel):
                name = models.CharField(max_length=255)
                price = models.DecimalField(max_digits=10, decimal_places=2)
                category = models.ForeignKey('Category', on_delete=models.CASCADE)

            class Category(models.Model):
                title = models.CharField(max_length=100)
            """
        )
    )
    return f


@pytest.fixture()
def controller_file(tmp_path: Path) -> Path:
    f = tmp_path / "product_controller.py"
    f.write_text(
        textwrap.dedent(
            """\
            from ninja_extra import api_controller, http_get, http_post, http_put, http_delete
            from core.controllers.base_controller import BaseController
            from core.auth import JWTAuth

            @api_controller("/products", tags=["Products"])
            class ProductController(BaseController):

                @http_get("/", response=list[ProductSchema])
                def list_products(self, request):
                    return Product.objects.all()

                @http_post("/", response={201: ProductSchema}, auth=JWTAuth())
                def create_product(self, request, payload: ProductCreateSchema):
                    return Product.objects.create(**payload.model_dump())
            """
        )
    )
    return f


@pytest.fixture()
def project_with_models(tmp_path: Path, model_file: Path) -> Path:
    """Minimal project tree with models."""
    apps = tmp_path / "backend" / "apps" / "catalog" / "models"
    apps.mkdir(parents=True)
    (apps / "product.py").write_text(model_file.read_text())
    (tmp_path / "backend" / "pyproject.toml").write_text(
        '[project]\nname="backend"\n[tool.poetry.dependencies]\ndjango = "*"\n'
    )
    return tmp_path


@pytest.fixture()
def project_with_controllers(tmp_path: Path, controller_file: Path) -> Path:
    """Minimal project tree with controllers."""
    ctrl = tmp_path / "backend" / "apps" / "catalog" / "controllers"
    ctrl.mkdir(parents=True)
    (ctrl / "product_controller.py").write_text(controller_file.read_text())
    (tmp_path / "backend" / "pyproject.toml").write_text(
        '[project]\nname="backend"\n[tool.poetry.dependencies]\ndjango = "*"\n'
    )
    return tmp_path


# ── django_models parser ──────────────────────────────────────────────────────


def test_parse_models_inherits_abstract_base_model(model_file: Path) -> None:
    models = parse_models_file(model_file)
    names = {m.name for m in models}
    assert "Product" in names
    product = next(m for m in models if m.name == "Product")
    assert product.inherits == "AbstractBaseModel"


def test_parse_models_inherits_models_model(model_file: Path) -> None:
    models = parse_models_file(model_file)
    category = next((m for m in models if m.name == "Category"), None)
    assert category is not None
    assert category.inherits == "models.Model"


def test_parse_models_extracts_fields(model_file: Path) -> None:
    models = parse_models_file(model_file)
    product = next(m for m in models if m.name == "Product")
    field_names = [f.name for f in product.fields]
    assert "name" in field_names
    assert "price" in field_names
    assert "category" in field_names


def test_parse_models_field_type(model_file: Path) -> None:
    models = parse_models_file(model_file)
    product = next(m for m in models if m.name == "Product")
    name_field = next(f for f in product.fields if f.name == "name")
    assert name_field.field_type == "CharField"


def test_parse_models_fk_field_type(model_file: Path) -> None:
    models = parse_models_file(model_file)
    product = next(m for m in models if m.name == "Product")
    cat_field = next(f for f in product.fields if f.name == "category")
    assert cat_field.field_type == "ForeignKey"


def test_parse_models_app_from_path(tmp_path: Path) -> None:
    apps = tmp_path / "backend" / "apps" / "catalog" / "models"
    apps.mkdir(parents=True)
    f = apps / "product.py"
    f.write_text(
        "from core.models.base import AbstractBaseModel\nclass X(AbstractBaseModel):\n    pass\n"
    )
    models = parse_models_file(f)
    assert models[0].app == "catalog"


# ── django_routes controller parser ──────────────────────────────────────────


def test_parse_controller_finds_controller(controller_file: Path) -> None:
    controllers = parse_controller_file(controller_file)
    assert len(controllers) == 1
    assert controllers[0].name == "ProductController"


def test_parse_controller_prefix(controller_file: Path) -> None:
    controllers = parse_controller_file(controller_file)
    assert controllers[0].prefix == "/products"


def test_parse_controller_tag(controller_file: Path) -> None:
    controllers = parse_controller_file(controller_file)
    assert controllers[0].tag == "Products"


def test_parse_controller_endpoints(controller_file: Path) -> None:
    controllers = parse_controller_file(controller_file)
    endpoints = controllers[0].endpoints
    methods = {ep.method for ep in endpoints}
    assert "GET" in methods
    assert "POST" in methods


def test_parse_controller_auth_on_post(controller_file: Path) -> None:
    controllers = parse_controller_file(controller_file)
    post_ep = next(ep for ep in controllers[0].endpoints if ep.method == "POST")
    assert post_ep.auth is True


def test_parse_controller_no_auth_on_get(controller_file: Path) -> None:
    controllers = parse_controller_file(controller_file)
    get_ep = next(ep for ep in controllers[0].endpoints if ep.method == "GET")
    assert get_ep.auth is False


def test_parse_controller_handler_names(controller_file: Path) -> None:
    controllers = parse_controller_file(controller_file)
    handlers = {ep.handler for ep in controllers[0].endpoints}
    assert "list_products" in handlers
    assert "create_product" in handlers


# ── build_models_context ──────────────────────────────────────────────────────


def test_build_models_context_returns_models_key(project_with_models: Path) -> None:
    ctx = build_models_context(project_with_models)
    assert "models" in ctx
    assert isinstance(ctx["models"], list)


def test_build_models_context_finds_product(project_with_models: Path) -> None:
    ctx = build_models_context(project_with_models)
    names = [m["name"] for m in ctx["models"]]
    assert "Product" in names


def test_build_models_context_json_serializable(project_with_models: Path) -> None:
    ctx = build_models_context(project_with_models)
    dumped = json.dumps(ctx)
    parsed = json.loads(dumped)
    assert "models" in parsed


# ── build_routes_context ──────────────────────────────────────────────────────


def test_build_routes_context_returns_routes_key(project_with_controllers: Path) -> None:
    ctx = build_routes_context(project_with_controllers)
    assert "routes" in ctx


def test_build_routes_context_finds_product_controller(project_with_controllers: Path) -> None:
    ctx = build_routes_context(project_with_controllers)
    names = [r["controller"] for r in ctx["routes"]]
    assert "ProductController" in names


def test_build_routes_context_json_serializable(project_with_controllers: Path) -> None:
    ctx = build_routes_context(project_with_controllers)
    dumped = json.dumps(ctx)
    parsed = json.loads(dumped)
    assert "routes" in parsed


# ── build_types_context ───────────────────────────────────────────────────────


def test_build_types_context_returns_keys(tmp_path: Path) -> None:
    ctx = build_types_context(tmp_path)
    assert "interfaces" in ctx
    assert "zod_schemas" in ctx


def test_build_types_context_finds_interfaces(tmp_path: Path) -> None:
    ts_dir = tmp_path / "frontend" / "src" / "types"
    ts_dir.mkdir(parents=True)
    (ts_dir / "types.ts").write_text(
        "export interface Product {\n  id: string;\n  name: string;\n}\n"
    )
    ctx = build_types_context(tmp_path)
    names = [i["name"] for i in ctx["interfaces"]]
    assert "Product" in names


# ── formatters ────────────────────────────────────────────────────────────────


def test_format_context_claude_wraps_in_context_tag() -> None:
    ctx = {"project_name": "myapp", "project_path": "/tmp/myapp", "components": {}}
    output = format_context_claude(ctx)
    assert output.startswith("<context>")
    assert output.strip().endswith("</context>")


def test_format_context_claude_includes_models() -> None:
    ctx = {
        "project_name": "myapp",
        "project_path": "/tmp",
        "components": {},
        "models": [
            {"name": "Product", "app": "catalog", "inherits": "AbstractBaseModel", "fields": []}
        ],
    }
    output = format_context_claude(ctx)
    assert "<models>" in output
    assert 'name="Product"' in output


def test_format_context_claude_includes_routes() -> None:
    ctx = {
        "project_name": "myapp",
        "project_path": "/tmp",
        "components": {},
        "routes": [
            {
                "controller": "ProductController",
                "prefix": "/products",
                "tag": "Products",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/",
                        "handler": "list_products",
                        "response": None,
                        "auth": False,
                    }
                ],
            }
        ],
    }
    output = format_context_claude(ctx)
    assert "<routes>" in output
    assert 'name="ProductController"' in output


def test_format_context_markdown_models_section() -> None:
    ctx = {
        "project_name": "myapp",
        "components": {},
        "models": [
            {"name": "Product", "app": "catalog", "inherits": "AbstractBaseModel", "fields": []}
        ],
    }
    output = format_context_markdown(ctx)
    assert "## Models" in output
    assert "Product" in output


def test_format_context_markdown_routes_section() -> None:
    ctx = {
        "project_name": "myapp",
        "components": {},
        "routes": [
            {
                "controller": "ProductController",
                "prefix": "/products",
                "tag": "Products",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/",
                        "handler": "list_products",
                        "response": None,
                        "auth": False,
                    }
                ],
            }
        ],
    }
    output = format_context_markdown(ctx)
    assert "## API Routes" in output
    assert "ProductController" in output


# ── token estimate ────────────────────────────────────────────────────────────


def test_estimate_tokens_rough_sanity() -> None:
    text = "a" * 400
    assert estimate_tokens(text) == 100


def test_estimate_tokens_minimum_one() -> None:
    assert estimate_tokens("") == 1


def test_estimate_tokens_scales_with_length() -> None:
    short = estimate_tokens("hello")
    long = estimate_tokens("hello " * 100)
    assert long > short


# ── CLI integration ───────────────────────────────────────────────────────────


def test_cli_context_stack_runs(tmp_path: Path) -> None:
    result = runner.invoke(app, ["context", "stack", str(tmp_path)])
    assert result.exit_code == 0


def test_cli_context_models_runs(tmp_path: Path) -> None:
    result = runner.invoke(app, ["context", "models", str(tmp_path)])
    assert result.exit_code == 0


def test_cli_context_routes_runs(tmp_path: Path) -> None:
    result = runner.invoke(app, ["context", "routes", str(tmp_path)])
    assert result.exit_code == 0


def test_cli_context_types_runs(tmp_path: Path) -> None:
    result = runner.invoke(app, ["context", "types", str(tmp_path)])
    assert result.exit_code == 0


def test_cli_context_full_runs(tmp_path: Path) -> None:
    result = runner.invoke(app, ["context", "full", str(tmp_path)])
    assert result.exit_code == 0


def test_cli_context_full_json_format(tmp_path: Path) -> None:
    result = runner.invoke(app, ["context", "full", str(tmp_path), "--format", "json"])
    assert result.exit_code == 0
    # Output should contain valid JSON prefix
    assert "{" in result.output


def test_cli_context_full_claude_format(tmp_path: Path) -> None:
    result = runner.invoke(app, ["context", "full", str(tmp_path), "--format", "claude"])
    assert result.exit_code == 0
    assert "<context>" in result.output


def test_cli_context_full_includes_token_count(tmp_path: Path) -> None:
    result = runner.invoke(app, ["context", "full", str(tmp_path)])
    assert result.exit_code == 0
    assert "Estimated tokens" in result.output


def test_cli_context_models_json_format(tmp_path: Path) -> None:
    result = runner.invoke(app, ["context", "models", str(tmp_path), "--format", "json"])
    assert result.exit_code == 0
    assert "models" in result.output


def test_cli_context_output_to_file(tmp_path: Path) -> None:
    out_file = tmp_path / "context.md"
    result = runner.invoke(app, ["context", "full", str(tmp_path), "--output", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text()
    assert len(content) > 0
