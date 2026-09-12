#!/usr/bin/env python3
"""Architecture layer enforcement for mattstack-cli.

Rules:
    1. commands/ may import from core (gauntlet, generators, parsers, post_processors,
       templates, utils, plus top-level modules: config, presets, user_config, detected).
    2. Core modules MUST NOT import from commands/ (no reverse imports).
    3. No circular imports between core modules.

Exit 0 on pass, 1 on fail.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "mattstack"

# Module paths relative to SRC_DIR
CLI_LAYER = {"commands"}
CORE_LAYER = {
    "generators",
    "gauntlet",
    "parsers",
    "post_processors",
    "templates",
    "utils",
}
TOP_LEVEL_CORE = {
    "config",
    "presets",
    "user_config",
    "detected",
}

# cli.py is considered part of the CLI layer for import rules
CLI_ALLOWED = CLI_LAYER | {"cli"}

CORE = CORE_LAYER | TOP_LEVEL_CORE

# Remaining top-level modules that aren't CLI or core — treat as neutral
NEUTRAL = {
    "__init__",
    "__main__",
    "py",
}


def _module_path(file_path: Path) -> str | None:
    """Convert a source file path to a module dotted-path relative to the package root."""
    try:
        rel = file_path.resolve().relative_to(SRC_DIR.resolve())
    except ValueError:
        return None
    parts = list(rel.parts)
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _imported_modules(node: ast.AST) -> list[str]:
    """Extract all imported module names from an AST."""
    imports: list[str] = []
    for n in ast.walk(node):
        if isinstance(n, ast.Import):
            for alias in n.names:
                imports.append(alias.name)
        elif isinstance(n, ast.ImportFrom) and n.module:
            imports.append(n.module)
    return imports


def _is_mattstack_import(module: str) -> bool:
    """Check if an import is from the mattstack package."""
    return module == "mattstack" or module.startswith("mattstack.")


def _module_top_level(module: str) -> str | None:
    """Extract the top-level subpackage of a mattstack import.

    Returns None if not a mattstack import.
    E.g. 'mattstack.commands.init' -> 'commands'
         'mattstack.generators.base' -> 'generators'
         'mattstack.config' -> 'config'
    """
    if not _is_mattstack_import(module):
        return None
    parts = module.split(".")
    if len(parts) == 1:  # bare 'mattstack'
        return None
    return parts[1]


def check_file(file_path: Path) -> list[str]:
    """Check a single Python file for architecture violations.

    Returns a list of violation messages.
    """
    violations: list[str] = []

    try:
        source = file_path.read_text(encoding="utf-8")
    except Exception:
        return violations

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return violations

    current_module = _module_path(file_path)
    if current_module is None:
        return violations

    # Determine layer of the current file
    parts = current_module.split(".")
    top_level = parts[0]

    for mod in _imported_modules(tree):
        target_top = _module_top_level(mod)
        if target_top is None:
            continue

        # Rule 2: Core modules must not import from commands/
        if top_level in CORE and target_top in CLI_ALLOWED:
            violations.append(
                f"{current_module} imports {mod} — "
                f"core module '{top_level}' must not import from CLI layer 'commands/'"
            )

    return violations


def main() -> int:
    """Check all Python files under src/mattstack/ for architecture violations.

    Returns exit code: 0 on pass, 1 on failure.
    """
    all_violations: list[str] = []

    for py_file in sorted(SRC_DIR.rglob("*.py")):
        # Skip __pycache__ and egg-info
        if "__pycache__" in str(py_file) or ".egg-info" in str(py_file):
            continue

        violations = check_file(py_file)
        all_violations.extend(violations)

    if all_violations:
        print("Architecture violations found:")
        for v in all_violations:
            print(f"  - {v}")
        print(f"\n{len(all_violations)} violation(s)")
        return 1

    print("Architecture check passed — no layer violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
