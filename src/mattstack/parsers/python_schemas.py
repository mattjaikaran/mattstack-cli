"""Parse Pydantic Schema/BaseModel classes from Python files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PydanticField:
    name: str
    type_str: str
    optional: bool = False
    default: str | None = None
    constraints: dict[str, str] = field(default_factory=dict)
    alias: str | None = None
    serialization_alias: str | None = None
    validation_alias: str | None = None

    @property
    def api_name(self) -> str:
        """The field name as it appears in API responses (serialization).

        Priority: serialization_alias > alias > name.
        """
        return self.serialization_alias or self.alias or self.name

    @property
    def input_name(self) -> str:
        """The field name expected in API requests (validation).

        Priority: validation_alias > alias > name.
        """
        return self.validation_alias or self.alias or self.name


@dataclass
class PydanticSchema:
    name: str
    file: Path
    line: int
    fields: list[PydanticField] = field(default_factory=list)
    parent: str | None = None
    alias_generator: str | None = None  # e.g. "to_camel", "to_pascal"


# Pattern: class Name(Schema): or class Name(BaseModel):
CLASS_RE = re.compile(
    r"^class\s+(\w+)\s*\(\s*(Schema|BaseModel|ModelSchema)\s*\)\s*:", re.MULTILINE
)

# Pattern: field_name: type = default or Field(...)
FIELD_RE = re.compile(r"^\s{2,8}(\w+)\s*:\s*(.+?)(?:\s*=\s*(.+))?\s*$", re.MULTILINE)

# Pattern: Field(min_length=X, max_length=Y, ...) constraints
CONSTRAINT_RE = re.compile(r"(\w+)\s*=\s*([^,\)]+)")

# Pattern: alias="foo" or alias='foo' in Field(...)
ALIAS_RE = re.compile(r"""\balias\s*=\s*["']([^"']+)["']""")
SERIALIZATION_ALIAS_RE = re.compile(r"""\bserialization_alias\s*=\s*["']([^"']+)["']""")
VALIDATION_ALIAS_RE = re.compile(r"""\bvalidation_alias\s*=\s*["']([^"']+)["']""")

# Pattern: alias_generator = to_camel or alias_generator=to_camel
ALIAS_GENERATOR_RE = re.compile(r"\balias_generator\s*=\s*(\w+)")

# Pattern: model_config = ConfigDict(...) on a single line (common case)
MODEL_CONFIG_RE = re.compile(r"^\s+model_config\s*=\s*ConfigDict\((.+?)\)", re.MULTILINE)

# Type patterns for optionality
OPTIONAL_RE = re.compile(r"Optional\[(.+)\]|(\w+)\s*\|\s*None|None\s*\|\s*(\w+)")


def parse_pydantic_file(path: Path) -> list[PydanticSchema]:
    """Parse all Pydantic schema classes from a Python file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    schemas: list[PydanticSchema] = []

    for match in CLASS_RE.finditer(text):
        class_name = match.group(1)
        parent = match.group(2)
        class_start = text[: match.start()].count("\n") + 1

        # Find the class body (indented lines after class declaration)
        body_lines: list[str] = []
        for line in lines[class_start:]:
            if line.strip() == "" or line.startswith("    ") or line.strip().startswith("#"):
                body_lines.append(line)
            elif body_lines:  # Non-indented non-empty line = end of class
                break

        body_text = "\n".join(body_lines)
        alias_gen = _detect_alias_generator(body_text)
        fields = _parse_fields(body_text)

        schemas.append(
            PydanticSchema(
                name=class_name,
                file=path,
                line=class_start,
                fields=fields,
                parent=parent,
                alias_generator=alias_gen,
            )
        )

    return schemas




def _strip_docstrings(body: str) -> str:
    """Remove triple-quoted blocks from a class body.

    A docstring is not a field. Without this, a docstring line such as
    ``- ``alias_generator=to_camel``: field ``first_name`` -> key`` parses as
    a field named ``alias_generator``, and the generated TypeScript is
    invalid.
    """
    return re.sub(r'"""(?:.|\n)*?"""', "", body)


def _parse_fields(body: str) -> list[PydanticField]:
    """Extract fields from a class body."""
    fields: list[PydanticField] = []
    body = _strip_docstrings(body)

    for match in FIELD_RE.finditer(body):
        name = match.group(1)
        type_str = match.group(2).strip()
        default_val = match.group(3)

        # Skip class Meta, Config, methods, private attrs
        if name.startswith("_") or name in ("class", "def", "Meta", "Config"):
            continue

        optional = bool(OPTIONAL_RE.search(type_str))

        # Parse constraints and aliases from Field(...)
        constraints: dict[str, str] = {}
        alias: str | None = None
        serialization_alias: str | None = None
        validation_alias: str | None = None
        if default_val and "Field(" in default_val:
            for cm in CONSTRAINT_RE.finditer(default_val):
                key, val = cm.group(1).strip(), cm.group(2).strip()
                if key not in (
                    "default",
                    "default_factory",
                    "alias",
                    "serialization_alias",
                    "validation_alias",
                ):
                    constraints[key] = val

            # Extract aliases
            am = ALIAS_RE.search(default_val)
            if am:
                alias = am.group(1)
            sam = SERIALIZATION_ALIAS_RE.search(default_val)
            if sam:
                serialization_alias = sam.group(1)
            vam = VALIDATION_ALIAS_RE.search(default_val)
            if vam:
                validation_alias = vam.group(1)

        fields.append(
            PydanticField(
                name=name,
                type_str=_normalize_type(type_str),
                optional=optional,
                default=default_val.strip() if default_val else None,
                constraints=constraints,
                alias=alias,
                serialization_alias=serialization_alias,
                validation_alias=validation_alias,
            )
        )

    return fields


def _detect_alias_generator(body: str) -> str | None:
    """Detect alias_generator in model_config = ConfigDict(...)."""
    m = MODEL_CONFIG_RE.search(body)
    if m:
        config_body = m.group(1)
        gm = ALIAS_GENERATOR_RE.search(config_body)
        if gm:
            return gm.group(1)
    # Also check bare alias_generator = ... (class-level attribute)
    gm = ALIAS_GENERATOR_RE.search(body)
    if gm:
        return gm.group(1)
    return None


def _normalize_type(t: str) -> str:
    """Normalize Python type to a canonical form."""
    t = t.strip()
    # Remove Optional wrapper
    m = OPTIONAL_RE.match(t)
    if m:
        inner = m.group(1) or m.group(2) or m.group(3)
        if inner:
            t = inner.strip()
    return t


def find_schema_files(project_path: Path) -> list[Path]:
    """Find Python files likely containing Pydantic schemas."""
    from mattstack.parsers.utils import find_files

    patterns = ["**/schemas.py", "**/schemas/*.py", "**/schema.py", "**/models.py"]
    return find_files(project_path, patterns)
