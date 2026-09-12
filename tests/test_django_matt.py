"""Tests for Phase 15A: django-matt backend support."""

from __future__ import annotations

from pathlib import Path

from mattstack.config import BackendFramework, ProjectConfig, ProjectType, Variant
from mattstack.presets import get_preset

# ---------------------------------------------------------------------------
# Config: BackendFramework enum
# ---------------------------------------------------------------------------


def test_backend_framework_enum_values() -> None:
    assert BackendFramework.DJANGO_NINJA.value == "django-ninja"
    assert BackendFramework.DJANGO_MATT.value == "django-matt"


def test_project_config_default_backend_framework(tmp_path: Path) -> None:
    config = ProjectConfig(name="test-app", path=tmp_path)
    assert config.backend_framework == BackendFramework.DJANGO_NINJA


def test_project_config_django_matt_framework(tmp_path: Path) -> None:
    config = ProjectConfig(
        name="test-app",
        path=tmp_path,
        backend_framework=BackendFramework.DJANGO_MATT,
    )
    assert config.backend_framework == BackendFramework.DJANGO_MATT
    assert config.is_django_matt is True


def test_project_config_django_ninja_not_django_matt(tmp_path: Path) -> None:
    config = ProjectConfig(name="test-app", path=tmp_path)
    assert config.is_django_matt is False


def test_backend_repo_key_django_ninja(tmp_path: Path) -> None:
    config = ProjectConfig(
        name="test-app",
        path=tmp_path,
        backend_framework=BackendFramework.DJANGO_NINJA,
    )
    assert config.backend_repo_key == "django-ninja"


def test_backend_repo_key_django_matt(tmp_path: Path) -> None:
    config = ProjectConfig(
        name="test-app",
        path=tmp_path,
        backend_framework=BackendFramework.DJANGO_MATT,
    )
    assert config.backend_repo_key == "django-matt"


# ---------------------------------------------------------------------------
# Config: REPO_URLS
# ---------------------------------------------------------------------------


def test_repo_urls_has_django_matt() -> None:
    from mattstack.config import REPO_URLS

    assert "django-matt" in REPO_URLS
    assert "boilerplate" in REPO_URLS["django-matt"]


# ---------------------------------------------------------------------------
# Presets: matt-api, matt-fullstack, matt-b2b-fullstack
# ---------------------------------------------------------------------------


def test_matt_api_preset_exists() -> None:
    preset = get_preset("matt-api")
    assert preset is not None
    assert preset.project_type == ProjectType.BACKEND_ONLY
    assert preset.backend_framework == BackendFramework.DJANGO_MATT
    assert preset.variant == Variant.STARTER


def test_matt_fullstack_preset_exists() -> None:
    preset = get_preset("matt-fullstack")
    assert preset is not None
    assert preset.project_type == ProjectType.FULLSTACK
    assert preset.backend_framework == BackendFramework.DJANGO_MATT
    assert preset.variant == Variant.STARTER


def test_matt_b2b_fullstack_preset_exists() -> None:
    preset = get_preset("matt-b2b-fullstack")
    assert preset is not None
    assert preset.project_type == ProjectType.FULLSTACK
    assert preset.backend_framework == BackendFramework.DJANGO_MATT
    assert preset.variant == Variant.B2B


def test_matt_api_preset_to_config(tmp_path: Path) -> None:
    preset = get_preset("matt-api")
    assert preset is not None
    config = preset.to_config("my-api", tmp_path / "my-api")
    assert config.backend_framework == BackendFramework.DJANGO_MATT
    assert config.is_django_matt is True
    assert config.backend_repo_key == "django-matt"


def test_existing_presets_unaffected() -> None:
    """Existing presets should still default to django-ninja."""
    for name in ("starter-fullstack", "b2b-fullstack", "starter-api", "b2b-api"):
        preset = get_preset(name)
        assert preset is not None
        assert preset.backend_framework == BackendFramework.DJANGO_NINJA, (
            f"Preset '{name}' should default to django-ninja"
        )


# ---------------------------------------------------------------------------
# Generate: django-matt code generators
# ---------------------------------------------------------------------------


def test_generate_django_matt_controller_imports() -> None:
    from mattstack.commands.generate import _generate_django_matt_controller

    fields = [("title", "str", None), ("price", "decimal", None)]
    code = _generate_django_matt_controller("Product", fields, "core")
    assert "from django_matt import APIController" in code
    assert "from django_matt.auth import JWTAuth" in code
    assert "class ProductController(APIController):" in code
    assert 'prefix = "/products"' in code


def test_generate_django_matt_controller_crud_methods() -> None:
    from mattstack.commands.generate import _generate_django_matt_controller

    code = _generate_django_matt_controller("Product", [("title", "str", None)], "core")
    assert "@get(" in code
    assert "@post(" in code
    assert "@put(" in code
    assert "@delete(" in code
    assert "def list_products" in code
    assert "def get_product" in code
    assert "def create_product" in code
    assert "def update_product" in code
    assert "def delete_product" in code


def test_generate_django_matt_controller_search_uses_str_field() -> None:
    from mattstack.commands.generate import _generate_django_matt_controller

    fields = [("title", "str", None), ("price", "decimal", None)]
    code = _generate_django_matt_controller("Product", fields, "core")
    assert "title__icontains=search" in code


def test_generate_django_matt_controller_no_str_field_fallback() -> None:
    from mattstack.commands.generate import _generate_django_matt_controller

    code = _generate_django_matt_controller("Product", [("price", "decimal", None)], "core")
    assert "id__icontains=search" in code


def test_generate_django_matt_service() -> None:
    from mattstack.commands.generate import _generate_django_matt_service

    code = _generate_django_matt_service("Product", [("title", "str", None)], "core")
    assert "from django_matt.services import CRUDService" in code
    assert "class ProductService(CRUDService):" in code
    assert "model = Product" in code
    assert "create_schema = ProductCreateSchema" in code
    assert "response_schema = ProductResponseSchema" in code
    assert 'search_fields = ["title"]' in code


def test_generate_django_matt_service_no_str_field() -> None:
    from mattstack.commands.generate import _generate_django_matt_service

    code = _generate_django_matt_service("Product", [("price", "decimal", None)], "core")
    assert "search_fields: list[str] = []" in code


def test_generate_django_matt_endpoint_method() -> None:
    from mattstack.commands.generate import _generate_django_matt_endpoint_method

    code = _generate_django_matt_endpoint_method("/products", "GET", False)
    assert "@get(" in code
    assert "def products" in code


def test_generate_django_matt_endpoint_method_with_auth() -> None:
    from mattstack.commands.generate import _generate_django_matt_endpoint_method

    code = _generate_django_matt_endpoint_method("/products", "POST", True)
    assert "auth=JWTAuth()" in code


def test_generate_django_matt_controller_file() -> None:
    from mattstack.commands.generate import (
        _generate_django_matt_controller_file,
        _generate_django_matt_endpoint_method,
    )

    method = _generate_django_matt_endpoint_method("/products", "GET", False)
    code = _generate_django_matt_controller_file("products", method, False)
    assert "from django_matt import APIController" in code
    assert "class ProductsController(APIController):" in code
    assert 'prefix = "/productss"' in code


# ---------------------------------------------------------------------------
# Generate model command: django-matt detection path
# ---------------------------------------------------------------------------


def test_model_command_generates_django_matt_files(tmp_path: Path) -> None:
    """generate model should write CRUDService when django-matt detected."""
    from typer.testing import CliRunner

    from mattstack.commands.generate import generate_app

    # Set up a fake project with django-matt in pyproject
    backend = tmp_path / "backend"
    (backend / "apps" / "core" / "models").mkdir(parents=True)
    (backend / "pyproject.toml").write_text('[project]\ndependencies = ["django-matt>=0.9.0"]\n')

    runner = CliRunner()
    result = runner.invoke(
        generate_app,
        ["model", "Widget", "--fields", "name:str", "--path", str(tmp_path), "--dry-run"],
    )
    assert result.exit_code == 0
    assert "django-matt" in result.output


def test_model_command_dry_run_shows_ninja_extra_by_default(tmp_path: Path) -> None:
    """generate model dry-run should show ninja-extra when no django-matt detected."""
    from typer.testing import CliRunner

    from mattstack.commands.generate import generate_app

    backend = tmp_path / "backend"
    (backend / "apps" / "core" / "models").mkdir(parents=True)
    (backend / "pyproject.toml").write_text('[project]\ndependencies = ["django-ninja>=1.0"]\n')

    runner = CliRunner()
    result = runner.invoke(
        generate_app,
        ["model", "Widget", "--fields", "name:str", "--path", str(tmp_path), "--dry-run"],
    )
    assert result.exit_code == 0
    assert "ninja-extra" in result.output
