"""Source of the round-trip fixture: print the Django Ninja OpenAPI document.

Run it with any environment that has django-ninja, for example the backend:

    uv run --project ../django-ninja-boilerplate python \
        tests/test_auditors/fixtures/roundtrip/export_schema.py \
        > tests/test_auditors/fixtures/roundtrip/openapi.json
"""

import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

import django
from django.conf import settings

settings.configure(SECRET_KEY="fixture-only", ROOT_URLCONF=__name__, INSTALLED_APPS=[])
django.setup()

from django.urls import path  # noqa: E402
from ninja import NinjaAPI, Schema  # noqa: E402
from pydantic import ConfigDict, Field  # noqa: E402
from pydantic.alias_generators import to_camel  # noqa: E402


class CamelCaseSchema(Schema):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ProductStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Address(CamelCaseSchema):
    street_line: str = Field(min_length=1, max_length=120)
    postal_code: str | None = Field(default=None, pattern=r"^[0-9]{5}$")


class Product(CamelCaseSchema):
    display_name: str = Field(min_length=2, max_length=50)
    unit_price: Decimal = Field(max_digits=10, decimal_places=2, ge=0)
    stock_count: int = Field(ge=0, le=1000)
    rating: float | None = Field(default=None, gt=0, lt=5)
    status: ProductStatus
    kind: Literal["physical", "digital"]
    created_at: datetime
    shipping_address: Address
    tags: list[str] = Field(default_factory=list, max_length=10)
    notes: str | None = None
    schema_version: Literal["v1"] = "v1"


api = NinjaAPI(title="Round trip", version="1.0.0")


@api.post("/products", response=Product, by_alias=True)
def create_product(request: object, payload: Product) -> Product:
    return payload


urlpatterns = [path("api/", api.urls)]

print(json.dumps(api.get_openapi_schema(path_prefix="/api"), indent=2, sort_keys=True))
