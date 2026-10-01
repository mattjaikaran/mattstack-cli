"""Resolve FK targets to installed models and their primary key types.

A generated `<name>_id` field must carry the target's real key type: UUID
keys are strings on the wire, integer auto keys are numbers. The type is
derived from the target's declared primary key or from verified Django
inheritance; anything else is refused rather than guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from mattstack.commands.codegen.backend_layout import (
    SKIP_PARTS,
    BackendLayout,
    GenerateError,
    app_label,
    installed_apps,
    settings_texts,
)
from mattstack.commands.codegen.fields import FieldSpec
from mattstack.parsers.utils import find_files

CLASS_RE = re.compile(r"^class\s+(\w+)\s*\(([^)]*)\)\s*:", re.MULTILINE)
ALIAS_RE = re.compile(r"^(\w+)\s*=\s*(\w+)\s*$", re.MULTILINE)
# `name = models.X(`, annotated `name: models.X[...] = models.X(`, or a
# parenthesized value `name: ... = (\n        models.X(`.
FIELD_START_RE = re.compile(
    r"^ {4}(\w+)\s*(?::[^=\n]+)?=\s*\(?\s*(?:models\.)?(\w+)\(", re.MULTILINE
)
AUTH_USER_RE = re.compile(r"""^AUTH_USER_MODEL\s*=\s*['"](\w+)\.(\w+)['"]""", re.MULTILINE)
DEFAULT_AUTO_RE = re.compile(r"""DEFAULT_AUTO_FIELD\s*=\s*['"]([\w.]+)['"]""")
MODEL_PATTERNS = ["*/models.py", "*/*/models.py", "*/models/*.py", "*/*/models/*.py"]

PK_FIELD_TYPES: dict[str, str] = {
    "UUIDField": "uuid",
    "CharField": "str",
    "SlugField": "str",
    "EmailField": "str",
    **dict.fromkeys(
        [
            "AutoField",
            "BigAutoField",
            "SmallAutoField",
            "IntegerField",
            "BigIntegerField",
            "PositiveIntegerField",
            "PositiveBigIntegerField",
            "SmallIntegerField",
        ],
        "int",
    ),
}
# Bases whose primary key is Django's default auto field.
AUTO_PK_BASES = frozenset({"Model", "AbstractUser", "AbstractBaseUser"})
# Bases that add no primary key and do not decide one.
NEUTRAL_BASES = frozenset({"PermissionsMixin", "object"})
CONTRIB_MODELS = {"auth.User": "int", "auth.Group": "int", "auth.Permission": "int"}


@dataclass(frozen=True)
class FKTarget:
    reference: str  # Python expression for ForeignKey's first argument
    pk_type: str  # "uuid" | "int" | "str"


def _class_body(text: str, start: int) -> str:
    nxt = re.search(r"^\S", text[start:], re.MULTILINE)
    return text[start : start + nxt.start()] if nxt else text[start:]


def _call_args(text: str, open_index: int) -> str:
    depth = 0
    for index in range(open_index, len(text)):
        depth += {"(": 1, ")": -1}.get(text[index], 0)
        if depth == 0:
            return text[open_index + 1 : index]
    return text[open_index + 1 :]


class _ModelIndex:
    """Class definitions and aliases across the project's model modules."""

    def __init__(self, backend_dir: Path) -> None:
        self.backend_dir = backend_dir
        self.classes: dict[str, list[tuple[Path, str, list[str]]]] = {}
        self.aliases: dict[str, str] = {}
        for path in find_files(backend_dir, MODEL_PATTERNS):
            if SKIP_PARTS.intersection(path.relative_to(backend_dir).parts):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in CLASS_RE.finditer(text):
                bases = [
                    b.strip().rsplit(".", 1)[-1] for b in match.group(2).split(",") if b.strip()
                ]
                body = _class_body(text, match.end())
                self.classes.setdefault(match.group(1), []).append((path, body, bases))
            for name, target in ALIAS_RE.findall(text):
                self.aliases.setdefault(name, target)
        texts = settings_texts(backend_dir)
        auto = next((m.group(1) for t in texts if (m := DEFAULT_AUTO_RE.search(t))), None)
        self.default_auto_ok = auto is None or auto.rsplit(".", 1)[-1] in PK_FIELD_TYPES

    def in_app(self, name: str, app_dir: Path) -> tuple[Path, str, list[str]] | None:
        for path, body, bases in self.classes.get(name, []):
            if app_dir in path.parents:
                return path, body, bases
        return None

    def lookup(self, name: str, near: Path) -> tuple[Path, str, list[str]] | None:
        """Find *name* in the same file, then the same app, then uniquely anywhere."""
        name = self.aliases.get(name, name)
        found = self.classes.get(name, [])
        for scope in (near, near.parent, near.parent.parent):
            local = [c for c in found if c[0] == scope or scope in c[0].parents]
            if len(local) == 1:
                return local[0]
        return found[0] if len(found) == 1 else None

    def pk_type(self, entry: tuple[Path, str, list[str]], depth: int = 0) -> str | None:
        """Primary key type of a class, or None when it cannot be verified."""
        path, body, bases = entry
        if depth > 20:
            return None
        for match in FIELD_START_RE.finditer(body):
            args = _call_args(body, match.end() - 1)
            if re.search(r"\bprimary_key\s*=\s*True\b", args):
                return PK_FIELD_TYPES.get(match.group(2))
        for base in bases:
            if base in NEUTRAL_BASES:
                continue
            if base in AUTO_PK_BASES:
                return "int" if self.default_auto_ok else None
            parent = self.lookup(base, path)
            return self.pk_type(parent, depth + 1) if parent else None
        return None


def _auth_user_label(backend_dir: Path) -> str:
    texts = settings_texts(backend_dir)
    match = next((m for t in texts if (m := AUTH_USER_RE.search(t))), None)
    return f"{match.group(1)}.{match.group(2)}" if match else "auth.User"


def resolve_fk_target(
    layout: BackendLayout, target: str, index: _ModelIndex | None = None
) -> FKTarget:
    """Resolve `Model` or `app_label.Model` to an installed model and its key type."""
    index = index or _ModelIndex(layout.backend_dir)
    user_label = _auth_user_label(layout.backend_dir)
    apps = {app_label(a): a for a in installed_apps(layout.backend_dir)}
    if "." in target:
        label, name = target.split(".", 1)
        candidates = [(label, name)]
    else:
        name = target
        own = [(layout.app_label, name)] if index.in_app(name, layout.app_dir) else []
        others = [(lbl, name) for lbl, d in apps.items() if index.in_app(name, d)]
        candidates = own or others
        if not candidates and user_label.rsplit(".", 1)[1] == name:
            candidates = [tuple(user_label.split("."))]  # type: ignore[list-item]
        if len({c for c in candidates}) > 1 and not own:
            listed = ", ".join(f"{lbl}.{n}" for lbl, n in candidates)
            raise GenerateError(
                f"FK target '{target}' is ambiguous ({listed}); use app_label.Model."
            )
    if not candidates:
        raise GenerateError(
            f"FK target model '{target}' not found in an installed app. "
            f"Generate it first: mattstack generate model {target} --fields ..."
        )
    label, name = candidates[0]
    full = f"{label}.{name}"
    reference = "settings.AUTH_USER_MODEL" if full == user_label else f'"{full}"'
    if full in CONTRIB_MODELS:
        return FKTarget(reference, CONTRIB_MODELS[full])
    app_dir = apps.get(label)
    entry = index.in_app(name, app_dir) if app_dir is not None else None
    if entry is None:
        raise GenerateError(f"FK target '{full}' is not a model in an installed app.")
    pk = index.pk_type(entry)
    if pk is None:
        raise GenerateError(
            f"Cannot determine the primary key type of {full}; declare its primary key "
            "explicitly or inherit from a model whose key is declared."
        )
    return FKTarget(reference, pk)


def with_model_key(layout: BackendLayout, base_class: str = "AbstractBaseModel") -> BackendLayout:
    """Return *layout* with the primary key type generated models will have.

    *base_class* is the abstract model in `layout.base_model_module` that
    generated models inherit.
    """
    if layout.base_model_module is None:
        return replace(layout, pk_key="uuid")  # generated models declare a UUID id
    index = _ModelIndex(layout.backend_dir)
    module_path = layout.backend_dir.joinpath(*layout.base_model_module.split("."))
    entry = index.lookup(base_class, module_path.with_suffix(".py"))
    pk = index.pk_type(entry) if entry else None
    if pk is None:
        raise GenerateError(
            f"Cannot determine the primary key type of {layout.base_model_module}.{base_class}."
        )
    return replace(layout, pk_key=pk)


def resolve_fields(layout: BackendLayout, fields: list[FieldSpec]) -> list[FieldSpec]:
    """Return *fields* with each FK's model reference and key type resolved."""
    index = _ModelIndex(layout.backend_dir)
    resolved = []
    for field in fields:
        if field.is_fk and field.fk_target:
            target = resolve_fk_target(layout, field.fk_target, index)
            field = replace(field, fk_reference=target.reference, fk_key=target.pk_type)
        resolved.append(field)
    return resolved
