"""Tests for Next.js integration across config, presets, templates, and generators."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mattstack.config import FrontendFramework, ProjectConfig, ProjectType, Variant


def _nextjs_config(tmp_path: Path, **kwargs) -> ProjectConfig:
    defaults = {
        "name": "test-nextjs",
        "path": tmp_path / "test-nextjs",
        "project_type": ProjectType.FULLSTACK,
        "variant": Variant.STARTER,
        "frontend_framework": FrontendFramework.NEXTJS,
        "init_git": False,
    }
    defaults.update(kwargs)
    return ProjectConfig(**defaults)


def _nextjs_frontend_config(tmp_path: Path, **kwargs) -> ProjectConfig:
    defaults = {
        "name": "test-nextjs",
        "path": tmp_path / "test-nextjs",
        "project_type": ProjectType.FRONTEND_ONLY,
        "variant": Variant.STARTER,
        "frontend_framework": FrontendFramework.NEXTJS,
        "init_git": False,
    }
    defaults.update(kwargs)
    return ProjectConfig(**defaults)


# --- Config ---


class TestNextjsConfig:
    def test_nextjs_enum_exists(self) -> None:
        assert FrontendFramework.NEXTJS.value == "nextjs"

    def test_is_nextjs_property(self, tmp_path: Path) -> None:
        config = _nextjs_config(tmp_path)
        assert config.is_nextjs is True

    def test_is_nextjs_false_for_vite(self, tmp_path: Path) -> None:
        config = ProjectConfig(
            name="test",
            path=tmp_path / "test",
            frontend_framework=FrontendFramework.REACT_VITE,
            init_git=False,
        )
        assert config.is_nextjs is False

    def test_frontend_repo_key(self, tmp_path: Path) -> None:
        config = _nextjs_config(tmp_path)
        assert config.frontend_repo_key == "nextjs"

    def test_repo_url_exists(self) -> None:
        from mattstack.config import REPO_URLS

        assert "nextjs" in REPO_URLS
        assert "nextjs-starter" in REPO_URLS["nextjs"]


# --- Presets ---


class TestNextjsPresets:
    def test_nextjs_fullstack_preset(self) -> None:
        from mattstack.presets import get_preset

        preset = get_preset("nextjs-fullstack")
        assert preset is not None
        assert preset.project_type == ProjectType.FULLSTACK
        assert preset.frontend_framework == FrontendFramework.NEXTJS

    def test_nextjs_frontend_preset(self) -> None:
        from mattstack.presets import get_preset

        preset = get_preset("nextjs-frontend")
        assert preset is not None
        assert preset.project_type == ProjectType.FRONTEND_ONLY
        assert preset.frontend_framework == FrontendFramework.NEXTJS
        assert preset.use_celery is False

    def test_nextjs_preset_to_config(self, tmp_path: Path) -> None:
        from mattstack.presets import get_preset

        preset = get_preset("nextjs-fullstack")
        config = preset.to_config("my-next-app", tmp_path / "my-next-app")
        assert config.is_nextjs is True
        assert config.has_backend is True
        assert config.has_frontend is True


# --- Templates ---


class TestNextjsMakefile:
    def test_makefile_fullstack(self, tmp_path: Path) -> None:
        from mattstack.templates.root_makefile import generate_makefile

        config = _nextjs_config(tmp_path)
        mk = generate_makefile(config)
        assert "frontend-dev" in mk
        assert "backend-dev" in mk
        assert "bun run dev" in mk

    def test_makefile_frontend_only(self, tmp_path: Path) -> None:
        from mattstack.templates.root_makefile import generate_makefile

        config = _nextjs_frontend_config(tmp_path)
        mk = generate_makefile(config)
        assert "frontend-dev" in mk
        assert "backend-dev" not in mk


class TestNextjsDockerCompose:
    def test_docker_compose_nextjs(self, tmp_path: Path) -> None:
        from mattstack.templates.docker_compose import generate_docker_compose

        config = _nextjs_config(tmp_path)
        dc = generate_docker_compose(config)
        assert "frontend-dev" in dc
        assert "api-dev" in dc
        assert "NEXT_PUBLIC_API_BASE_URL" in dc
        assert "VITE_" not in dc

    def test_docker_compose_vite_unchanged(self, tmp_path: Path) -> None:
        from mattstack.templates.docker_compose import generate_docker_compose

        config = ProjectConfig(
            name="test",
            path=tmp_path / "test",
            init_git=False,
        )
        dc = generate_docker_compose(config)
        assert "VITE_API_BASE_URL" in dc


class TestNextjsEnv:
    def test_env_nextjs(self, tmp_path: Path) -> None:
        from mattstack.templates.root_env import generate_env_example

        config = _nextjs_config(tmp_path)
        env = generate_env_example(config)
        assert "NEXT_PUBLIC_API_BASE_URL" in env
        assert "VITE_" not in env

    def test_env_vite_unchanged(self, tmp_path: Path) -> None:
        from mattstack.templates.root_env import generate_env_example

        config = ProjectConfig(
            name="test",
            path=tmp_path / "test",
            init_git=False,
        )
        env = generate_env_example(config)
        assert "VITE_API_BASE_URL" in env


class TestNextjsReadme:
    def test_readme_nextjs(self, tmp_path: Path) -> None:
        from mattstack.templates.root_readme import generate_readme

        config = _nextjs_config(tmp_path)
        readme = generate_readme(config)
        assert "Next.js" in readme
        assert "App Router" in readme

    def test_readme_frontend_only(self, tmp_path: Path) -> None:
        from mattstack.templates.root_readme import generate_readme

        config = _nextjs_frontend_config(tmp_path)
        readme = generate_readme(config)
        assert "Next.js App" in readme


class TestNextjsAgentsMd:
    def test_agents_md_names_nextjs_api_variable(self, tmp_path: Path) -> None:
        from mattstack.templates.root_agents_md import generate_agents_md

        md = generate_agents_md(_nextjs_config(tmp_path))
        assert "Next.js" in md
        assert "NEXT_PUBLIC_API_BASE_URL" in md


# --- Post Processors ---


class TestNextjsFrontendConfig:
    def test_vite_monorepo_setup(self, tmp_path: Path) -> None:
        from mattstack.post_processors.frontend_config import setup_frontend_monorepo

        config = ProjectConfig(
            name="test",
            path=tmp_path / "test",
            init_git=False,
        )
        config.frontend_dir.mkdir(parents=True)
        setup_frontend_monorepo(config)
        env = (config.frontend_dir / ".env").read_text()
        assert "VITE_MODE" in env

    def test_nextjs_env_routes_the_browser_through_the_rewrite(self, tmp_path: Path) -> None:
        from mattstack.post_processors.frontend_config import setup_frontend_monorepo

        config = _nextjs_config(tmp_path)
        config.frontend_dir.mkdir(parents=True)
        setup_frontend_monorepo(config)
        env = (config.frontend_dir / ".env.local").read_text()
        assert f"NEXT_PUBLIC_API_BASE_URL={config.api_prefix}\n" in env
        assert f"INTERNAL_API_URL=http://localhost:{config.backend_api_port}\n" in env

    def test_nextjs_rewrite_follows_the_backend_api_prefix(self, tmp_path: Path) -> None:
        """nextjs-starter rewrites /api/v1; a backend mounted at /api needs /api."""
        from mattstack.post_processors.frontend_config import setup_frontend_monorepo

        config = _nextjs_config(tmp_path)
        config.frontend_dir.mkdir(parents=True)
        (config.frontend_dir / "next.config.ts").write_text(
            "const backendUrl = process.env.INTERNAL_API_URL;\n"
            'export default { rewrites: () => [{ source: "/api/v1/:path*",'
            " destination: `${backendUrl}/api/v1/:path*` }] };\n"
        )
        setup_frontend_monorepo(config)
        content = (config.frontend_dir / "next.config.ts").read_text()
        assert f'source: "{config.api_prefix}/:path*"' in content
        assert f"`${{backendUrl}}{config.api_prefix}/:path*`" in content
        assert not list(config.frontend_dir.glob("*.monorepo.*"))

    def test_next_public_env_reads_are_literal(self, tmp_path: Path) -> None:
        """Next inlines only `process.env.NEXT_PUBLIC_X`, never `process.env[key]`."""
        from mattstack.post_processors.frontend_config import setup_frontend_monorepo

        config = _nextjs_frontend_config(tmp_path)
        upstream = (
            "const getEnvVar = (key: string, defaultValue: string = ''): string => {\n"
            "  return process.env[key] || defaultValue;\n"
            "};\n"
            "export const config = {\n"
            "  baseUrl: getEnvVar('NEXT_PUBLIC_API_BASE_URL', 'http://localhost:8000/api/v1'),\n"
            "  mode: getEnvVar('NEXT_PUBLIC_MODE'),\n"
            "};\n"
        )
        (config.frontend_dir / "config").mkdir(parents=True)
        (config.frontend_dir / "config" / "index.ts").write_text(upstream)
        setup_frontend_monorepo(config)

        content = (config.frontend_dir / "config" / "index.ts").read_text()
        assert "process.env[key]" not in content
        assert "NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL," in content
        assert "NEXT_PUBLIC_MODE: process.env.NEXT_PUBLIC_MODE," in content
        assert content.index("const publicEnv") < content.index("const getEnvVar")
        assert "return publicEnv[key] || defaultValue;" in content

    def test_no_monorepo_for_frontend_only(self, tmp_path: Path) -> None:
        from mattstack.post_processors.frontend_config import setup_frontend_monorepo

        config = _nextjs_frontend_config(tmp_path)
        config.frontend_dir.mkdir(parents=True)
        setup_frontend_monorepo(config)
        assert not (config.frontend_dir / ".env.local").exists()


# --- Generator ---


class TestNextjsGenerator:
    @staticmethod
    def _mock_clone(url: str, dest: Path, branch: str = "main", depth: int = 1) -> bool:
        dest.mkdir(parents=True, exist_ok=True)
        if "django" in url:
            (dest / "pyproject.toml").write_text("[project]\nname = 'test'\n")
            (dest / "manage.py").write_text("#!/usr/bin/env python\n")
            (dest / "scripts").mkdir()
            (dest / "scripts" / "env_secrets.py").write_text(
                "import shutil, sys\na = sys.argv\n"
                "shutil.copy(a[a.index('--template') + 1], a[a.index('--env-file') + 1])\n"
            )
        elif "nextjs" in url:
            (dest / "package.json").write_text('{"name": "nextjs-starter"}\n')
            (dest / "app").mkdir()
            (dest / "app" / "page.tsx").write_text("export default function Home() {}")
        elif "react" in url:
            (dest / "package.json").write_text('{"name": "test"}\n')
            (dest / "src").mkdir()
        return True

    @patch("mattstack.generators.base.clone_repo")
    def test_fullstack_nextjs(self, mock_clone, tmp_path: Path) -> None:
        mock_clone.side_effect = self._mock_clone
        from mattstack.generators.fullstack import FullstackGenerator

        config = _nextjs_config(tmp_path)
        gen = FullstackGenerator(config)
        result = gen.run()
        assert result is True
        assert (config.path / "Makefile").exists()
        assert (config.path / "docker-compose.yml").exists()

        # Should have cloned nextjs, not react-vite
        clone_urls = [call.args[0] for call in mock_clone.call_args_list]
        assert any("nextjs" in url for url in clone_urls)
        assert not any("react-vite" in url for url in clone_urls)

    @patch("mattstack.generators.base.clone_repo")
    def test_frontend_only_nextjs(self, mock_clone, tmp_path: Path) -> None:
        mock_clone.side_effect = self._mock_clone
        from mattstack.generators.frontend_only import FrontendOnlyGenerator

        config = _nextjs_frontend_config(tmp_path)
        gen = FrontendOnlyGenerator(config)
        result = gen.run()
        assert result is True
        assert (config.path / "Makefile").exists()
