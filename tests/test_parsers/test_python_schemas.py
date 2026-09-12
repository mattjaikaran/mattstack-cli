"""Tests for Pydantic schema parser."""

from __future__ import annotations

from pathlib import Path

from mattstack.parsers.python_schemas import parse_pydantic_file


def test_parse_basic_schema(tmp_path: Path) -> None:
    f = tmp_path / "schemas.py"
    f.write_text("""\
from ninja import Schema

class UserSchema(Schema):
    name: str
    email: str
    age: int
    is_active: bool = True
""")
    schemas = parse_pydantic_file(f)
    assert len(schemas) == 1
    assert schemas[0].name == "UserSchema"
    assert len(schemas[0].fields) == 4
    names = [field.name for field in schemas[0].fields]
    assert "name" in names
    assert "email" in names
    assert "age" in names
    assert "is_active" in names


def test_parse_optional_fields(tmp_path: Path) -> None:
    f = tmp_path / "schemas.py"
    f.write_text("""\
from typing import Optional
from ninja import Schema

class ProfileSchema(Schema):
    bio: Optional[str]
    avatar: str | None
    website: str
""")
    schemas = parse_pydantic_file(f)
    assert len(schemas) == 1
    fields = {field.name: field for field in schemas[0].fields}
    assert fields["bio"].optional is True
    assert fields["avatar"].optional is True
    assert fields["website"].optional is False


def test_parse_field_constraints(tmp_path: Path) -> None:
    f = tmp_path / "schemas.py"
    f.write_text("""\
from pydantic import BaseModel, Field

class RegisterSchema(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)
""")
    schemas = parse_pydantic_file(f)
    assert len(schemas) == 1
    fields = {field.name: field for field in schemas[0].fields}
    assert "min_length" in fields["username"].constraints
    assert "max_length" in fields["username"].constraints
    assert fields["username"].constraints["min_length"] == "3"


def test_parse_multiple_schemas(tmp_path: Path) -> None:
    f = tmp_path / "schemas.py"
    f.write_text("""\
from ninja import Schema

class UserSchema(Schema):
    name: str

class TodoSchema(Schema):
    title: str
    done: bool
""")
    schemas = parse_pydantic_file(f)
    assert len(schemas) == 2
    names = {s.name for s in schemas}
    assert names == {"UserSchema", "TodoSchema"}


def test_parse_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty.py"
    f.write_text("# no schemas here\n")
    schemas = parse_pydantic_file(f)
    assert schemas == []


def test_parse_field_alias(tmp_path: Path) -> None:
    f = tmp_path / "schemas.py"
    f.write_text("""\
from pydantic import BaseModel, Field

class UserSchema(BaseModel):
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    email: str
""")
    schemas = parse_pydantic_file(f)
    fields = {field.name: field for field in schemas[0].fields}
    assert fields["first_name"].alias == "firstName"
    assert fields["first_name"].api_name == "firstName"
    assert fields["last_name"].alias == "lastName"
    assert fields["email"].alias is None
    assert fields["email"].api_name == "email"


def test_parse_serialization_alias(tmp_path: Path) -> None:
    f = tmp_path / "schemas.py"
    f.write_text("""\
from pydantic import BaseModel, Field

class UserSchema(BaseModel):
    user_id: int = Field(serialization_alias="userId")
    display_name: str = Field(validation_alias="displayName")
""")
    schemas = parse_pydantic_file(f)
    fields = {field.name: field for field in schemas[0].fields}
    assert fields["user_id"].serialization_alias == "userId"
    assert fields["user_id"].api_name == "userId"
    assert fields["display_name"].validation_alias == "displayName"
    assert fields["display_name"].input_name == "displayName"
    # api_name falls back to field name when no serialization alias
    assert fields["display_name"].api_name == "display_name"


def test_parse_alias_with_constraints(tmp_path: Path) -> None:
    f = tmp_path / "schemas.py"
    f.write_text("""\
from pydantic import BaseModel, Field

class RegisterSchema(BaseModel):
    user_name: str = Field(alias="userName", min_length=3, max_length=50)
""")
    schemas = parse_pydantic_file(f)
    fields = {field.name: field for field in schemas[0].fields}
    assert fields["user_name"].alias == "userName"
    assert fields["user_name"].constraints["min_length"] == "3"
    assert fields["user_name"].constraints["max_length"] == "50"
    # alias should NOT be in constraints
    assert "alias" not in fields["user_name"].constraints


def test_parse_alias_generator(tmp_path: Path) -> None:
    f = tmp_path / "schemas.py"
    f.write_text("""\
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

class UserSchema(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    first_name: str
    last_name: str
""")
    schemas = parse_pydantic_file(f)
    assert schemas[0].alias_generator == "to_camel"


def test_field_api_name_priority(tmp_path: Path) -> None:
    """serialization_alias > alias > name."""
    f = tmp_path / "schemas.py"
    f.write_text("""\
from pydantic import BaseModel, Field

class TestSchema(BaseModel):
    field_a: str = Field(alias="a", serialization_alias="out_a")
    field_b: str = Field(alias="b")
    field_c: str
""")
    schemas = parse_pydantic_file(f)
    fields = {field.name: field for field in schemas[0].fields}
    assert fields["field_a"].api_name == "out_a"
    assert fields["field_b"].api_name == "b"
    assert fields["field_c"].api_name == "field_c"


def test_field_input_name_priority(tmp_path: Path) -> None:
    """validation_alias > alias > name."""
    f = tmp_path / "schemas.py"
    f.write_text("""\
from pydantic import BaseModel, Field

class TestSchema(BaseModel):
    field_a: str = Field(alias="a", validation_alias="in_a")
    field_b: str = Field(alias="b")
    field_c: str
""")
    schemas = parse_pydantic_file(f)
    fields = {field.name: field for field in schemas[0].fields}
    assert fields["field_a"].input_name == "in_a"
    assert fields["field_b"].input_name == "b"
    assert fields["field_c"].input_name == "field_c"


def test_docstring_is_not_parsed_as_fields(tmp_path: Path) -> None:
    """A class docstring must not become fields.

    Regression: the django-ninja boilerplate documents its base schema with a
    docstring containing ``alias_generator=to_camel`` and indented
    ``key: value`` lines. Those parsed as fields, and `mattstack sync types`
    emitted invalid TypeScript that failed the frontend type-check.
    """
    f = tmp_path / "base_schema.py"
    f.write_text('''\
from pydantic import ConfigDict
from ninja import Schema
from pydantic.alias_generators import to_camel


class CamelCaseSchema(Schema):
    """Base schema with automatic camelCase aliases.

    Features:
        - ``alias_generator=to_camel``: field ``first_name`` -> key ``firstName``
        - ``populate_by_name=True``: input accepts both casings

    Usage::

        class UserSchema(CamelCaseSchema):
            first_name: str
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
''')
    schemas = parse_pydantic_file(f)
    assert len(schemas) == 1
    assert schemas[0].name == "CamelCaseSchema"
    # The docstring is documentation, so the base class carries no fields.
    assert schemas[0].fields == []
    # The real config line still supplies the alias generator.
    assert schemas[0].alias_generator == "to_camel"


def test_fields_are_parsed_around_a_docstring(tmp_path: Path) -> None:
    """A docstring must not hide the real fields that follow it."""
    f = tmp_path / "schemas.py"
    f.write_text('''\
from pydantic import BaseModel


class ItemSchema(BaseModel):
    """An item.

    Attributes:
        name: the label
    """

    name: str
    count: int
''')
    schemas = parse_pydantic_file(f)
    assert {field.name for field in schemas[0].fields} == {"name", "count"}
