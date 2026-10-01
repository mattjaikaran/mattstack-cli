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
# Endpoint auditor: django-matt controller recognition
# ---------------------------------------------------------------------------


def test_auditor_recognizes_django_matt_controllers(tmp_path: Path) -> None:
    from mattstack.auditors.base import AuditConfig
    from mattstack.auditors.endpoints import EndpointAuditor

    project = tmp_path
    backend = project / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text('[project]\ndependencies = ["django-matt>=0.9.0"]\n')

    ctrl_dir = backend / "apps" / "core" / "controllers"
    ctrl_dir.mkdir(parents=True)
    (ctrl_dir / "product.py").write_text(
        "from django_matt import APIController, get, post\n"
        "from django_matt.auth import JWTAuth\n\n"
        "class ProductController(APIController):\n"
        '    prefix = "/products"\n'
        '    tags = ["Products"]\n\n'
        '    @get("/")\n'
        "    def list_products(self, request):\n"
        "        return []\n\n"
        '    @post("/", auth=JWTAuth())\n'
        "    def create_product(self, request, payload):\n"
        "        return {}\n"
    )

    cfg = AuditConfig(project_path=project)
    auditor = EndpointAuditor(cfg)
    findings = auditor.run()
    # Should NOT raise — list (GET) without auth is fine, POST has auth
    auth_warnings = [
        f
        for f in findings
        if "No auth on write endpoint" in f.message and "products" in f.message.lower()
    ]
    assert len(auth_warnings) == 0


def test_auditor_flags_unauth_write_in_django_matt(tmp_path: Path) -> None:
    from mattstack.auditors.base import AuditConfig
    from mattstack.auditors.endpoints import EndpointAuditor

    project = tmp_path
    backend = project / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text('[project]\ndependencies = ["django-matt>=0.9.0"]\n')

    ctrl_dir = backend / "apps" / "core" / "controllers"
    ctrl_dir.mkdir(parents=True)
    (ctrl_dir / "widget.py").write_text(
        "from django_matt import APIController, post\n\n"
        "class WidgetController(APIController):\n"
        '    prefix = "/widgets"\n'
        '    tags = ["Widgets"]\n\n'
        '    @post("/")\n'
        "    def create_widget(self, request, payload):\n"
        "        return {}\n"
    )

    cfg = AuditConfig(project_path=project)
    auditor = EndpointAuditor(cfg)
    findings = auditor.run()
    auth_warnings = [f for f in findings if "No auth on write endpoint" in f.message]
    assert len(auth_warnings) >= 1
