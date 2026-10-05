"""Tests for post-processor modules."""

from __future__ import annotations

import json
from pathlib import Path

from mattstack.config import FrontendFramework, ProjectConfig, ProjectType, Variant
from mattstack.post_processors.b2b import print_b2b_instructions
from mattstack.post_processors.consolidate import consolidate_backend, consolidate_frontend
from mattstack.post_processors.customizer import customize_backend, customize_frontend
from mattstack.post_processors.frontend_config import setup_frontend_monorepo


def _make_config(tmp_path: Path, **kwargs) -> ProjectConfig:
    defaults = {
        "name": "test-proj",
        "path": tmp_path / "test-proj",
        "project_type": ProjectType.FULLSTACK,
        "variant": Variant.STARTER,
    }
    defaults.update(kwargs)
    return ProjectConfig(**defaults)


# --- setup_frontend_monorepo ---

_UPSTREAM_VITE_CONFIG = """\
import { tanstackRouter } from '@tanstack/router-plugin/vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [
    tanstackRouter({
      target: 'react',
      autoCodeSplitting: true,
    }),
    react(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
      '@/components': path.resolve(import.meta.dirname, './src/components'),
    },
  },
  server: {
    port: 5173,
    host: true,
  },
});
"""

_UPSTREAM_RSBUILD_CONFIG = """\
import { defineConfig } from '@rsbuild/core'
import { pluginReact } from '@rsbuild/plugin-react'
import { TanStackRouterRspack } from '@tanstack/router-plugin/rspack'

export default defineConfig({
  plugins: [pluginReact()],
  resolve: {
    alias: {
      '@': './src',
    },
  },
  tools: {
    rspack: {
      plugins: [TanStackRouterRspack()],
    },
  },
})
"""


def _frontend(config: ProjectConfig, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = config.frontend_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def test_frontend_env_points_the_browser_at_the_relative_api_prefix(tmp_path: Path) -> None:
    """An absolute localhost URL bypasses the proxy and breaks in the container."""
    config = _make_config(tmp_path)
    config.frontend_dir.mkdir(parents=True)
    setup_frontend_monorepo(config)

    content = (config.frontend_dir / ".env").read_text()
    assert "VITE_MODE=django-spa" in content
    assert f"VITE_API_BASE_URL={config.api_prefix}\n" in content


def test_rsbuild_env_uses_the_variable_the_app_reads(tmp_path: Path) -> None:
    """The Rsbuild boilerplates read PUBLIC_API_URL, not PUBLIC_API_BASE_URL."""
    config = _make_config(tmp_path, frontend_framework=FrontendFramework.REACT_RSBUILD)
    _frontend(config, {"rsbuild.config.ts": _UPSTREAM_RSBUILD_CONFIG})
    setup_frontend_monorepo(config)

    assert f"PUBLIC_API_URL={config.api_prefix}\n" in (config.frontend_dir / ".env").read_text()


def test_vite_proxy_is_added_to_the_config_dev_runs(tmp_path: Path) -> None:
    """Patch upstream's config in place; plugins and aliases must survive."""
    config = _make_config(tmp_path)
    _frontend(config, {"vite.config.ts": _UPSTREAM_VITE_CONFIG})
    setup_frontend_monorepo(config)

    content = (config.frontend_dir / "vite.config.ts").read_text()
    assert "tanstackRouter({" in content
    assert "'@/components': path.resolve(import.meta.dirname" in content
    assert "host: true" in content
    assert f"'{config.api_prefix}': {{ target: apiProxyTarget }}" in content
    assert "process.env.API_PROXY_TARGET" in content
    # Compose publishes ${FRONTEND_PORT:-3000}:3000, so 5173 is unreachable.
    assert "5173" not in content
    assert "FRONTEND_PORT ?? 3000" in content
    assert not list(config.frontend_dir.glob("*.monorepo.*"))


def test_dev_server_patch_is_idempotent(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    _frontend(config, {"vite.config.ts": _UPSTREAM_VITE_CONFIG})
    setup_frontend_monorepo(config)
    once = (config.frontend_dir / "vite.config.ts").read_text()
    setup_frontend_monorepo(config)
    assert (config.frontend_dir / "vite.config.ts").read_text() == once


def test_rsbuild_proxy_keeps_its_own_static_assets(tmp_path: Path) -> None:
    """Rsbuild serves bundles from /static/js; proxying /static breaks the app."""
    config = _make_config(tmp_path, frontend_framework=FrontendFramework.REACT_RSBUILD)
    _frontend(config, {"rsbuild.config.ts": _UPSTREAM_RSBUILD_CONFIG})
    setup_frontend_monorepo(config)

    content = (config.frontend_dir / "rsbuild.config.ts").read_text()
    assert "plugins: [TanStackRouterRspack()]" in content
    assert f"'{config.api_prefix}': {{ target: apiProxyTarget }}" in content
    assert "'/static/admin'" in content
    assert "'/static':" not in content


def test_tanstack_router_is_aligned_and_route_casts_removed(tmp_path: Path) -> None:
    """router-plugin 1.58.4 cannot load, and the newer router rejects `as any` ids."""
    config = _make_config(tmp_path)
    package = {
        "dependencies": {
            "@tanstack/react-router": "1.58.3",
            "@tanstack/router-devtools": "1.58.3",
        },
        "devDependencies": {"@tanstack/router-plugin": "1.58.4", "vite": "5.4.8"},
    }
    _frontend(
        config,
        {
            "package.json": json.dumps(package),
            "src/routes/dashboard/index.tsx": "createFileRoute('/dashboard' as any)({})\n",
            "src/routes/profile.tsx": "<Link to={'/settings' as any}>\n",
            "src/routes/__root.tsx": (
                "import { TanStackRouterDevtools } from '@tanstack/router-devtools';\n"
            ),
        },
    )
    setup_frontend_monorepo(config)

    data = json.loads((config.frontend_dir / "package.json").read_text())
    assert data["dependencies"]["@tanstack/react-router"] == "1.169.2"
    # The deprecated package has no release that fits the aligned router.
    assert "@tanstack/router-devtools" not in data["dependencies"]
    assert data["dependencies"]["@tanstack/react-router-devtools"] == "1.166.13"
    assert data["devDependencies"]["@tanstack/router-plugin"] == "1.167.34"
    assert data["devDependencies"]["vite"] == "5.4.8"
    routes = config.frontend_dir / "src" / "routes"
    assert (routes / "dashboard/index.tsx").read_text() == "createFileRoute('/dashboard/')({})\n"
    assert (routes / "profile.tsx").read_text() == '<Link to="/settings">\n'
    assert (routes / "__root.tsx").read_text() == (
        "import { TanStackRouterDevtools } from '@tanstack/react-router-devtools';\n"
    )


def test_tanstack_router_alignment_never_downgrades(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    package = {"dependencies": {"@tanstack/react-router": "1.170.0"}}
    _frontend(config, {"package.json": json.dumps(package)})
    setup_frontend_monorepo(config)

    data = json.loads((config.frontend_dir / "package.json").read_text())
    assert data["dependencies"]["@tanstack/react-router"] == "1.170.0"


def test_aligned_react_vite_source_is_left_unchanged(tmp_path: Path) -> None:
    """Tooling adoption must preserve the aligned router's versions and build order."""
    config = _make_config(tmp_path)
    package = json.dumps(
        {
            "scripts": {"build": "vite build && tsc -b"},
            "dependencies": {
                "@tanstack/react-router": "1.169.2",
                "@tanstack/react-router-devtools": "1.166.13",
            },
            "devDependencies": {"@tanstack/router-plugin": "1.167.34"},
        }
    )
    root = "import { TanStackRouterDevtools } from '@tanstack/react-router-devtools';\n"
    _frontend(config, {"package.json": package, "src/routes/__root.tsx": root})
    setup_frontend_monorepo(config)

    result = json.loads((config.frontend_dir / "package.json").read_text())
    original = json.loads(package)
    assert result["dependencies"] == original["dependencies"]
    assert result["devDependencies"]["@tanstack/router-plugin"] == "1.167.34"
    assert result["scripts"]["build"] == original["scripts"]["build"]
    assert (config.frontend_dir / "src/routes/__root.tsx").read_text() == root


_CUSTOM_ROUTES_VITE = (
    "import { tanstackRouter } from '@tanstack/router-plugin/vite'\n"
    "export default defineConfig({\n"
    "  plugins: [tanstackRouter({ routesDirectory: './app/pages', indexToken: 'home' })],\n"
    "})\n"
)


def test_route_casts_follow_the_configured_routes_directory(tmp_path: Path) -> None:
    """Casts are fixed where the plugin generates routes, with its index token."""
    config = _make_config(tmp_path)
    _frontend(
        config,
        {
            "vite.config.ts": _CUSTOM_ROUTES_VITE,
            "app/pages/reports/home.tsx": "createFileRoute('/reports' as any)({})\n",
        },
    )
    setup_frontend_monorepo(config)

    page = config.frontend_dir / "app/pages/reports/home.tsx"
    assert page.read_text() == "createFileRoute('/reports/')({})\n"


def test_route_casts_stay_when_the_plugin_config_cannot_be_read(tmp_path: Path) -> None:
    """A computed routesDirectory is never replaced by the src/routes default."""
    config = _make_config(tmp_path)
    vite = (
        "import { tanstackRouter } from '@tanstack/router-plugin/vite'\n"
        "export default defineConfig({ plugins: [tanstackRouter({ routesDirectory: dir })] })\n"
    )
    cast = "createFileRoute('/dashboard' as any)({})\n"
    _frontend(config, {"vite.config.ts": vite, "src/routes/dashboard/index.tsx": cast})
    setup_frontend_monorepo(config)

    assert (config.frontend_dir / "src/routes/dashboard/index.tsx").read_text() == cast


def test_react_router_starter_is_left_on_react_router(tmp_path: Path) -> None:
    """react-vite-starter uses react-router-dom by design."""
    config = _make_config(tmp_path, frontend_framework=FrontendFramework.REACT_VITE_STARTER)
    package = json.dumps({"dependencies": {"react-router-dom": "7.1.0"}})
    _frontend(config, {"package.json": package})
    setup_frontend_monorepo(config)

    result = json.loads((config.frontend_dir / "package.json").read_text())
    assert result["dependencies"] == {"react-router-dom": "7.1.0"}


def test_setup_frontend_monorepo_noop_for_backend_only(tmp_path: Path) -> None:
    config = _make_config(tmp_path, project_type=ProjectType.BACKEND_ONLY)
    config.path.mkdir(parents=True)
    setup_frontend_monorepo(config)

    # Should not create any files since there's no frontend
    env_file = config.frontend_dir / ".env"
    assert not env_file.exists()


def test_frontend_only_sets_the_port_without_a_proxy(tmp_path: Path) -> None:
    config = _make_config(tmp_path, project_type=ProjectType.FRONTEND_ONLY)
    _frontend(config, {"vite.config.ts": _UPSTREAM_VITE_CONFIG})
    setup_frontend_monorepo(config)

    content = (config.frontend_dir / "vite.config.ts").read_text()
    assert "FRONTEND_PORT ?? 3000" in content
    assert "proxy" not in content
    assert not (config.frontend_dir / ".env").exists()


# --- print_b2b_instructions ---


def test_print_b2b_instructions_runs_without_error(tmp_path: Path) -> None:
    config = _make_config(tmp_path, variant=Variant.B2B)
    # Should not raise any exception
    print_b2b_instructions(config)


def test_print_b2b_instructions_with_starter(tmp_path: Path) -> None:
    config = _make_config(tmp_path, variant=Variant.STARTER)
    # Should still work regardless of variant
    print_b2b_instructions(config)


# --- customize_backend ---


def test_customize_backend_updates_pyproject_name(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.backend_dir.mkdir(parents=True)

    pyproject = config.backend_dir / "pyproject.toml"
    pyproject.write_text('[project]\nname = "django-ninja-boilerplate"\n')

    customize_backend(config)

    content = pyproject.read_text()
    assert 'name = "test-proj-backend"' in content
    assert "django-ninja-boilerplate" not in content


def test_customize_backend_updates_python_package_name(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.backend_dir.mkdir(parents=True)

    pyproject = config.backend_dir / "pyproject.toml"
    pyproject.write_text('[project]\nname = "django_ninja_boilerplate"\n')

    customize_backend(config)

    content = pyproject.read_text()
    assert 'name = "test_proj_backend"' in content


def test_customize_backend_no_pyproject_is_noop(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.backend_dir.mkdir(parents=True)
    # Should not raise when pyproject.toml doesn't exist
    customize_backend(config)


def test_customize_backend_removes_cli_dir(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.backend_dir.mkdir(parents=True)

    cli_dir = config.backend_dir / "cli"
    cli_dir.mkdir()
    (cli_dir / "some_file.py").write_text("# placeholder")

    customize_backend(config)

    assert not cli_dir.exists()


# --- customize_frontend ---


def test_customize_frontend_updates_package_json(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.frontend_dir.mkdir(parents=True)

    package_json = config.frontend_dir / "package.json"
    package_json.write_text(json.dumps({"name": "react-boilerplate", "version": "0.1.0"}))

    customize_frontend(config)

    data = json.loads(package_json.read_text())
    assert data["name"] == "test-proj-frontend"
    assert data["version"] == "0.1.0"


def test_customize_frontend_no_package_json_is_noop(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.frontend_dir.mkdir(parents=True)
    # Should not raise when package.json doesn't exist
    customize_frontend(config)


# --- consolidate_monorepo ---


def _populate_backend_standalone(backend: Path) -> None:
    backend.mkdir(parents=True, exist_ok=True)
    for f in [
        "Makefile",
        "docker-compose.yml",
        "docker-compose.prod.yml",
        "docker-compose.single.yml",
        ".env",
        ".env.example",
        ".env.development",
        ".env.deploy.example",
        "Dockerfile",
        "Dockerfile.uv",
        "README.md",
        "CLAUDE.md",
        ".cursorrules",
        ".gitignore",
        ".dockerignore",
        ".pre-commit-config.yaml",
        "CHANGELOG.md",
    ]:
        (backend / f).write_text("x")
    for d in [
        "cli",
        "docker",
        "deploy",
        "nginx",
        "env",
        "media",
        "files",
        ".claude",
        ".cursor",
        ".vscode",
        ".omp",
        ".agents",
        ".continue",
        ".kiro",
        ".windsurf",
        ".tanstack",
    ]:
        (backend / d).mkdir(parents=True, exist_ok=True)
    # Files that must be preserved
    (backend / "pyproject.toml").write_text("[project]\n")
    (backend / "manage.py").write_text("x")
    (backend / "api").mkdir()
    (backend / "core").mkdir()


def _populate_frontend_standalone(frontend: Path) -> None:
    frontend.mkdir(parents=True, exist_ok=True)
    for f in [
        "Makefile",
        "docker-compose.yml",
        "docker-compose.monorepo.yml",
        ".env",
        ".env.example",
        "env.example",
        "env.monorepo.example",
        "Dockerfile",
        "Dockerfile.dev",
        "README.md",
        "CLAUDE.md",
        ".gitignore",
        ".dockerignore",
        "DEPLOYMENT.md",
        "nginx.conf",
    ]:
        (frontend / f).write_text("x")
    for d in ["nginx", "docs", "dist", ".claude", ".cursor", ".vscode", ".omp"]:
        (frontend / d).mkdir(parents=True, exist_ok=True)
    # Files that must be preserved
    (frontend / "package.json").write_text('{"name": "test"}\n')
    (frontend / "src").mkdir()
    (frontend / "vite.config.ts").write_text("export default {}")
    (frontend / "tsconfig.json").write_text("{}")
    (frontend / "eslint.config.js").write_text("export default []")
    (frontend / ".prettierrc").write_text("{}")


def test_consolidate_backend_removes_standalone_files(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    _populate_backend_standalone(config.backend_dir)

    consolidate_backend(config)

    for f in [
        "Makefile",
        "docker-compose.yml",
        "docker-compose.prod.yml",
        ".env",
        ".env.example",
        "Dockerfile",
        "Dockerfile.uv",
        "CLAUDE.md",
        ".gitignore",
        ".dockerignore",
        ".pre-commit-config.yaml",
    ]:
        assert not (config.backend_dir / f).exists(), f"{f} should be removed"
    for d in ["cli", "docker", "deploy", "nginx", "env", "media", "files", ".claude"]:
        assert not (config.backend_dir / d).exists(), f"{d}/ should be removed"
    # Canonical agent guidance stays: the gauntlet's cross-stack rules check
    # and scripts/export_rules.py read .omp/, and AGENTS.md names .agents/.
    for d in [".omp", ".agents"]:
        assert (config.backend_dir / d).is_dir(), f"{d}/ should be kept"
    for d in [".cursor", ".windsurf", ".kiro", ".continue"]:
        assert not (config.backend_dir / d).exists(), f"{d}/ adapter should be removed"
    assert (config.backend_dir / "pyproject.toml").exists()
    assert (config.backend_dir / "manage.py").exists()
    assert (config.backend_dir / "api").exists()
    assert (config.backend_dir / "core").exists()
    # backend/pyproject.toml declares readme = "README.md". Removing it makes
    # the package unbuildable, so consolidation must keep it.
    assert (config.backend_dir / "README.md").exists()


def test_consolidate_backend_keeps_optional_django_app(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    _populate_backend_standalone(config.backend_dir)
    app = config.backend_dir / "files"
    (app / "services").mkdir(parents=True)
    (app / "apps.py").write_text("class FilesConfig: ...\n")
    (app / "services" / "upload_service.py").write_text("x")

    consolidate_backend(config)

    assert (app / "apps.py").is_file()
    assert (app / "services" / "upload_service.py").is_file()
    assert not (config.backend_dir / "docker").exists()


def test_consolidate_frontend_removes_standalone_files(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    _populate_frontend_standalone(config.frontend_dir)

    consolidate_frontend(config)

    for f in [
        "Makefile",
        "docker-compose.yml",
        ".env",
        ".env.example",
        "env.example",
        "Dockerfile",
        "Dockerfile.dev",
        "CLAUDE.md",
        ".gitignore",
        ".dockerignore",
        "DEPLOYMENT.md",
        "nginx.conf",
    ]:
        assert not (config.frontend_dir / f).exists(), f"{f} should be removed"
    for d in ["nginx", "docs", "dist", ".claude"]:
        assert not (config.frontend_dir / d).exists(), f"{d}/ should be removed"
    assert (config.frontend_dir / ".omp").is_dir()
    assert (config.frontend_dir / "package.json").exists()
    assert (config.frontend_dir / "src").exists()
    assert (config.frontend_dir / "vite.config.ts").exists()
    assert (config.frontend_dir / "tsconfig.json").exists()
    assert (config.frontend_dir / "eslint.config.js").exists()
    assert (config.frontend_dir / ".prettierrc").exists()
    assert (config.frontend_dir / "README.md").exists()
