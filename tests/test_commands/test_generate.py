"""Behavior of `mattstack generate`: field specs, wiring, refusal, and output contracts."""

from __future__ import annotations

import json
import shutil
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


def crud(root: Path, *args: str, name: str = "Product") -> Result:
    return runner.invoke(generate_app, ["crud", name, "--path", str(root), *args])


def page(root: Path, *args: str) -> Result:
    return runner.invoke(generate_app, ["page", *args, "--project", str(root)])


def snapshot(root: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


APP = """\
import { Routes, Route } from 'react-router-dom'
import Layout from '@/components/Layout'
import ProtectedRoute from '@/components/ProtectedRoute'
import HomePage from '@/pages/HomePage'
import NotFoundPage from '@/pages/NotFoundPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<HomePage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
"""


def react_router_project(root: Path, app: str = APP) -> Path:
    """Turn the TanStack fixture frontend into the react-vite-starter router shape."""
    frontend = root / "frontend"
    deps = {"vite": "6", "react-router-dom": "7", "@tanstack/react-query": "5", "axios": "1"}
    (frontend / "package.json").write_text(json.dumps({"dependencies": deps}))
    shutil.rmtree(frontend / "src" / "routes")
    (frontend / "src" / "pages").mkdir()
    (frontend / "src" / "App.tsx").write_text(app)
    return root


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
    py_type, ts_type, _ = _fk_contract(root)
    assert (py_type, ts_type) == ("int", "number")


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
    route = root / "frontend" / "src" / "routes" / "products" / "index.tsx"
    assert 'createFileRoute("/products/")' in route.read_text()


def test_tanstack_crud_refuses_a_section_hidden_by_a_flat_layout(
    tmp_path: Path, make_project: MakeProject
) -> None:
    root = make_project(tmp_path)
    (root / "frontend" / "src" / "routes" / "products.tsx").write_text(
        'export const Route = createFileRoute("/products")({ component: Products })\n'
    )
    before = snapshot(root)
    assert crud(root, "-f", "title:str").exit_code == 1
    assert snapshot(root) == before


def test_react_router_page_registers_once_inside_the_protected_group(
    tmp_path: Path, make_project: MakeProject
) -> None:
    root = react_router_project(make_project(tmp_path))
    app = root / "frontend" / "src" / "App.tsx"
    assert page(root, "user-settings", "--route-group", "protected").exit_code == 0

    text = app.read_text()
    guard = text.index("<ProtectedRoute />}>")
    route = text.index('<Route path="/user-settings" element={<UserSettingsPage />} />')
    assert guard < route < text.index("</Route>", guard)
    assert "import UserSettingsPage from '@/pages/UserSettingsPage'" in text
    page_file = root / "frontend" / "src" / "pages" / "UserSettingsPage.tsx"
    assert "export default function UserSettingsPage" in page_file.read_text()

    before = snapshot(root)
    assert page(root, "user-settings", "--route-group", "protected").exit_code == 1
    assert page(root, "user-settings", "--force").exit_code == 1  # other group
    assert snapshot(root) == before

    app_text = app.read_text()
    page_file.write_text("// user edits\n")
    assert page(root, "user-settings", "--route-group", "protected", "--force").exit_code == 0
    assert app.read_text() == app_text
    assert "export default function UserSettingsPage" in page_file.read_text()


@pytest.mark.parametrize(
    ("app", "args", "exit_code"),
    [
        (APP.replace("<Routes>", "<Routes>{extra}"), (), 1),
        (APP.replace("export default", "const r = useRoutes([])\nexport default"), (), 1),
        (APP.replace("<Routes>", "<Routes>\n      <Route {...extra} />"), (), 1),
        (APP, ("--dry-run",), 0),
    ],
    ids=["dynamic-routes", "use-routes", "spread-route", "dry-run"],
)
def test_react_router_page_leaves_project_unchanged(
    tmp_path: Path, make_project: MakeProject, app: str, args: tuple[str, ...], exit_code: int
) -> None:
    root = react_router_project(make_project(tmp_path), app)
    before = snapshot(root)
    assert page(root, "settings", *args).exit_code == exit_code
    assert snapshot(root) == before


def test_react_router_crud_registers_a_kebab_public_route(
    tmp_path: Path, make_project: MakeProject
) -> None:
    root = react_router_project(make_project(tmp_path))
    assert crud(root, "-f", "title:str", name="ProductItem").exit_code == 0

    src = root / "frontend" / "src"
    assert (
        "export default function ProductItemsPage"
        in (src / "pages" / "ProductItemsPage.tsx").read_text()
    )
    text = (src / "App.tsx").read_text()
    route = text.index('<Route path="/product-items" element={<ProductItemsPage />} />')
    assert route < text.index("<ProtectedRoute />}>") < text.index('path="*"')
    assert '"/product_items/"' in (src / "api" / "product_item.ts").read_text()


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
