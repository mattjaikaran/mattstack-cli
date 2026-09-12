"""Tests for the Python to TypeScript type mapping.

These cover the mappings that broke on the real django-ninja boilerplate.
`make sync-types` writes invalid TypeScript whenever an annotation is not
mapped, and the failure only appears at `make frontend-typecheck`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mattstack.commands.sync import _resolve_ts_type, _split_top_level_union
from mattstack.parsers.python_schemas import parse_enums_file, parse_pydantic_file


@pytest.mark.parametrize(
    ("python_type", "expected"),
    [
        ("str", "string"),
        ("int", "number"),
        ("bool", "boolean"),
        ("UUID", "string"),
        # A module-qualified annotation must resolve like the bare name.
        ("uuid.UUID", "string"),
        ("datetime.datetime", "string"),
        ("EmailStr", "string"),
        ("Any", "unknown"),
        ("None", "null"),
        ("list[str]", "string[]"),
        ("dict[str, Any]", "Record<string, unknown>"),
        ("dict[str, Any] | None", "Record<string, unknown> | null"),
        # A bare container has no element type, and TS has no `list` name.
        ("list", "unknown[]"),
        ("dict", "Record<string, unknown>"),
        # A bar inside brackets belongs to the inner type.
        ("dict[str, bool | str]", "Record<string, boolean | string>"),
        ("list[dict[str, int]]", "Record<string, number>[]"),
    ],
)
def test_type_mapping(python_type: str, expected: str) -> None:
    assert _resolve_ts_type(python_type) == expected


def test_union_split_ignores_bracketed_bars() -> None:
    assert _split_top_level_union("dict[str, bool | str]") == ["dict[str, bool | str]"]
    assert _split_top_level_union("str | None") == ["str", "None"]


def test_enum_members_drop_trailing_comments(tmp_path: Path) -> None:
    """A value comment would otherwise become part of the emitted string."""
    f = tmp_path / "enums.py"
    f.write_text('''\
from enum import Enum


class FlagType(str, Enum):
    """Flag kinds."""

    BOOLEAN = "boolean"  # on/off toggle
    PERCENTAGE = "percentage"  # gradual rollout
''')
    enums = parse_enums_file(f)
    assert enums[0].name == "FlagType"
    assert enums[0].values == ["boolean", "percentage"]


def test_schema_subclass_of_a_local_base_is_parsed(tmp_path: Path) -> None:
    """Real schemas inherit a local base, not Schema or BaseModel directly."""
    f = tmp_path / "schemas.py"
    f.write_text("""\
from core.schemas.base_schema import CamelCaseSchema


class OrganizationSchema(CamelCaseSchema):
    id: str
    name: str
""")
    schemas = parse_pydantic_file(f)
    assert len(schemas) == 1
    assert {field.name for field in schemas[0].fields} == {"id", "name"}


def test_non_schema_class_is_ignored(tmp_path: Path) -> None:
    """A view or service class is not a schema."""
    f = tmp_path / "views.py"
    f.write_text("""\
from django.views import View


class OrganizationView(View):
    name: str
""")
    assert parse_pydantic_file(f) == []
