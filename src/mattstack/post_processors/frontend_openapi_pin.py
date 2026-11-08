"""Pin the OpenAPI client generator and document it alongside the frontend.

The boilerplate's ``check-dependencies`` gate reads every ``| name |`` row of
``DEPENDENCIES.md`` and requires one for each ``package.json`` dependency. A pin
written without a matching row makes a fresh scaffold fail that gate.
"""

from __future__ import annotations

import json

from mattstack.config import ProjectConfig
from mattstack.parsers.openapi_spec import EXACT_VERSION, HEY_API_NAME, HEY_API_VERSION
from mattstack.utils.console import print_info
from mattstack.utils.package_json import write_package_json

_TABLE_SECTIONS = ("devDependencies", "dependencies")


def pin_openapi_generator(config: ProjectConfig) -> None:
    """Pin the OpenAPI client generator exactly, so `mattstack sync check` is reproducible.

    An existing exact pin is the frontend's choice and stays; a range or a
    missing entry becomes the version mattstack's parity audit is verified with.
    The exact version in ``package.json`` is then documented in ``DEPENDENCIES.md``
    when that file exists.
    """
    manifest = config.frontend_dir / "package.json"
    if not manifest.is_file():
        return
    package = json.loads(manifest.read_text())
    owned = [name for name in _TABLE_SECTIONS if HEY_API_NAME in package.get(name, {})]
    section = owned[0] if owned else _TABLE_SECTIONS[0]
    entries = package.setdefault(section, {})
    current = entries.get(HEY_API_NAME)
    if isinstance(current, str) and EXACT_VERSION.fullmatch(current):
        _document_dependency(config)
        return
    entries[HEY_API_NAME] = HEY_API_VERSION
    write_package_json(manifest, package)
    print_info(f"Pinned {HEY_API_NAME} to {HEY_API_VERSION} in frontend/package.json")
    _document_dependency(config)


def _document_dependency(config: ProjectConfig) -> None:
    """Record the pinned generator in ``DEPENDENCIES.md``, if the boilerplate has one."""
    path = config.frontend_dir / "DEPENDENCIES.md"
    manifest = config.frontend_dir / "package.json"
    if not path.is_file() or not manifest.is_file():
        return
    package = json.loads(manifest.read_text())
    version = next(
        (
            package[section][HEY_API_NAME]
            for section in _TABLE_SECTIONS
            if isinstance(package.get(section, {}).get(HEY_API_NAME), str)
        ),
        None,
    )
    if version is None:
        return

    text = path.read_text()
    lines = text.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in text else "\n"
    row = next(
        (index for index, line in enumerate(lines) if _row_name(line) == HEY_API_NAME),
        None,
    )
    if row is not None:
        lines[row] = _replace_version(lines[row], version)
    else:
        lines.insert(_insert_at(lines, newline), f"| {HEY_API_NAME} | {version} |{newline}")
    path.write_text("".join(lines))


def _row_name(line: str) -> str | None:
    """Return the package name of a two-column Markdown table row, else ``None``."""
    text = line.rstrip("\r\n")
    if not text.startswith("|") or not text.endswith("|"):
        return None
    cells = text.split("|")[1:-1]
    if len(cells) != 2:
        return None
    name = cells[0].strip()
    if not name or set(name) == {"-"} or name.lower() == "package":
        return None
    return name


def _replace_version(line: str, version: str) -> str:
    """Replace only the version cell, leaving the name cell and line ending intact."""
    text = line.rstrip("\r\n")
    ending = line[len(text) :]
    cells = text.split("|")
    cells[-2] = f" {version} "
    return "|".join(cells) + ending


def _insert_at(lines: list[str], newline: str) -> int:
    """Find the sorted position for the generator row among the table's data rows."""
    last_row = None
    for index, line in enumerate(lines):
        name = _row_name(line)
        if name is None:
            continue
        last_row = index
        if name > HEY_API_NAME:
            return index
    if last_row is None:
        return len(lines)
    if not lines[last_row].endswith(("\n", "\r")):
        lines[last_row] += newline
    return last_row + 1
