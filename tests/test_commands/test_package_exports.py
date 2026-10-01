"""Preserve package export behavior during generation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from mattstack.commands.codegen.backend_layout import GenerateError
from mattstack.commands.codegen.package_exports import export_names, plan_exports
from mattstack.commands.codegen.plan import FilePlan


def test_extended_exports_remain_importable_and_idempotent(tmp_path: Path) -> None:
    package = tmp_path / "export_fixture"
    package.mkdir()
    (package / "existing.py").write_text("class Existing:\n    pass\n")
    (package / "product.py").write_text("class Product:\n    pass\n")
    init = package / "__init__.py"
    original = 'from .existing import Existing\n\n__all__ = ["Existing"  # Keep this export\n]\n'
    extended = export_names(original, init, ".product", ["Product"])
    init.write_text(extended)
    assert export_names(extended, init, ".product", ["Product"]) == extended
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from export_fixture import *; "
            "assert {k for k in globals() if not k.startswith('_')} == {'Existing', 'Product'}",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_dynamic_exports_refuse_generation_without_mutation(tmp_path: Path) -> None:
    init = tmp_path / "__init__.py"
    original = '__all__ = ["Existing"] + other.__all__\n'
    init.write_text(original)
    plan = FilePlan(tmp_path)
    with pytest.raises(GenerateError):
        plan_exports(plan, init, ".product", ["Product"])
    assert not plan.creates and not plan.updates
    assert init.read_text() == original
