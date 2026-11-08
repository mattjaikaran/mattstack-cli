"""Pin the OpenAPI client generator and document it alongside the frontend.

The boilerplate's ``check-dependencies`` gate reads every ``| name |`` row of
``DEPENDENCIES.md`` and requires one for each ``package.json`` dependency. A pin
written without a matching row makes a fresh scaffold fail that gate.
"""

from __future__ import annotations

import json
import re

from mattstack.config import ProjectConfig
from mattstack.parsers.openapi_spec import EXACT_VERSION, HEY_API_NAME, HEY_API_VERSION
from mattstack.utils.console import print_info
from mattstack.utils.package_json import write_package_json

_TABLE_SECTIONS = ("devDependencies", "dependencies")
_SEPARATOR_CELL = re.compile(r":?-+:?")


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
        target = row
    else:
        target = _insert_at(lines, newline)
        lines.insert(target, f"| {HEY_API_NAME} | {version} |{newline}")
    _align_table(lines, target)
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


def _table_cells(line: str) -> list[str] | None:
    """Split a Markdown table row into trimmed cells, else ``None`` for other lines."""
    text = line.strip()
    if len(text) < 2 or not text.startswith("|") or not text.endswith("|"):
        return None
    return [cell.strip() for cell in text[1:-1].split("|")]


def _align_table(lines: list[str], index: int) -> None:
    """Pad the table around ``index`` the way the frontend formatter expects.

    The boilerplates commit column-aligned tables and ``oxfmt --check`` (part of
    the frontend gauntlet) reports a row whose cells are padded differently.
    Leave single-space tables alone; only re-pad a table that is already aligned.
    """
    start = index
    while start > 0 and _table_cells(lines[start - 1]) is not None:
        start -= 1
    end = index
    while end + 1 < len(lines) and _table_cells(lines[end + 1]) is not None:
        end += 1

    rows = [_table_cells(line) for line in lines[start : end + 1]]
    table = [row for row in rows if row is not None]
    separator = next(
        (
            offset
            for offset, row in enumerate(table)
            if all(_SEPARATOR_CELL.fullmatch(cell) for cell in row)
        ),
        None,
    )
    if separator is None or any(len(row) != len(table[separator]) for row in table):
        return
    raw = [lines[position].strip()[1:-1].split("|") for position in range(start, end + 1)]
    if all(len(cell) == len(cell.strip()) + 2 for row in raw for cell in row):
        return

    widths = [
        max(3, *(len(row[column]) for offset, row in enumerate(table) if offset != separator))
        for column in range(len(table[separator]))
    ]
    for offset, row in enumerate(table):
        rendered = [
            _separator_cell(cell, widths[column])
            if offset == separator
            else cell.ljust(widths[column])
            for column, cell in enumerate(row)
        ]
        line = lines[start + offset]
        ending = line[len(line.rstrip("\r\n")) :]
        lines[start + offset] = "| " + " | ".join(rendered) + " |" + ending


def _separator_cell(marker: str, width: int) -> str:
    """Render an alignment separator cell at ``width``, keeping its colons."""
    if marker.startswith(":") and marker.endswith(":") and len(marker) > 1:
        return ":" + "-" * max(width - 2, 1) + ":"
    if marker.startswith(":"):
        return ":" + "-" * (width - 1)
    if marker.endswith(":"):
        return "-" * (width - 1) + ":"
    return "-" * width
