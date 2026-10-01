"""Resource scope and model lifecycle for generated CRUD backends.

Authorization is never inferred from the fields: a user foreign key is only a
column until `--scope owned --owner-field <name>` names it the owner. Every
choice is checked against the project before anything is planned, and a
refusal names the missing prerequisite and the command that fixes it.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from mattstack.commands.codegen.backend_layout import (
    DJANGO_MATT,
    BackendLayout,
    GenerateError,
    detect_backend_layout,
)
from mattstack.commands.codegen.fields import FieldSpec
from mattstack.commands.codegen.model_pk import resolve_fields, with_model_key

USER_REFERENCE = "settings.AUTH_USER_MODEL"
# The boilerplate's UNSCOPED_QUERY gate (scripts/check_conventions.py) skips a
# controller line that holds "noqa:". A global list is unscoped on purpose, so
# that line names the check it waives and the policy that allows it.
# Ruff does not read the generated waiver as one of its directives.
GLOBAL_QUERY_WAIVER = "# global policy; noqa: UNSCOPED_QUERY"


class Scope(StrEnum):
    GLOBAL = "global"
    OWNED = "owned"


class Lifecycle(StrEnum):
    BASE = "base"
    TIMESTAMPED = "timestamped"
    SOFT_DELETE = "soft-delete"


# Abstract model, in the project's base model module, that each lifecycle inherits.
BASE_CLASSES: dict[Lifecycle, str] = {
    Lifecycle.BASE: "AbstractBaseModel",
    Lifecycle.TIMESTAMPED: "TimestampedModel",
    Lifecycle.SOFT_DELETE: "SoftDeleteModel",
}


@dataclass(frozen=True)
class ResourcePolicy:
    """Who may read and write a generated resource, and how its rows end."""

    scope: Scope = Scope.GLOBAL
    lifecycle: Lifecycle = Lifecycle.BASE
    owner_field: str | None = None  # user FK that owns each row; owned scope only
    with_service: bool = False

    def __post_init__(self) -> None:
        # Typer or YAML may pass raw strings; `is` comparisons below need members,
        # and a bad value must fail here instead of silently meaning "global".
        object.__setattr__(self, "scope", Scope(self.scope))
        object.__setattr__(self, "lifecycle", Lifecycle(self.lifecycle))

    @property
    def owned(self) -> bool:
        return self.scope is Scope.OWNED

    @property
    def soft_delete(self) -> bool:
        return self.lifecycle is Lifecycle.SOFT_DELETE

    @property
    def base_class(self) -> str:
        return BASE_CLASSES[self.lifecycle]


DEFAULT_POLICY = ResourcePolicy()


def api_fields(fields: list[FieldSpec], policy: ResourcePolicy) -> list[FieldSpec]:
    """Fields on the wire: an owned resource's owner FK is set by the server, never sent."""
    if not policy.owned:
        return fields
    return [f for f in fields if f.name != policy.owner_field]


def _class_body(text: str, name: str) -> str | None:
    match = re.search(rf"^class {name}\b[^\n]*\n", text, re.MULTILINE)
    if match is None:
        return None
    end = re.search(r"^\S", text[match.end() :], re.MULTILINE)
    return text[match.end() : match.end() + end.start()] if end else text[match.end() :]


def _check_soft_delete(module: str, text: str) -> None:
    """Generated reads trust `objects` to hide soft-deleted rows; verify that it does."""
    body = _class_body(text, "SoftDeleteModel")
    manager = re.search(r"^\s+objects\s*=\s*(\w+)\(\)", body or "", re.MULTILINE)
    manager_body = _class_body(text, manager.group(1)) if manager else None
    if (
        body is None
        or "def soft_delete(" not in text
        or manager_body is None
        or "is_active=True" not in manager_body
    ):
        raise GenerateError(
            f"--lifecycle soft-delete needs {module}.SoftDeleteModel with a soft_delete() "
            "method and a default `objects` manager that filters is_active=True, so normal "
            "reads hide deleted rows. Add them as in django-ninja-boilerplate "
            "core/models/base.py, or rerun with --lifecycle timestamped."
        )


def _check_lifecycle(layout: BackendLayout, policy: ResourcePolicy) -> None:
    if policy.lifecycle is Lifecycle.BASE:
        return
    module = layout.base_model_module
    if module is None:
        if policy.soft_delete:
            raise GenerateError(
                "--lifecycle soft-delete needs a base model module defining "
                "AbstractBaseModel and SoftDeleteModel (django-ninja-boilerplate "
                f"core/models/base.py); none was found under {layout.backend_dir}. "
                "Rerun with --lifecycle timestamped or --lifecycle base."
            )
        return  # timestamped: generated models declare their own UUID id and timestamps
    path = layout.backend_dir.joinpath(*module.split(".")).with_suffix(".py")
    text = path.read_text(encoding="utf-8", errors="replace")
    name = policy.base_class
    if not re.search(rf"^(?:class {name}\b|{name}\s*=)", text, re.MULTILINE):
        raise GenerateError(
            f"--lifecycle {policy.lifecycle} needs {name} in {module} ({path}), but it is "
            f"not defined there. Define it or rerun with --lifecycle base."
        )
    if policy.soft_delete:
        _check_soft_delete(module, text)


def _check_owner(layout: BackendLayout, fields: list[FieldSpec], policy: ResourcePolicy) -> None:
    owner = policy.owner_field
    if not policy.owned:
        if owner is not None:
            raise GenerateError(
                f"--owner-field {owner} applies only to --scope owned. Add --scope owned "
                "to bind rows to the authenticated user, or drop --owner-field."
            )
        return
    example = f'-f "{owner or "owner"}:fk:User" --owner-field {owner or "owner"}'
    if owner is None:
        raise GenerateError(
            "--scope owned needs --owner-field naming the user foreign key that owns "
            f"each row, e.g. {example}."
        )
    field = next((f for f in fields if f.name == owner), None)
    if field is None:
        raise GenerateError(f"--owner-field {owner} is not in --fields; add it: {example}.")
    if not field.is_fk or field.fk_reference != USER_REFERENCE:
        raise GenerateError(
            f"Owner field '{owner}' must be a foreign key to AUTH_USER_MODEL, but it is "
            f"{field.fk_target or field.type}. Declare it as {example} "
            "(User is the AUTH_USER_MODEL class)."
        )
    if not layout.has_jwt:
        package, fix = (
            ("django-matt[auth]", 'uv add "django-matt[auth]"')
            if layout.framework == DJANGO_MATT
            else ("django-ninja-jwt", "uv add django-ninja-jwt")
        )
        raise GenerateError(
            "--scope owned binds rows to the authenticated request user, but "
            f"{layout.backend_dir / 'pyproject.toml'} does not depend on {package}. "
            f"Run `{fix}` in {layout.backend_dir}, or use --scope global."
        )


INHERITED_FIELD_RE = re.compile(r"^ {4}(\w+)\s*(?::[^=\n]+)?=\s*\(?\s*models\.\w+\(", re.MULTILINE)


def _inherited_fields(text: str, name: str, depth: int = 0) -> set[str]:
    """Model fields *name* inherits within the base module, following aliases and bases."""
    alias = re.search(rf"^{name}\s*=\s*(\w+)\s*$", text, re.MULTILINE)
    if alias and depth < 20:
        return _inherited_fields(text, alias.group(1), depth + 1)
    header = re.search(rf"^class {name}\(([^)]*)\)", text, re.MULTILINE)
    body = _class_body(text, name)
    if header is None or body is None or depth >= 20:
        return set()
    found = set(INHERITED_FIELD_RE.findall(body))
    for base in header.group(1).split(","):
        found |= _inherited_fields(text, base.strip().rsplit(".", 1)[-1], depth + 1)
    return found


def _check_inherited(
    layout: BackendLayout, fields: list[FieldSpec], policy: ResourcePolicy
) -> None:
    """Refuse a field that would silently override one the base model provides.

    Django lets a child redeclare an abstract parent's field, so `is_active:bool`
    would replace the soft-delete flag with default=False and hide every new row.
    """
    module = layout.base_model_module
    if module is None:
        return
    path = layout.backend_dir.joinpath(*module.split(".")).with_suffix(".py")
    text = path.read_text(encoding="utf-8", errors="replace")
    inherited = _inherited_fields(text, policy.base_class)
    clashes = sorted({f.name for f in fields} & inherited)
    if clashes:
        raise GenerateError(
            f"--fields {', '.join(clashes)} redeclare fields that {module}.{policy.base_class} "
            f"already provides ({', '.join(sorted(inherited))}). Remove them from --fields; "
            "the generated model inherits them."
        )


def _check_service_package(layout: BackendLayout, policy: ResourcePolicy) -> None:
    module = layout.app_dir / "services.py"
    if policy.with_service and module.exists():
        raise GenerateError(
            f"{module} is a module; --with-service needs a services/ package. "
            "Move it to services/__init__.py or drop --with-service."
        )


def policy_context(
    backend_dir: Path, app: str | None, fields: list[FieldSpec], policy: ResourcePolicy
) -> tuple[BackendLayout, list[FieldSpec]]:
    """Inspect the backend, resolve key types, and refuse a policy it cannot honor.

    Returns the layout, with the key type of *policy*'s base model, and
    *fields* with FK targets resolved. Nothing has been written when this
    raises GenerateError.
    """
    layout = detect_backend_layout(backend_dir, app)
    _check_lifecycle(layout, policy)
    _check_service_package(layout, policy)
    layout = with_model_key(layout, policy.base_class)
    resolved = resolve_fields(layout, fields)
    _check_inherited(layout, resolved, policy)
    _check_owner(layout, resolved, policy)
    return layout, resolved


def _writes(layout: BackendLayout, policy: ResourcePolicy) -> str:
    if policy.owned:
        return ""
    if layout.has_jwt:
        return "Create, update, and delete require a valid JWT and may change any row."
    return "Create, update, and delete are open to every caller: the project has no JWT auth."


def policy_doc(
    name: str, layout: BackendLayout, policy: ResourcePolicy, *, waives_gate: bool = False
) -> list[str]:
    """Docstring paragraphs that state *policy* in the generated module.

    *waives_gate* marks the module holding the global list query and its
    UNSCOPED_QUERY waiver, so only that module explains the waiver.
    """
    if policy.owned:
        owner = policy.owner_field
        scope = (
            f"Resource policy: owned by `{owner}`. Every route requires a valid JWT; an "
            f"anonymous request gets 401. Create sets `{owner}` to the authenticated user "
            "and ignores any owner in the payload. List, get, update, and delete see only "
            "the caller's rows, so another user's row answers 404, like a missing one. "
            "Related rows are checked for existence, not ownership."
        )
    else:
        scope = (
            f"Resource policy: global. Every caller lists and reads every {name} row. "
            f"{_writes(layout, policy)} Rows have no owner: a user foreign key grants no "
            "access. Regenerate with --scope owned --owner-field <field> to bind rows "
            "to the authenticated user."
        )
    paragraphs = [scope]
    if waives_gate:
        paragraphs.append(
            "Convention gate: the list queryset is unscoped on purpose, and its line "
            "waives UNSCOPED_QUERY (scripts/check_conventions.py skips lines with `noqa:`)."
        )
    if policy.soft_delete:
        paragraphs.append(
            "Lifecycle: SoftDeleteModel. Delete calls soft_delete(), which keeps the row "
            "with is_active=False; the default `objects` manager hides it from list, get, "
            "update, and delete, which then answer 404."
        )
    else:
        base = policy.base_class if layout.base_model_module else "models.Model"
        paragraphs.append(f"Lifecycle: {base}. Delete removes the row.")
    lines: list[str] = []
    for paragraph in paragraphs:
        lines += [*textwrap.wrap(paragraph, width=79), ""]
    return lines[:-1]
