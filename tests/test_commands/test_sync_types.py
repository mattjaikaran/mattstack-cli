"""Tests for the Python to TypeScript type mapping.

These cover the mappings that broke on the real django-ninja boilerplate.
`make sync-types` writes invalid TypeScript whenever an annotation is not
mapped, and the failure only appears at `make frontend-typecheck`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mattstack.commands.codegen.ts_schemas import resolve_ts_type
from mattstack.parsers.python_enums import parse_enums_file
from mattstack.parsers.python_schemas import parse_pydantic_file, split_top_level_union


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
        # Ninja writes Decimal as a string, an orjson renderer as a number.
        ("Decimal", "number | string"),
        ("list[str | None]", "(string | null)[]"),
        # Literal values are TypeScript literal types, not bare identifiers.
        ("Literal['draft', 'live']", '"draft" | "live"'),
        ("Literal[1, None, True]", "1 | null | true"),
    ],
)
def test_type_mapping(python_type: str, expected: str) -> None:
    assert resolve_ts_type(python_type) == expected


def test_unknown_names_do_not_leak_into_typescript() -> None:
    assert resolve_ts_type("ThirdPartyThing", {"Known"}) == "unknown"
    assert resolve_ts_type("list[Known]", {"Known"}) == "Known[]"


def test_nullability_and_defaults_are_tracked_separately(tmp_path: Path) -> None:
    f = tmp_path / "schemas.py"
    f.write_text("""\
class ItemSchema(Schema):
    required_nullable: str | None
    optional_value: int = 0
    field_required: str = Field(..., min_length=1)
    field_default: str = Field("x")
    wrapped: Optional[list[str]] = None
    status: Literal["draft", "None"] | None = None
    parent: "ItemSchema | None" = None
""")
    fields = {f.name: f for f in parse_pydantic_file(f)[0].fields}
    assert (fields["required_nullable"].optional, fields["required_nullable"].has_default) == (
        True,
        False,
    )
    assert (fields["optional_value"].optional, fields["optional_value"].has_default) == (
        False,
        True,
    )
    assert fields["field_required"].has_default is False
    assert fields["field_default"].has_default is True
    assert (fields["wrapped"].type_str, fields["wrapped"].optional) == ("list[str]", True)
    # Literal strings keep their quotes; the string "None" is a value, not null.
    assert (fields["status"].type_str, fields["status"].optional) == (
        'Literal["draft", "None"]',
        True,
    )
    assert (fields["parent"].type_str, fields["parent"].optional) == ("ItemSchema", True)


def test_union_split_ignores_bracketed_bars() -> None:
    assert split_top_level_union("dict[str, bool | str]") == ["dict[str, bool | str]"]
    assert split_top_level_union("str | None") == ["str", "None"]


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
