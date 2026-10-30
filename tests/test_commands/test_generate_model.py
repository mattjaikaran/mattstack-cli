"""Contract of `mattstack generate model`: fields guard, admin package, and base model."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from click.testing import Result
from typer.testing import CliRunner

from mattstack.commands.generate import generate_app

runner = CliRunner()
MakeProject = Callable[..., Path]


def model(root: Path, *args: str) -> Result:
    return runner.invoke(generate_app, ["model", "Product", "--path", str(root), *args])


def snapshot(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_model_without_fields_or_empty_exits_before_writing(
    tmp_path: Path, make_project: MakeProject
) -> None:
    root = make_project(tmp_path)
    before = snapshot(root)

    result = model(root)

    assert result.exit_code == 1
    assert "No --fields given" in result.stderr
    assert snapshot(root) == before


def test_model_writes_admin_package_and_exports(tmp_path: Path, make_project: MakeProject) -> None:
    root = make_project(tmp_path)

    assert model(root, "-f", "title:str").exit_code == 0

    backend = root / "backend"
    admin_file = backend / "core" / "admin" / "product_admin.py"
    assert admin_file.is_file()
    assert (
        "from .product import Product" in (backend / "core" / "models" / "__init__.py").read_text()
    )
    assert (
        "from .product_admin import ProductAdmin"
        in (backend / "core" / "admin" / "__init__.py").read_text()
    )


def test_model_inherits_the_project_base_class_without_timestamps(
    tmp_path: Path, make_project: MakeProject
) -> None:
    root = make_project(tmp_path)
    (root / "backend" / "core" / "models" / "base.py").write_text(
        "class AbstractBaseModel(models.Model):\n"
        "    id = models.UUIDField(primary_key=True, default=uuid.uuid4)\n"
    )

    assert model(root, "-f", "title:str").exit_code == 0

    product = (root / "backend" / "core" / "models" / "product.py").read_text()
    assert "class Product(AbstractBaseModel):" in product
    assert "created_at =" not in product
    assert "updated_at =" not in product
