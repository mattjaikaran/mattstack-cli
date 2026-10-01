"""Parse Pydantic Schema/BaseModel classes from Python files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PydanticField:
    name: str
    type_str: str
    optional: bool = False  # the annotation admits None
    default: str | None = None
    has_default: bool = False  # the field may be omitted from input
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
    # Field name -> return annotation of a `@field_serializer` that covers it.
    serializers: dict[str, str] = field(default_factory=dict)


# Pattern: class Name(SomeBase):
# The base is any identifier; `_is_schema_parent` decides whether the class is
# a schema. The boilerplate's schemas inherit a local base such as
# CamelCaseSchema, so matching only `Schema`/`BaseModel` finds nothing.
CLASS_RE = re.compile(r"^class\s+(\w+)\s*\(\s*([\w.]+)\s*\)\s*:", re.MULTILINE)

# Base classes that mark a class as a schema.
SCHEMA_BASES = frozenset({"Schema", "BaseModel", "ModelSchema"})


def _is_schema_parent(parent: str) -> bool:
    """Return True when a base class marks the class as a Pydantic schema."""
    name = parent.rsplit(".", 1)[-1]
    # A local base such as CamelCaseSchema or UserSchema is also a schema.
    return name in SCHEMA_BASES or name.endswith("Schema")


# Pattern: field_name: type = default or Field(...). Class-body fields sit at
# exactly four spaces; deeper lines belong to methods or nested classes.
FIELD_RE = re.compile(r"^ {4}(\w+)\s*:\s*(.+?)(?:\s*=\s*(.+))?\s*$", re.MULTILINE)

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

OPTIONAL_WRAPPER_RE = re.compile(r"^(?:typing\.)?Optional\[(.+)\]$")
ANNOTATED_RE = re.compile(r"^(?:typing\.)?Annotated\[(.+)\]$")
NULL_MEMBERS = frozenset({"None", "NoneType"})


def split_top_level_union(type_str: str) -> list[str]:
    """Split on `|` that sits outside brackets.

    A naive split breaks `dict[str, bool | str]`, where the bar belongs to the
    inner type. Only a bar at bracket depth zero separates union members.
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in type_str:
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        if char == "|" and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def _split_top_level_args(type_str: str) -> list[str]:
    """Split comma-separated generic arguments at bracket depth zero."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in type_str:
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def split_nullable(type_str: str) -> tuple[str, bool]:
    """Return the annotation without None members and whether None was allowed."""
    t = type_str.strip()
    if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'":
        t = t[1:-1]  # a whole forward reference: "Model"
    if "Literal[" not in t:
        # Forward references inside generics: list["Model"]. Literal values keep quotes.
        t = t.replace('"', "").replace("'", "")
    annotated = ANNOTATED_RE.match(t)
    if annotated:
        t = _split_top_level_args(annotated.group(1))[0]
    wrapper = OPTIONAL_WRAPPER_RE.match(t)
    if wrapper:
        inner, _ = split_nullable(wrapper.group(1))
        return inner, True
    members = split_top_level_union(t)
    non_null = [m for m in members if m not in NULL_MEMBERS]
    if len(non_null) < len(members):
        return " | ".join(non_null) if non_null else "None", True
    return t, False


def _field_has_default(default_val: str | None) -> bool:
    """Return True when a field may be omitted, given its `= ...` text."""
    if default_val is None:
        return False
    value = default_val.strip()
    if not value.startswith("Field("):
        return value != "..."
    args = value[len("Field(") :].rstrip()
    if args.endswith(")"):
        args = args[:-1]
    parts = _split_top_level_args(args)
    if parts and "=" not in parts[0].split("(")[0]:
        return parts[0] != "..."
    return any(part.startswith(("default=", "default_factory=")) for part in parts)


def parse_pydantic_file(path: Path) -> list[PydanticSchema]:
    """Parse all Pydantic schema classes from a Python file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    schemas: list[PydanticSchema] = []

    for match in CLASS_RE.finditer(text):
        class_name = match.group(1)
        parent = match.group(2)
        # A subclass of an earlier schema in this file is a schema too, even
        # when its base is named `CommentBase` rather than `...Schema`.
        local_parent = parent.rsplit(".", 1)[-1] in {s.name for s in schemas}
        if not (_is_schema_parent(parent) or local_parent):
            continue
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
                serializers=_serializers(body_text),
            )
        )

    return schemas


# @field_serializer("a", "b", ...) stacked on `def name(...) -> ReturnType:`
SERIALIZER_RE = re.compile(
    r"@(?:pydantic\.)?field_serializer\(([^)]*)\)\s*\n(?:\s*@[^\n]*\n)*"
    r"\s*def\s+\w+\s*\([^)]*\)\s*->\s*([^:\n]+):"
)


def _serializers(body: str) -> dict[str, str]:
    """Field name -> return annotation for each always-active `@field_serializer`.

    `when_used="json"` serializers are skipped: Ninja dumps responses in
    Python mode and leaves the final encoding to the project's renderer.
    """
    found: dict[str, str] = {}
    for args, returns in SERIALIZER_RE.findall(body):
        when = re.search(r"""when_used\s*=\s*['"]([\w-]+)['"]""", args)
        if when and when.group(1).startswith("json"):
            continue
        for arg in args.split(","):
            name = re.fullmatch(r"""\s*['"](\w+)['"]\s*""", arg)
            if name:  # positional field names only; keyword args are options
                found[name.group(1)] = returns.strip()
    return found


def _strip_docstrings(body: str) -> str:
    """Remove triple-quoted blocks: a docstring line such as
    ``alias_generator=to_camel`` would otherwise parse as a field."""
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
        if name.startswith("_") or name in ("class", "def", "Meta", "Config", "model_config"):
            continue
        if type_str.startswith(("ClassVar", "typing.ClassVar")):
            continue

        normalized, optional = split_nullable(type_str)

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
                type_str=normalized,
                optional=optional,
                default=default_val.strip() if default_val else None,
                has_default=_field_has_default(default_val),
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


def resolve_schema_inheritance(schemas: list[PydanticSchema]) -> list[PydanticSchema]:
    """Return copies of *schemas* with fields and alias generators inherited.

    Parents resolve by class name, preferring one in the same file. Subclass
    fields override inherited fields of the same name, as in Pydantic. A parent
    outside the parsed set (Schema, BaseModel) adds nothing.
    """
    by_name: dict[str, list[PydanticSchema]] = {}
    for schema in schemas:
        by_name.setdefault(schema.name, []).append(schema)
    resolved: dict[int, PydanticSchema] = {}

    def find_parent(schema: PydanticSchema) -> PydanticSchema | None:
        candidates = by_name.get((schema.parent or "").rsplit(".", 1)[-1], [])
        same_file = [c for c in candidates if c.file == schema.file and c is not schema]
        others = [c for c in candidates if c is not schema]
        choices = same_file or others
        return choices[0] if choices else None

    def resolve(schema: PydanticSchema, seen: frozenset[int]) -> PydanticSchema:
        key = id(schema)
        if key in resolved:
            return resolved[key]
        parent = find_parent(schema)
        fields: dict[str, PydanticField] = {}
        alias_generator = schema.alias_generator
        serializers: dict[str, str] = {}
        if parent is not None and id(parent) not in seen:
            base = resolve(parent, seen | {key})
            fields = {f.name: f for f in base.fields}
            alias_generator = alias_generator or base.alias_generator
            serializers = dict(base.serializers)
        for own in schema.fields:
            fields[own.name] = own
        result = PydanticSchema(
            name=schema.name,
            file=schema.file,
            line=schema.line,
            fields=list(fields.values()),
            parent=schema.parent,
            alias_generator=alias_generator,
            serializers={**serializers, **schema.serializers},
        )
        resolved[key] = result
        return result

    return [resolve(schema, frozenset()) for schema in schemas]


def find_schema_files(project_path: Path) -> list[Path]:
    """Find Python files likely containing Pydantic schemas."""
    from mattstack.parsers.utils import find_files

    patterns = ["**/schemas.py", "**/schemas/*.py", "**/schema.py", "**/models.py"]
    return find_files(project_path, patterns)
