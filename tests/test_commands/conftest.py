"""Shared fixtures for command tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

URLS = """\
from django.urls import path
from ninja_extra import NinjaExtraAPI

api = NinjaExtraAPI()

api.register_controllers(
    HealthController,
)

urlpatterns = [
    path("api/", api.urls),
]
"""


def _make_project(
    root: Path, *, installed: tuple[str, ...] = ("core",), api_class: str = "NinjaExtraAPI"
) -> Path:
    """Write a minimal Ninja-extra backend and Rsbuild/TanStack frontend under *root*."""
    backend = root / "backend"
    (backend / "api").mkdir(parents=True)
    (backend / "api" / "__init__.py").write_text("")
    (backend / "api" / "urls.py").write_text(URLS.replace("NinjaExtraAPI", api_class))
    (backend / "api" / "settings.py").write_text(f"INSTALLED_APPS = {list(installed)!r}\n")
    (backend / "pyproject.toml").write_text(
        '[project]\ndependencies = ["django-ninja-extra", "django-ninja-jwt"]\n'
    )
    core = backend / "core"
    (core / "models").mkdir(parents=True)
    (core / "__init__.py").write_text("")
    (core / "apps.py").write_text(
        "from django.apps import AppConfig\n\n\nclass CoreConfig(AppConfig):\n    name = 'core'\n"
    )
    (core / "models" / "__init__.py").write_text("")
    (core / "models" / "category.py").write_text("class Category(models.Model):\n    pass\n")

    frontend = root / "frontend"
    (frontend / "src" / "api").mkdir(parents=True)
    (frontend / "src" / "routes").mkdir()
    deps = {
        "@rsbuild/core": "1",
        "@tanstack/react-query": "5",
        "@tanstack/react-router": "1",
        "axios": "1",
        "vitest": "3",
        "@testing-library/react": "16",
    }
    (frontend / "package.json").write_text(json.dumps({"dependencies": deps}))
    (frontend / "tsconfig.json").write_text('{"compilerOptions": {"paths": {"@/*": ["./src/*"]}}}')
    (frontend / "src" / "api" / "client.ts").write_text(
        'import axios from "axios"\nexport const apiClient = axios.create({ baseURL: "/api" })\n'
    )
    return root


@pytest.fixture
def make_project() -> Callable[..., Path]:
    return _make_project
