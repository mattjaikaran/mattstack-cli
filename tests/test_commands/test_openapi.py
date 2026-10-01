"""Protect project-owned files during optional OpenAPI generation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from mattstack.cli import app


def _project(path: Path) -> Path:
    binary = path / "frontend/node_modules/.bin/openapi-ts"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        f"#!{sys.executable}\n"
        "import argparse, json\n"
        "from pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('-i')\n"
        "parser.add_argument('-o')\n"
        "args = parser.parse_args()\n"
        "output = Path(args.o)\n"
        "output.mkdir(parents=True, exist_ok=True)\n"
        "title = json.loads(Path(args.i).read_text())['info']['title']\n"
        "(output / 'types.gen.ts').write_text(f'export const source = {title!r};\\n')\n"
    )
    binary.chmod(0o755)
    (path / "frontend/package.json").write_text('{"dependencies":{"react":"19.0.0"}}\n')
    _schema(path / "openapi.json", "Root")
    return path


def _schema(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {"openapi": "3.1.0", "info": {"title": title, "version": "1"}, "paths": {}}
    path.write_text(json.dumps(document))


def _ninja(path: Path) -> Path:
    project = _project(path)
    (project / "backend").mkdir()
    (project / "backend/manage.py").write_text("")
    (project / "backend/pyproject.toml").write_text('[project]\ndependencies = ["django-ninja"]\n')
    return project


def _generated(project: Path) -> str:
    return (project / "frontend/src/api/generated/types.gen.ts").read_text()


def test_openapi_reports_missing_ninja_export_with_command(tmp_path: Path) -> None:
    project = _ninja(tmp_path)
    result = CliRunner().invoke(app, ["sync", "openapi", "--path", str(project)])
    assert result.exit_code == 1
    assert "uv run python manage.py export_openapi" in result.output
    # The stale root file is never used silently for a Ninja backend.
    assert "--schema openapi.json" in result.output
    assert not (project / "frontend/src/api/generated").exists()


def test_openapi_uses_ninja_export_unless_schema_is_explicit(tmp_path: Path) -> None:
    project = _ninja(tmp_path)
    _schema(project / "backend/docs/openapi/openapi.json", "Ninja")

    discovered = CliRunner().invoke(app, ["sync", "openapi", "--path", str(project)])
    assert discovered.exit_code == 0, discovered.output
    assert _generated(project) == "export const source = 'Ninja';\n"

    explicit = CliRunner().invoke(
        app, ["sync", "openapi", "--path", str(project), "--schema", "openapi.json"]
    )
    assert explicit.exit_code == 0, explicit.output
    assert _generated(project) == "export const source = 'Root';\n"


def test_openapi_reports_missing_explicit_schema(tmp_path: Path) -> None:
    project = _ninja(tmp_path)
    _schema(project / "backend/docs/openapi/openapi.json", "Ninja")
    result = CliRunner().invoke(
        app, ["sync", "openapi", "--path", str(project), "--schema", "missing.json"]
    )
    assert result.exit_code == 1
    assert "from --schema" in result.output
    assert not (project / "frontend/src/api/generated").exists()


def test_openapi_refuses_unmanaged_output(tmp_path: Path) -> None:
    project = _project(tmp_path)
    output = project / "frontend/src/api/generated"
    output.mkdir(parents=True)
    owned = output / "client.ts"
    owned.write_text("export const handwritten = true;\n")
    result = CliRunner().invoke(app, ["sync", "openapi", "--path", str(project)])
    assert result.exit_code == 1
    assert owned.read_text() == "export const handwritten = true;\n"
    assert list(output.iterdir()) == [owned]


def test_openapi_refuses_output_outside_frontend(tmp_path: Path) -> None:
    project = _project(tmp_path)
    owned = project / "notes.txt"
    owned.write_text("Keep this file.\n")
    result = CliRunner().invoke(
        app, ["sync", "openapi", "--path", str(project), "--output", "..", "--force"]
    )
    assert result.exit_code == 1
    assert owned.read_text() == "Keep this file.\n"


def test_openapi_refuses_symlink_output(tmp_path: Path) -> None:
    project = _project(tmp_path)
    original = project / "frontend/owned"
    original.mkdir()
    owned = original / "client.ts"
    owned.write_text("export const handwritten = true;\n")
    linked = project / "frontend/generated"
    linked.symlink_to(original, target_is_directory=True)
    result = CliRunner().invoke(
        app, ["sync", "openapi", "--path", str(project), "--output", "generated", "--force"]
    )
    assert result.exit_code == 1
    assert linked.is_symlink()
    assert owned.read_text() == "export const handwritten = true;\n"
