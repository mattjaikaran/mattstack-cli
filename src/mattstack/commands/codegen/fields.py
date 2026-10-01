"""Field specs and name conversions for generated models."""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass

DJANGO_FIELD_MAP: dict[str, str] = {
    "str": "CharField(max_length=255)",
    "int": "IntegerField()",
    "float": "FloatField()",
    "decimal": "DecimalField(max_digits=10, decimal_places=2)",
    "bool": "BooleanField(default=False)",
    "text": "TextField()",
    "date": "DateField()",
    "datetime": "DateTimeField()",
    "email": "EmailField()",
    "url": "URLField()",
    "uuid": "UUIDField(default=uuid.uuid4)",
}

# Instance attribute type of each DJANGO_FIELD_MAP column, for annotations.
FIELD_VALUE_TYPES: dict[str, str] = {
    "str": "str",
    "int": "int",
    "float": "float",
    "decimal": "Decimal",
    "bool": "bool",
    "text": "str",
    "date": "date",
    "datetime": "datetime",
    "email": "str",
    "url": "str",
    "uuid": "uuid.UUID",
}

PYDANTIC_TYPE_MAP: dict[str, str] = {
    "str": "str",
    "int": "int",
    "float": "float",
    "decimal": "Decimal",
    "bool": "bool",
    "text": "str",
    "date": "date",
    "datetime": "datetime",
    "email": "EmailStr",
    "url": "HttpUrl",
    "uuid": "UUID",
}

# JSON wire types. Pydantic serializes Decimal as a string, so a numeric
# TypeScript type would lie about every response.
TS_TYPE_MAP: dict[str, str] = {
    "str": "string",
    "int": "number",
    "float": "number",
    "decimal": "string",
    "bool": "boolean",
    "text": "string",
    "date": "string",
    "datetime": "string",
    "email": "string",
    "url": "string",
    "uuid": "string",
}

RESERVED_FIELDS = frozenset({"id", "pk", "created_at", "updated_at", "objects"})
IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
MODEL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
FK_TARGET_RE = re.compile(r"^(?:[a-z_][a-z0-9_]*\.)?[A-Z][A-Za-z0-9]*$")


class FieldSpecError(ValueError):
    """A --fields value cannot produce valid Python and TypeScript."""


# Key type of an FK target -> (Pydantic type, TypeScript type).
FK_KEY_TYPES: dict[str, tuple[str, str]] = {
    "uuid": ("UUID", "string"),
    "int": ("int", "number"),
    "str": ("str", "string"),
}

INT32_MAX = 2147483647
# Pydantic `Field(...)` arguments that reject what the DJANGO_FIELD_MAP column
# cannot store, so bad input is a 4xx instead of a database error or a value
# the database silently changes. EmailStr already caps length at 254
# (email-validator), matching EmailField. FK ids get no bounds: the target's
# key range is not known here, and the controller's existence lookup answers
# 404 for any id with no row.
FIELD_CONSTRAINTS: dict[str, str] = {
    "str": "max_length=255",
    "int": f"ge={-INT32_MAX - 1}, le={INT32_MAX}",
    "float": "allow_inf_nan=False",
    "decimal": "max_digits=10, decimal_places=2",
    "url": "max_length=200",
}


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    fk_target: str | None = None
    fk_reference: str | None = None  # ForeignKey's first argument, once resolved
    fk_key: str | None = None  # target primary key type: "uuid" | "int" | "str"

    @property
    def is_fk(self) -> bool:
        return self.type == "fk"

    @property
    def api_name(self) -> str:
        """Name on the wire and in schemas: Django exposes FKs as `<name>_id`."""
        return f"{self.name}_id" if self.is_fk else self.name

    def _fk_types(self) -> tuple[str, str]:
        if self.fk_key not in FK_KEY_TYPES:
            raise FieldSpecError(f"FK field '{self.name}' has no resolved target key type")
        return FK_KEY_TYPES[self.fk_key]

    @property
    def py_type(self) -> str:
        return self._fk_types()[0] if self.is_fk else PYDANTIC_TYPE_MAP[self.type]

    @property
    def ts_type(self) -> str:
        return self._fk_types()[1] if self.is_fk else TS_TYPE_MAP[self.type]

    @property
    def py_constraints(self) -> str:
        """`Field(...)` keyword arguments matching the column, or ""."""
        return "" if self.is_fk else FIELD_CONSTRAINTS.get(self.type, "")


def split_field_args(raw: list[str]) -> list[str]:
    """Flatten repeated `--fields` values and quoted space/comma lists."""
    return [spec for value in raw for spec in re.split(r"[\s,]+", value.strip()) if spec]


def parse_fields(raw: list[str]) -> list[FieldSpec]:
    """Parse `name:type` and `name:fk:Model` specs.

    `-f title:str -f price:decimal` and `-f "title:str price:decimal"` give the
    same result.
    """
    fields: list[FieldSpec] = []
    seen: set[str] = set()
    for spec in split_field_args(raw):
        parts = spec.split(":")
        if len(parts) == 3 and parts[1] == "fk":
            name, ftype, target = parts[0], "fk", parts[2]
            if not FK_TARGET_RE.match(target):
                raise FieldSpecError(
                    f"Invalid FK target '{target}' in '{spec}'. Use Model or app_label.Model."
                )
        elif len(parts) == 2:
            name, ftype, target = parts[0], parts[1], None
            if ftype == "fk":
                raise FieldSpecError(f"FK field '{spec}' needs a target: {name}:fk:ModelName")
            if ftype not in DJANGO_FIELD_MAP:
                valid = ", ".join(sorted(DJANGO_FIELD_MAP))
                raise FieldSpecError(
                    f"Unknown field type '{ftype}'. Valid: {valid} or fk:ModelName"
                )
        else:
            raise FieldSpecError(f"Invalid field spec '{spec}'. Use name:type or name:fk:ModelName")
        if not IDENTIFIER_RE.match(name) or keyword.iskeyword(name):
            raise FieldSpecError(f"Invalid field name '{name}': use a lowercase Python identifier")
        api_name = f"{name}_id" if ftype == "fk" else name
        if name in RESERVED_FIELDS or api_name in RESERVED_FIELDS:
            raise FieldSpecError(f"Field name '{name}' is reserved by the generated model")
        for key in {name, api_name}:
            if key in seen:
                raise FieldSpecError(f"Duplicate field '{key}'")
            seen.add(key)
        fields.append(FieldSpec(name, ftype, target))
    return fields


def validate_model_name(name: str) -> None:
    if not MODEL_NAME_RE.match(name) or keyword.iskeyword(name):
        raise FieldSpecError(f"Invalid model name '{name}': use PascalCase letters and digits")


def to_snake(name: str) -> str:
    """Convert PascalCase or camelCase to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.replace("-", "_").lower()


def to_pascal(name: str) -> str:
    """Convert snake_case, kebab-case, or PascalCase to PascalCase."""
    return "".join(word[:1].upper() + word[1:] for word in re.split(r"[_\-]", name) if word)


def to_camel(name: str) -> str:
    """Convert to camelCase."""
    pascal = to_pascal(name)
    return pascal[:1].lower() + pascal[1:]


def ts_key(name: str, camel_case: bool) -> str:
    """Return the JSON key the frontend sees for a snake_case field."""
    if not camel_case:
        return name
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def search_field(fields: list[FieldSpec]) -> str | None:
    """First text field, used for list search and __str__."""
    return next((f.name for f in fields if f.type in ("str", "text", "email")), None)
