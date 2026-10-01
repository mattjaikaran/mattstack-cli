"""Parse Django model class definitions from Python files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ModelField:
    name: str
    field_type: str
    kwargs: dict[str, str] = field(default_factory=dict)


@dataclass
class DjangoModel:
    name: str
    app: str
    file: Path
    line: int
    inherits: str  # "AbstractBaseModel" or "models.Model" etc.
    fields: list[ModelField] = field(default_factory=list)


# class Product(AbstractBaseModel): or class Product(models.Model):
CLASS_RE = re.compile(
    r"^class\s+(\w+)\s*\(\s*([^)]+)\s*\)\s*:",
    re.MULTILINE,
)

# field_name = models.CharField(...), field_name = CharField(...), annotated
# field_name: models.CharField[str, str] = models.CharField(...), or the value
# parenthesized on the following lines.
FIELD_RE = re.compile(
    r"^\s{4}(\w+)\s*(?::[^=\n]+)?=\s*\(?\s*(?:models\.)?(\w+Field|ForeignKey|OneToOneField|ManyToManyField|AutoField|BigAutoField|UUIDField|SlugField|EmailField|URLField|IPAddressField|BinaryField|FileField|ImageField|JSONField|ArrayField)\s*\(([^)]*)\)",
    re.MULTILINE,
)

# Extract kwarg key=value pairs
KWARG_RE = re.compile(r"(\w+)\s*=\s*([^,]+?)(?=,\s*\w+\s*=|$)", re.DOTALL)


def _parse_kwargs(args_str: str) -> dict[str, str]:
    """Extract keyword arguments from a field constructor string."""
    result: dict[str, str] = {}
    for m in KWARG_RE.finditer(args_str):
        key = m.group(1).strip()
        val = m.group(2).strip().strip("'\"")
        result[key] = val
    return result


def _extract_app_from_path(path: Path) -> str:
    """Derive app name from file path (e.g. backend/apps/catalog/models/product.py -> catalog)."""
    parts = path.parts
    for i, part in enumerate(parts):
        if part == "apps" and i + 1 < len(parts):
            return parts[i + 1]
    # fallback: parent of models/ dir
    for i, part in enumerate(parts):
        if part == "models" and i > 0:
            return parts[i - 1]
    return path.parent.name


def parse_models_file(path: Path) -> list[DjangoModel]:
    """Parse all Django model classes from a Python file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    models: list[DjangoModel] = []
    app = _extract_app_from_path(path)

    for match in CLASS_RE.finditer(text):
        class_name = match.group(1)
        parent_str = match.group(2).strip()

        # Skip non-model classes (Meta, Admin, Manager, etc.)
        skip_names = {"Meta", "Migration", "Manager", "Admin", "Config", "Form", "Serializer"}
        if class_name in skip_names:
            continue

        # Determine inheritance label
        if "AbstractBaseModel" in parent_str:
            inherits = "AbstractBaseModel"
        elif "models.Model" in parent_str or parent_str == "Model":
            inherits = "models.Model"
        elif "AbstractModel" in parent_str:
            inherits = parent_str
        else:
            # Skip classes that don't look like Django models
            if "Model" not in parent_str and "AbstractBase" not in parent_str:
                continue
            inherits = parent_str

        line_num = text[: match.start()].count("\n") + 1

        # Extract fields from class body
        class_start = match.end()
        # Find next top-level class or end of file
        next_class = CLASS_RE.search(text, class_start)
        class_end = next_class.start() if next_class else len(text)
        class_body = text[class_start:class_end]

        fields: list[ModelField] = []
        for fm in FIELD_RE.finditer(class_body):
            field_name = fm.group(1)
            if field_name.startswith("_"):
                continue
            field_type = fm.group(2)
            kwargs = _parse_kwargs(fm.group(3))
            fields.append(ModelField(name=field_name, field_type=field_type, kwargs=kwargs))

        models.append(
            DjangoModel(
                name=class_name,
                app=app,
                file=path,
                line=line_num,
                inherits=inherits,
                fields=fields,
            )
        )

    return models


def find_model_files(project_path: Path) -> list[Path]:
    """Find Python files containing Django model definitions."""
    from mattstack.parsers.utils import find_files

    patterns = [
        "**/models.py",
        "**/models/*.py",
    ]
    return find_files(project_path, patterns)
