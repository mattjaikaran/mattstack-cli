"""Tests for the context command: AI agent context dumper."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer

from mattstack.commands.context import run_context
from mattstack.commands.context_builders import (
    build_stack_context,
    detect_env_vars,
    detect_makefile_targets,
)
from mattstack.commands.context_format import format_context_claude, format_context_markdown
from mattstack.config import BackendFramework, FrontendFramework


def _make_fullstack(path: Path) -> Path:
    """Create a minimal fullstack project."""
    path.mkdir(parents=True, exist_ok=True)
    backend = path / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["django", "django-ninja", "celery"]\n'
    )
    frontend = path / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps(
            {
                "name": "test-frontend",
                "dependencies": {"react": "^18", "next": "^14", "tailwindcss": "^3"},
                "devDependencies": {},
                "scripts": {"dev": "next dev", "build": "next build", "lint": "eslint ."},
            }
        )
    )
    (path / "Makefile").write_text("setup:\n\techo setup\ntest:\n\techo test\n")
    (path / ".env.example").write_text(
        "DATABASE_URL=postgres://localhost/db\nSECRET_KEY=changeme\n"
    )
    (path / "docker-compose.yml").write_text("version: '3'\n")
    (path / "CLAUDE.md").write_text("# test\n")
    return path


class TestDetectComponents:
    def test_fullstack(self, tmp_path: Path) -> None:
        proj = _make_fullstack(tmp_path / "app")
        comps = build_stack_context(proj)["components"]
        assert comps["backend"] is True
        assert comps["frontend"] is True
        assert comps["docker"] is True
        assert comps["makefile"] is True
        assert comps["claude_md"] is True

    def test_empty(self, tmp_path: Path) -> None:
        comps = build_stack_context(tmp_path)["components"]
        assert all(v is False for v in comps.values())

    def test_nested_cwd_resolves_project_root(self, tmp_path: Path) -> None:
        proj = _make_fullstack(tmp_path / "app")
        nested = proj / "frontend" / "src"
        nested.mkdir()
        ctx = build_stack_context(nested)
        assert ctx["project_name"] == "app"
        assert ctx["components"]["backend"] is True


class TestDetectFrontendStack:
    def test_nextjs_detected(self, tmp_path: Path) -> None:
        proj = _make_fullstack(tmp_path / "app")
        stack = build_stack_context(proj)["frontend"]
        assert stack["framework"] == FrontendFramework.NEXTJS
        assert stack["bundler"] == "next"
        assert stack["ui_library"] == "react"
        assert stack["styling"] == "tailwind"
        assert "dev" in stack["scripts"]

    def test_backend_framework_from_resolver(self, tmp_path: Path) -> None:
        proj = _make_fullstack(tmp_path / "app")
        assert build_stack_context(proj)["backend"]["framework"] == BackendFramework.DJANGO_NINJA

    def test_spa_with_src_app_is_not_reported_as_nextjs(self, tmp_path: Path) -> None:
        proj = _make_fullstack(tmp_path / "app")
        frontend = proj / "frontend"
        (frontend / "package.json").write_text(
            json.dumps(
                {
                    "dependencies": {"react": "^19", "@tanstack/react-router": "^1"},
                    "devDependencies": {"vite": "^6"},
                }
            )
        )
        (frontend / "src" / "app" / "dashboard").mkdir(parents=True)
        (frontend / "src" / "app" / "dashboard" / "page.tsx").write_text("export default 1\n")
        (frontend / "src" / "routes").mkdir()
        (frontend / "src" / "routes" / "about.tsx").write_text(
            "export const Route = createFileRoute('/about')({ component: About })\n"
        )
        ctx = build_stack_context(proj)
        assert ctx["frontend"]["router"] == "tanstack-router"
        assert ctx["frontend"]["route_source"] == "frontend/src/routes"
        assert [(r["router"], r["path"]) for r in ctx["ui_routes"]] == [
            ("tanstack-router", "/about")
        ]

    def test_no_frontend(self, tmp_path: Path) -> None:
        assert "frontend" not in build_stack_context(tmp_path)


class TestNoSecretValues:
    def test_env_values_never_emitted(self, tmp_path: Path) -> None:
        proj = _make_fullstack(tmp_path / "app")
        (proj / ".env").write_text("SECRET_KEY=super-secret-value\n")
        text = json.dumps(build_stack_context(proj))
        assert "super-secret-value" not in text
        assert "changeme" not in text


class TestDetectEnvVars:
    def test_parses_env_example(self, tmp_path: Path) -> None:
        proj = _make_fullstack(tmp_path / "app")
        env_vars = detect_env_vars(proj)
        assert "DATABASE_URL" in env_vars
        assert "SECRET_KEY" in env_vars

    def test_empty(self, tmp_path: Path) -> None:
        assert detect_env_vars(tmp_path) == []


class TestDetectMakefileTargets:
    def test_parses_targets(self, tmp_path: Path) -> None:
        proj = _make_fullstack(tmp_path / "app")
        targets = detect_makefile_targets(proj)
        assert "setup" in targets
        assert "test" in targets

    def test_no_makefile(self, tmp_path: Path) -> None:
        assert detect_makefile_targets(tmp_path) == []


class TestBuildContext:
    def test_fullstack_context(self, tmp_path: Path) -> None:
        proj = _make_fullstack(tmp_path / "app")
        ctx = build_stack_context(proj)
        assert ctx["project_name"] == "app"
        assert ctx["components"]["backend"] is True
        assert "backend" in ctx
        assert "frontend" in ctx
        assert "env_vars" in ctx
        assert "makefile_targets" in ctx
        assert "tools" in ctx


class TestFormatContextMarkdown:
    def test_produces_markdown(self, tmp_path: Path) -> None:
        proj = _make_fullstack(tmp_path / "app")
        ctx = build_stack_context(proj)
        md = format_context_markdown(ctx)
        assert "# Project: app" in md
        assert "## Backend" in md
        assert "## Frontend" in md
        assert "## Environment Variables" in md
        assert "## Makefile Targets" in md


class TestRunContext:
    def test_json_output(self, tmp_path: Path, capsys) -> None:
        proj = _make_fullstack(tmp_path / "app")
        run_context(proj, json_output=True, output_file=str(tmp_path / "out.json"))
        content = (tmp_path / "out.json").read_text()
        data = json.loads(content)
        assert data["project_name"] == "app"

    def test_markdown_output_to_file(self, tmp_path: Path) -> None:
        proj = _make_fullstack(tmp_path / "app")
        run_context(proj, json_output=False, output_file=str(tmp_path / "out.md"))
        content = (tmp_path / "out.md").read_text()
        assert "# Project: app" in content

    def test_nonexistent_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit):
            run_context(tmp_path / "nope")


class TestMachineReadableStdout:
    def test_piped_json_with_long_path_parses(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from mattstack.cli import app

        proj = _make_fullstack(tmp_path / ("a" * 120) / "app")
        result = CliRunner().invoke(app, ["context", "stack", str(proj), "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["project_path"] == str(proj.resolve())

    def test_invalid_format_errors_on_stderr(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from mattstack.cli import app

        result = CliRunner().invoke(app, ["context", "stack", str(tmp_path), "-f", "yaml"])
        assert result.exit_code == 2
        assert result.stdout == ""
        assert "yaml" in result.stderr

    def test_claude_xml_escapes_attribute_values(self) -> None:
        import xml.etree.ElementTree as ET

        ctx = {
            "project_name": 'a"b&c',
            "project_path": "/tmp/<x>",
            "components": {},
            "interfaces": [
                {
                    "name": "Lookup",
                    "extends": None,
                    "fields": [
                        {"name": "items", "type": "Record<string, Item[]>", "optional": False}
                    ],
                }
            ],
        }
        root = ET.fromstring(format_context_claude(ctx))
        assert root.find("project").get("name") == 'a"b&c'  # type: ignore[union-attr]
        field = root.find("types/interface/field")
        assert field is not None
        assert field.get("type") == "Record<string, Item[]>"
