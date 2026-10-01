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
        "import argparse\n"
        "from pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('-i')\n"
        "parser.add_argument('-o')\n"
        "args = parser.parse_args()\n"
        "output = Path(args.o)\n"
        "output.mkdir(parents=True, exist_ok=True)\n"
        "(output / 'types.gen.ts').write_text('export type Response = { name: string };\\n')\n"
    )
    binary.chmod(0o755)
    (path / "frontend/package.json").write_text('{"dependencies":{"react":"19.0.0"}}\n')
    (path / "openapi.json").write_text(
        json.dumps({"openapi": "3.1.0", "info": {"title": "Test", "version": "1"}, "paths": {}})
    )
    return path


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
