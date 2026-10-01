"""Behavior of `mattstack sync`: mounted paths, inherited fields, enums, and `all` parity."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mattstack.commands.generate import generate_app
from mattstack.commands.sync import sync_app
from mattstack.parsers.api_routes import collect_api_routes

runner = CliRunner()

ENUMS = """\
from enum import Enum


class Status(str, Enum):
    DRAFT = "draft"
    LIVE = "live"
"""


@pytest.fixture
def crud_root(tmp_path: Path, make_project: Callable[..., Path]) -> Path:
    root = make_project(tmp_path)
    (root / "backend" / "core" / "enums.py").write_text(ENUMS)
    result = runner.invoke(
        generate_app,
        [
            "crud",
            "Product",
            "--path",
            str(root),
            "-f",
            "title:str price:decimal category:fk:Category",
        ],
    )
    assert result.exit_code == 0, result.output
    return root


def sync(root: Path, command: str) -> None:
    result = runner.invoke(sync_app, [command, "--path", str(root)])
    assert result.exit_code == 0, result.output


def generated(root: Path, kind: str) -> str:
    return (root / "frontend" / "src" / kind / "generated.ts").read_text()


def test_api_client_uses_controller_prefix_and_mutate_variables(crud_root: Path) -> None:
    root = crud_root
    sync(root, "api-client")
    client = generated(root, "api")

    assert "#" not in client.replace("#!", "")
    assert 'request<Paginated<ProductResponseSchema>>("GET", "/products/"' in client
    assert "`/products/${encodeURIComponent(product_id)}`" in client
    assert "mutationFn: (data: ProductCreateSchema) =>" in client
    assert (
        "mutationFn: ({ product_id, data }: { product_id: string; data: ProductUpdateSchema })"
        in client
    )
    assert 'import { apiClient as http } from "@/api/client";' in client


def test_types_include_inherited_fields_and_string_decimals(crud_root: Path) -> None:
    root = crud_root
    sync(root, "types")
    types = generated(root, "types")

    response = types.split("export interface ProductResponseSchema {", 1)[1].split("}", 1)[0]
    for field in ("title: string;", "price: string;", "category_id: number;", "id: string;"):
        assert field in response
    assert "export interface ProductCreateSchema {" in types
    assert 'export type Status = "draft" | "live";' in types


def test_sync_all_writes_what_each_command_writes(crud_root: Path) -> None:
    root = crud_root
    sync(root, "types")
    sync(root, "zod")
    sync(root, "api-client")
    individual = {kind: generated(root, kind) for kind in ("types", "schemas", "api")}

    sync(root, "all")
    assert {kind: generated(root, kind) for kind in ("types", "schemas", "api")} == individual
    assert "export const statusSchema = z.enum(" in individual["schemas"]


def test_inherited_camel_case_alias_generator(crud_root: Path) -> None:
    root = crud_root
    (root / "backend" / "core" / "schemas" / "base.py").write_text(
        "class CamelCaseSchema(Schema):\n"
        "    model_config = ConfigDict(alias_generator=to_camel)\n\n\n"
        "class OrderSchema(CamelCaseSchema):\n    created_by: str\n"
    )
    sync(root, "types")
    assert "createdBy: string;" in generated(root, "types")


def test_conflicting_schema_names_are_qualified_not_dropped(crud_root: Path) -> None:
    root = crud_root
    other = root / "backend" / "billing" / "schemas"
    other.mkdir(parents=True)
    (other / "invoice.py").write_text("class ProductBaseSchema(Schema):\n    sku: str\n")
    sync(root, "types")
    types = generated(root, "types")
    assert "export interface CoreProductBaseSchema {" in types
    assert "export interface BillingProductBaseSchema {" in types


def test_router_mount_and_django_matt_paths(tmp_path: Path) -> None:
    backend = tmp_path / "backend"
    (backend / "users").mkdir(parents=True)
    (backend / "api.py").write_text(
        'from users.routes import router as users_router\n\napi.add_router("/auth", users_router)\n'
    )
    (backend / "users" / "routes.py").write_text(
        'router = Router()\n\n\n@router.post("/login")\ndef login(request, payload: LoginSchema):\n'
        "    return {}\n"
    )
    (backend / "users" / "api").mkdir()
    (backend / "users" / "api" / "items.py").write_text(
        "class ItemController(APIController):\n"
        '    prefix = "/items"\n\n'
        '    @get("/<uuid:item_id>")\n'
        "    async def get_item(self, request, item_id: UUID) -> ItemSchema:\n"
        "        return item\n"
    )
    routes = {(r.method, r.path): r for r in collect_api_routes(backend)}
    assert routes[("POST", "/auth/login")].body_type == "LoginSchema"
    assert routes[("GET", "/items/{item_id}")].response == "ItemSchema"


def test_request_bodies_use_validation_aliases(crud_root: Path) -> None:
    """A body keyed by serialization aliases would be rejected by Ninja."""
    core = crud_root / "backend" / "core"
    (core / "schemas" / "tag.py").write_text(
        "class TagBaseSchema(Schema):\n"
        '    category: str = Field(validation_alias="category_id", '
        'serialization_alias="category")\n'
        "\n\n"
        "class TagCreateSchema(TagBaseSchema):\n"
        "    label: str\n"
    )
    (core / "controllers" / "tag.py").write_text(
        '@api_controller("/tags")\n'
        "class TagController:\n"
        '    @http_post("/", response={201: TagCreateSchema})\n'
        "    def create_tag(self, payload: TagCreateSchema):\n"
        "        return 201, payload\n"
    )
    sync(crud_root, "all")
    types = generated(crud_root, "types")
    request = types.split("export interface TagCreateSchemaInput {", 1)[1].split("}", 1)[0]
    response = types.split("export interface TagCreateSchema {", 1)[1].split("}", 1)[0]
    assert "category_id: string;" in request and "label: string;" in request
    assert "category: string;" in response and "category_id" not in response
    client = generated(crud_root, "api")
    assert "mutationFn: (data: TagCreateSchemaInput) =>" in client
    type_import = next(line for line in client.splitlines() if line.startswith("import type"))
    assert "TagCreateSchemaInput" in type_import


def test_nested_request_bodies_use_nested_validation_aliases(crud_root: Path) -> None:
    core = crud_root / "backend" / "core"
    (core / "schemas" / "batch.py").write_text(
        "class TagIn(Schema):\n"
        '    category: str = Field(validation_alias="category_id", '
        'serialization_alias="category")\n'
        "\n\n"
        "class BatchSchema(Schema):\n"
        "    items: list[TagIn]\n"
    )
    (core / "controllers" / "batch.py").write_text(
        '@api_controller("/batches")\n'
        "class BatchController:\n"
        '    @http_post("/", response={201: BatchSchema})\n'
        "    def create_batch(self, payload: BatchSchema):\n"
        "        return 201, payload\n"
    )
    sync(crud_root, "all")
    types = generated(crud_root, "types")
    wrapper = types.split("export interface BatchSchemaInput {", 1)[1].split("}", 1)[0]
    assert "items: TagInInput[];" in wrapper
    assert "category_id: string;" in types.split("export interface TagInInput {", 1)[1]
    assert "mutationFn: (data: BatchSchemaInput) =>" in generated(crud_root, "api")


def test_request_variant_names_avoid_existing_schemas(crud_root: Path) -> None:
    (crud_root / "backend" / "core" / "schemas" / "foo.py").write_text(
        "class Foo(Schema):\n"
        '    ref: str = Field(validation_alias="ref_id", serialization_alias="ref")\n'
        "\n\n"
        "class FooInput(Schema):\n"
        "    ref: int\n"
    )
    sync(crud_root, "types")
    types = generated(crud_root, "types")
    assert types.count("export interface FooInput {") == 1
    assert "ref: number;" in types.split("export interface FooInput {", 1)[1].split("}", 1)[0]
    assert "ref_id: string;" in types.split("export interface FooInput2 {", 1)[1].split("}", 1)[0]


def test_route_decorators_and_ninja_paginator_shapes(crud_root: Path) -> None:
    (crud_root / "backend" / "core" / "controllers" / "note.py").write_text(
        "from ninja.pagination import LimitOffsetPagination, paginate\n"
        "from ninja_extra import api_controller, route\n\n\n"
        '@api_controller("/notes")\n'
        "class NoteController:\n"
        '    @route.get("/", response=list[ProductResponseSchema])\n'
        "    @paginate(LimitOffsetPagination)\n"
        "    def list_notes(self):\n"
        "        return []\n"
    )
    sync(crud_root, "api-client")
    client = generated(crud_root, "api")
    hook = client.split("export function useListNotes(", 1)[1].split("\n}", 1)[0]
    assert 'request<PagedItems<ProductResponseSchema>>("GET", "/notes/"' in hook
    assert "{ params: { limit, offset } }" in hook
    assert "export interface PagedItems<T> {\n  count: number;\n  items: T[];\n}" in client


def test_decimal_wire_type_follows_field_serializers(crud_root: Path) -> None:
    """Only an always-active `-> str` serializer settles the renderer-dependent wire form."""
    (crud_root / "backend" / "core" / "schemas" / "money.py").write_text(
        "class PriceSchema(Schema):\n"
        "    amount: Decimal = Field(ge=0)\n"
        "\n\n"
        "class PricedSchema(PriceSchema):\n"
        '    @field_serializer("amount")\n'
        "    def amount_text(self, value: Decimal) -> str:\n"
        "        return str(value)\n"
        "\n\n"
        "class ResalePriceSchema(PricedSchema):\n"
        "    note: str\n"
        "\n\n"
        "class JsonPriceSchema(PriceSchema):\n"
        '    @field_serializer("amount", when_used="json")\n'
        "    def amount_text(self, value: Decimal) -> str:\n"
        "        return str(value)\n"
    )
    sync(crud_root, "all")
    types, zod = generated(crud_root, "types"), generated(crud_root, "schemas")

    def ts_field(schema: str) -> str:
        body = types.split(f"export interface {schema} {{", 1)[1].split("}", 1)[0]
        return next(line.strip() for line in body.splitlines() if "amount" in line)

    def zod_field(schema: str) -> str:
        var = schema[:1].lower() + schema[1:] + "Schema"
        body = zod.split(f"export const {var} = z.object({{", 1)[1].split("});", 1)[0]
        return next(line.strip() for line in body.splitlines() if "amount" in line)

    # Ninja dumps in Python mode, so a json-only serializer never runs for it.
    for schema in ("PriceSchema", "JsonPriceSchema"):
        assert ts_field(schema) == "amount: number | string;"
        assert zod_field(schema).startswith("amount: z.union([z.number(), z.string()")
    for schema in ("PricedSchema", "ResalePriceSchema"):  # declared and inherited
        assert ts_field(schema) == "amount: string;"
        assert zod_field(schema) == "amount: z.string(),"


def test_enum_values_with_quotes_stay_valid_typescript(crud_root: Path) -> None:
    (crud_root / "backend" / "core" / "greetings.py").write_text(
        'class Greeting(str, Enum):\n    HI = \'say "hi"\'\n    YO = "it\'s"\n'
    )
    sync(crud_root, "all")
    assert 'export type Greeting = "say \\"hi\\"" | "it\'s";' in generated(crud_root, "types")
    assert 'z.enum(["say \\"hi\\"", "it\'s"])' in generated(crud_root, "schemas")
