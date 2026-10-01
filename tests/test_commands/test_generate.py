"""Behavior of `mattstack generate`: field specs, wiring, refusal, and output contracts."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from mattstack.commands.codegen.fields import FieldSpecError, parse_fields
from mattstack.commands.generate import generate_app
from mattstack.parsers.python_schemas import parse_pydantic_file

runner = CliRunner()
MakeProject = Callable[..., Path]


def crud(root: Path, *args: str) -> Result:
    return runner.invoke(generate_app, ["crud", "Product", "--path", str(root), *args])


def test_repeated_and_quoted_field_flags_are_equivalent() -> None:
    assert parse_fields(["title:str", "price:decimal"]) == parse_fields(["title:str price:decimal"])
    assert parse_fields(["title:str,price:decimal"]) == parse_fields(["title:str", "price:decimal"])


@pytest.mark.parametrize(
    "spec",
    ["category:fk", "id:str", "title:str title:text", "class:str", "price:money", "owner:fk:user"],
)
def test_invalid_field_specs_are_rejected(spec: str) -> None:
    with pytest.raises(FieldSpecError):
        parse_fields([spec])


def test_crud_registers_controller_before_urls_are_built(
    tmp_path: Path, make_project: MakeProject
) -> None:
    root = make_project(tmp_path)
    result = crud(
        root, "-f", "title:str price:decimal", "-f", "category:fk:Category", "--with-tests"
    )
    assert result.exit_code == 0, result.output

    urls = (root / "backend" / "api" / "urls.py").read_text()
    registration = urls.index("api.register_controllers(ProductController)")
    assert urls.index("from core.controllers.product import ProductController") < registration
    # Ninja builds its URL list when `api.urls` is read in urlpatterns.
    assert registration < urls.index("urlpatterns")

    for path in (root / "backend").rglob("*.py"):
        ast.parse(path.read_text(), filename=str(path))
    test_source = (root / "backend" / "core" / "tests" / "test_product_api.py").read_text()
    assert '"/api/products/"' in test_source


def _fk_contract(root: Path) -> tuple[str, str, str]:
    """Return (Pydantic FK type, TS FK type, model source) for generated Product."""
    schemas = {
        s.name: s for s in parse_pydantic_file(root / "backend" / "core" / "schemas" / "product.py")
    }
    fk = next(f for f in schemas["ProductBaseSchema"].fields if f.name.endswith("_id"))
    client = (root / "frontend" / "src" / "api" / "product.ts").read_text()
    ts = client.split("export interface ProductCreateSchema {", 1)[1].split("}", 1)[0]
    ts_type = next(line for line in ts.splitlines() if "_id" in line).split(":")[1].strip(" ;")
    model = (root / "backend" / "core" / "models" / "product.py").read_text()
    return fk.type_str, ts_type, model


def test_fk_to_integer_key_model_is_numeric(tmp_path: Path, make_project: MakeProject) -> None:
    root = make_project(tmp_path)  # Category(models.Model): Django's integer auto key
    assert crud(root, "-f", "title:str category:fk:Category").exit_code == 0
    py_type, ts_type, model = _fk_contract(root)
    assert (py_type, ts_type) == ("int", "number")
    assert 'models.ForeignKey("core.Category"' in model


def test_fk_to_uuid_key_model_is_string(tmp_path: Path, make_project: MakeProject) -> None:
    root = make_project(tmp_path)
    (root / "backend" / "core" / "models" / "base.py").write_text(
        "class TimestampedModel(models.Model):\n"
        "    id = models.UUIDField(\n        primary_key=True, default=uuid.uuid4\n    )\n\n\n"
        "AbstractBaseModel = TimestampedModel\n"
    )
    (root / "backend" / "core" / "models" / "tag.py").write_text(
        "class Tag(AbstractBaseModel):\n    name = models.CharField(max_length=20)\n"
    )
    assert crud(root, "-f", "title:str tag:fk:Tag").exit_code == 0
    py_type, ts_type, _ = _fk_contract(root)
    assert (py_type, ts_type) == ("UUID", "string")


def test_fk_to_swapped_user_model_uses_auth_user_model(
    tmp_path: Path, make_project: MakeProject
) -> None:
    root = make_project(tmp_path)
    settings = root / "backend" / "api" / "settings.py"
    settings.write_text(settings.read_text() + 'AUTH_USER_MODEL = "core.User"\n')
    (root / "backend" / "core" / "models" / "user.py").write_text(
        "class User(AbstractUser):\n    pass\n"
    )
    assert crud(root, "-f", "owner:fk:User").exit_code == 0
    py_type, ts_type, model = _fk_contract(root)
    assert (py_type, ts_type) == ("int", "number")
    assert "models.ForeignKey(settings.AUTH_USER_MODEL" in model
    assert "from django.conf import settings" in model


@pytest.mark.parametrize(
    ("target", "model_source"),
    [
        ("core.Missing", None),
        ("Thing", "class Thing(ThirdPartyBase):\n    pass\n"),
    ],
    ids=["unknown-explicit-label", "unverifiable-primary-key"],
)
def test_unresolvable_fk_targets_are_refused(
    tmp_path: Path, make_project: MakeProject, target: str, model_source: str | None
) -> None:
    root = make_project(tmp_path)
    if model_source:
        (root / "backend" / "core" / "models" / "thing.py").write_text(model_source)
    result = crud(root, "-f", f"link:fk:{target}")
    assert result.exit_code == 1
    assert not (root / "backend" / "core" / "models" / "product.py").exists()


def test_crud_frontend_uses_shared_transport_and_string_decimals(
    tmp_path: Path, make_project: MakeProject
) -> None:
    root = make_project(tmp_path)
    assert crud(root, "-f", "title:str price:decimal").exit_code == 0

    client = (root / "frontend" / "src" / "api" / "product.ts").read_text()
    assert 'import { apiClient as http } from "@/api/client";' in client
    assert "localhost" not in client
    assert '"/products/"' in client
    assert "price: string;" in client
    assert (root / "frontend" / "src" / "routes" / "products.tsx").exists()


def test_crud_refuses_to_overwrite_existing_files(
    tmp_path: Path, make_project: MakeProject
) -> None:
    root = make_project(tmp_path)
    assert crud(root, "-f", "title:str").exit_code == 0
    model = root / "backend" / "core" / "models" / "product.py"
    model.write_text("# user edits\n")
    urls_before = (root / "backend" / "api" / "urls.py").read_text()

    result = crud(root, "-f", "title:str")
    assert result.exit_code == 1
    assert model.read_text() == "# user edits\n"
    assert (root / "backend" / "api" / "urls.py").read_text() == urls_before

    assert crud(root, "-f", "title:str", "--force").exit_code == 0
    urls_after = (root / "backend" / "api" / "urls.py").read_text()
    assert urls_after.count("register_controllers(ProductController)") == 1
    assert "class Product(" in model.read_text()


@pytest.mark.parametrize(
    "kwargs",
    [{"installed": ("todos",)}, {"api_class": "NinjaAPI"}],
    ids=["app-not-installed", "plain-ninja-api"],
)
def test_crud_refuses_unsupported_projects_without_writing(
    tmp_path: Path, make_project: MakeProject, kwargs: dict[str, object]
) -> None:
    root = make_project(tmp_path, **kwargs)
    before = sorted(p for p in root.rglob("*"))
    result = crud(root, "-f", "title:str")
    assert result.exit_code == 1
    assert sorted(p for p in root.rglob("*")) == before


def test_fk_target_must_exist(tmp_path: Path, make_project: MakeProject) -> None:
    root = make_project(tmp_path)
    result = crud(root, "-f", "owner:fk:Missing")
    assert result.exit_code == 1
    assert not (root / "backend" / "core" / "models" / "product.py").exists()


def test_endpoint_appends_to_existing_controller_under_its_prefix(
    tmp_path: Path, make_project: MakeProject
) -> None:
    root = make_project(tmp_path)
    assert crud(root, "-f", "title:str").exit_code == 0
    result = runner.invoke(generate_app, ["endpoint", "/products/featured", "--path", str(root)])
    assert result.exit_code == 0, result.output
    source = (root / "backend" / "core" / "controllers" / "product.py").read_text()
    ast.parse(source)
    assert '@http_get("/featured"' in source
