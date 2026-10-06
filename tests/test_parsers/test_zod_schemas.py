"""Tests for Zod schema parser."""

from __future__ import annotations

from pathlib import Path

from mattstack.parsers.zod_schemas import parse_zod_file


def test_simple_schema(tmp_path: Path) -> None:
    f = tmp_path / "schema.ts"
    f.write_text(
        "export const userSchema = z.object({\n"
        "  name: z.string(),\n"
        "  age: z.number(),\n"
        "  email: z.string().email(),\n"
        "});\n"
    )
    schemas = parse_zod_file(f)
    assert len(schemas) == 1
    assert schemas[0].name == "userSchema"
    assert len(schemas[0].fields) == 3
    assert schemas[0].fields[0].name == "name"
    assert schemas[0].fields[0].type_str == "string"


def test_optional_fields(tmp_path: Path) -> None:
    f = tmp_path / "schema.ts"
    f.write_text(
        "const schema = z.object({\n"
        "  name: z.string(),\n"
        "  bio: z.string().optional(),\n"
        "  avatar: z.string().nullable(),\n"
        "});\n"
    )
    schemas = parse_zod_file(f)
    fields = {f.name: f for f in schemas[0].fields}
    assert fields["name"].optional is False
    assert fields["bio"].optional is True
    assert (fields["avatar"].optional, fields["avatar"].nullable) == (False, True)


def test_constraints(tmp_path: Path) -> None:
    f = tmp_path / "schema.ts"
    f.write_text(
        "const schema = z.object({\n"
        "  name: z.string().min(2).max(50),\n"
        "  email: z.string().email(),\n"
        "});\n"
    )
    schemas = parse_zod_file(f)
    fields = {f.name: f for f in schemas[0].fields}
    assert "min" in fields["name"].constraints
    assert "max" in fields["name"].constraints
    assert "email" in fields["email"].constraints


def test_multiline_fields(tmp_path: Path) -> None:
    """Test that multiline chained methods are joined before parsing."""
    f = tmp_path / "schema.ts"
    f.write_text(
        "const schema = z.object({\n"
        "  email: z.string()\n"
        "    .email()\n"
        "    .min(3),\n"
        "  name: z.string(),\n"
        "});\n"
    )
    schemas = parse_zod_file(f)
    assert len(schemas[0].fields) == 2
    fields = {f.name: f for f in schemas[0].fields}
    assert fields["email"].type_str == "string"
    assert "email" in fields["email"].constraints


def test_multiple_schemas(tmp_path: Path) -> None:
    f = tmp_path / "schema.ts"
    f.write_text(
        "export const userSchema = z.object({\n"
        "  name: z.string(),\n"
        "});\n\n"
        "export const postSchema = z.object({\n"
        "  title: z.string(),\n"
        "  body: z.string(),\n"
        "});\n"
    )
    schemas = parse_zod_file(f)
    assert len(schemas) == 2
    assert schemas[0].name == "userSchema"
    assert schemas[1].name == "postSchema"


def test_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "empty.ts"
    f.write_text("// no schemas here\n")
    schemas = parse_zod_file(f)
    assert len(schemas) == 0
