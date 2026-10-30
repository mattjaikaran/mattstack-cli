"""Output contract of `mattstack generate crud`: routes, schemas, UI, and tests."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from mattstack.commands.generate import generate_app

runner = CliRunner()
MakeProject = Callable[..., Path]


def crud(root: Path, *args: str, name: str = "Product") -> Result:
    return runner.invoke(generate_app, ["crud", name, "--path", str(root), *args])


def class_block(source: str, declaration: str) -> str:
    """Return the indented body of the class whose header is *declaration*."""
    lines = source[source.index(declaration) :].splitlines()
    body = [lines[0]]
    for line in lines[1:]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


@pytest.fixture
def generated(tmp_path: Path, make_project: MakeProject) -> Path:
    root = make_project(tmp_path)
    result = crud(root, "-f", "title:str price:decimal", "--with-tests")
    assert result.exit_code == 0, result.output
    return root


def test_controller_declares_one_route_per_crud_verb(generated: Path) -> None:
    controller = (generated / "backend" / "core" / "controllers" / "product.py").read_text()

    for decorator in ("@http_get", "@http_post", "@http_put", "@http_delete"):
        assert any(line.strip().startswith(decorator) for line in controller.splitlines()), (
            f"no {decorator} route"
        )


def test_update_schema_is_all_optional_and_response_has_identity(generated: Path) -> None:
    schemas = (generated / "backend" / "core" / "schemas" / "product.py").read_text()

    update = class_block(schemas, "class ProductUpdateSchema")
    field_lines = [line for line in update.splitlines() if " = Field(" in line]
    declared = {line.split(":", 1)[0].strip() for line in field_lines}
    assert declared == {"title", "price"}
    for line in field_lines:
        arguments = line.split("Field(", 1)[1]
        assert "default=None" in arguments, line

    response = class_block(schemas, "class ProductResponseSchema")
    for name in ("id", "created_at", "updated_at"):
        assert re.search(rf"^\s+{name}:", response, re.M), f"ResponseSchema has no {name}"


def test_crud_writes_hooks_component_and_tests(generated: Path) -> None:
    src = generated / "frontend" / "src"
    assert (src / "hooks" / "useProducts.ts").is_file()
    component = src / "components" / "ProductList" / "index.tsx"
    assert "export function ProductList()" in component.read_text()
    assert (component.parent / "ProductList.test.tsx").is_file()
    assert (generated / "backend" / "core" / "tests" / "test_product_api.py").is_file()


def test_every_new_backend_module_compiles(tmp_path: Path, make_project: MakeProject) -> None:
    root = make_project(tmp_path)
    before = set((root / "backend").rglob("*.py"))
    assert crud(root, "-f", "title:str price:decimal", "--with-tests").exit_code == 0

    created = sorted(set((root / "backend").rglob("*.py")) - before)
    assert created, "crud created no backend module"
    for path in created:
        compile(path.read_text(), str(path), "exec")
