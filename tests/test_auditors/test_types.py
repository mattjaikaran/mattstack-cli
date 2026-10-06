"""Round trip: Pydantic → Django Ninja OpenAPI → @hey-api/openapi-ts Zod → parity audit.

`fixtures/roundtrip/openapi.json` is the export of `export_schema.py` (alias,
Optional, enum, Literal, nested model, Decimal, datetime, constraints).
`zod.gen.ts` is the pinned generator's output for it:

    ./node_modules/.bin/openapi-ts -i openapi.json -o out -c @hey-api/client-fetch \
        --no-log-file -p @hey-api/typescript @hey-api/sdk zod @tanstack/react-query

Regenerate both when `HEY_API_VERSION` changes.
"""

from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mattstack.auditors.base import AuditConfig, Severity
from mattstack.auditors.types import TypeSafetyAuditor

FIXTURE = Path(__file__).parent / "fixtures" / "roundtrip"
Spec = dict[str, Any]


def _project(root: Path, spec: Spec) -> Path:
    backend = root / "backend"
    (backend / "docs" / "openapi").mkdir(parents=True)
    (backend / "manage.py").write_text("")
    (backend / "pyproject.toml").write_text('[project]\ndependencies = ["django-ninja"]\n')
    (backend / "docs" / "openapi" / "openapi.json").write_text(json.dumps(spec))
    generated = root / "frontend" / "src" / "api" / "generated"
    generated.mkdir(parents=True)
    (root / "frontend" / "package.json").write_text('{"dependencies": {"zod": "4.6.5"}}\n')
    shutil.copy(FIXTURE / "zod.gen.ts", generated / "zod.gen.ts")
    return root


def _audit(root: Path, spec: Spec) -> list[str]:
    findings = TypeSafetyAuditor(AuditConfig(project_path=_project(root, spec))).run()
    assert all(f.severity == Severity.ERROR for f in findings), findings
    return [f.message for f in findings]


def _fixture() -> Spec:
    spec: Spec = json.loads((FIXTURE / "openapi.json").read_text())
    return spec


def _schemas(spec: Spec) -> dict[str, Any]:
    schemas: dict[str, Any] = spec["components"]["schemas"]
    return schemas


def test_generated_zod_matches_the_contract(tmp_path: Path) -> None:
    assert _audit(tmp_path, _fixture()) == []


def _set(path: str, key: str, value: Any) -> Callable[[Spec], None]:
    def mutate(spec: Spec) -> None:
        schema, prop = path.split(".")
        _schemas(spec)[schema]["properties"][prop][key] = value

    return mutate


def _optional_display_name(spec: Spec) -> None:
    _schemas(spec)["Product"]["required"].remove("displayName")


def _snake_case_key(spec: Spec) -> None:
    props = _schemas(spec)["Product"]["properties"]
    props["created_at"] = props.pop("createdAt")
    _schemas(spec)["Product"]["required"].remove("createdAt")
    _schemas(spec)["Product"]["required"].append("created_at")


def _not_nullable_notes(spec: Spec) -> None:
    _schemas(spec)["Product"]["properties"]["notes"] = {"type": "string"}


def _new_enum_member(spec: Spec) -> None:
    _schemas(spec)["ProductStatus"]["enum"].append("deleted")


def _ref_changed(spec: Spec) -> None:
    _set("Product.shippingAddress", "$ref", "#/components/schemas/ProductStatus")(spec)


def _decimal_branch(spec: Spec) -> None:
    _schemas(spec)["Product"]["properties"]["unitPrice"]["anyOf"].append({"type": "integer"})


def _new_property(spec: Spec) -> None:
    _schemas(spec)["Address"]["properties"]["city"] = {"type": "string"}


@pytest.mark.parametrize(
    ("drifted", "mutate"),
    [
        ("Product.displayName", _optional_display_name),
        ("Product.displayName", _set("Product.displayName", "minLength", 3)),
        ("Address.streetLine", _set("Address.streetLine", "maxLength", 80)),
        ("Address.postalCode", _set("Address.postalCode", "anyOf", [{"type": "string"}])),
        ("Product.stockCount", _set("Product.stockCount", "maximum", 999)),
        ("Product.rating", _set("Product.rating", "anyOf", [{"type": "number"}, {"type": "null"}])),
        ("Product.createdAt", _set("Product.createdAt", "format", "date")),
        ("Product.created_at", _snake_case_key),
        ("Product.notes", _not_nullable_notes),
        ("Product.kind", _set("Product.kind", "enum", ["physical"])),
        ("Product.schemaVersion", _set("Product.schemaVersion", "const", "v2")),
        ("ProductStatus", _new_enum_member),
        ("Product.shippingAddress", _ref_changed),
        ("Product.unitPrice", _decimal_branch),
        ("Product.tags", _set("Product.tags", "maxItems", 5)),
        ("Address.city", _new_property),
    ],
)
def test_contract_drift_is_reported_on_the_drifted_field(
    tmp_path: Path, drifted: str, mutate: Callable[[Spec], None]
) -> None:
    spec = copy.deepcopy(_fixture())
    mutate(spec)
    messages = _audit(tmp_path, spec)
    assert messages, f"no finding for {drifted}"
    assert all(f"{drifted}:" in message for message in messages), messages
