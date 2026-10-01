"""Resource policy validation for `generate model`/`crud` (#6).

Security and soft-delete behavior is proven by the generated API tests run
against a real Django Ninja backend; these tests cover what mattstack decides
before writing anything.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from mattstack.commands.codegen.backend_layout import GenerateError
from mattstack.commands.codegen.fields import parse_fields
from mattstack.commands.codegen.resource_policy import (
    Lifecycle,
    ResourcePolicy,
    Scope,
    policy_context,
)

MakeProject = Callable[..., Path]

# Mirrors django-ninja-boilerplate's model tiers (core/models/base.py).
BASE_MODELS = """\
import uuid

from django.conf import settings
from django.db import models


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)


class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class SoftDeleteBaseModel(TimestampedModel):
    is_active = models.BooleanField(default=True)
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL)

    def soft_delete(self, user=None) -> None:
        self.is_active = False


class SoftDeleteModel(SoftDeleteBaseModel):
    objects = ActiveManager()
    all_objects = models.Manager()


AbstractBaseModel = SoftDeleteBaseModel
"""
OWNED = ResourcePolicy(Scope.OWNED, owner_field="owner")
OWNED_SPEC = "title:str owner:fk:User"


def boilerplate(make_project: MakeProject, tmp_path: Path) -> Path:
    """A fixture backend with the boilerplate's base models and a swapped user model."""
    backend = make_project(tmp_path) / "backend"
    settings = backend / "api" / "settings.py"
    settings.write_text(settings.read_text() + 'AUTH_USER_MODEL = "core.User"\n')
    models = backend / "core" / "models"
    (models / "base.py").write_text(BASE_MODELS)
    (models / "user.py").write_text("class User(AbstractUser):\n    pass\n")
    return backend


def resolve(backend: Path, spec: str, policy: ResourcePolicy) -> None:
    policy_context(backend, None, parse_fields([spec] if spec else []), policy)


def test_policy_from_cli_strings_keeps_owned_scope_and_soft_delete() -> None:
    policy = ResourcePolicy("owned", "soft-delete", "owner")  # type: ignore[arg-type]
    assert policy.owned and policy.soft_delete
    with pytest.raises(ValueError):
        ResourcePolicy(scope="private")  # type: ignore[arg-type]


REFUSALS = [
    ("owned-without-owner-field", OWNED_SPEC, ResourcePolicy(Scope.OWNED), "--owner-field"),
    ("owner-field-not-declared", "title:str", OWNED, '-f "owner:fk:User"'),
    ("owner-not-a-user-fk", "title:str owner:fk:Category", OWNED, "AUTH_USER_MODEL"),
    ("owner-not-an-fk", "owner:str", OWNED, "AUTH_USER_MODEL"),
    ("owner-field-on-global", OWNED_SPEC, ResourcePolicy(owner_field="owner"), "--scope owned"),
    (
        "owner-is-an-audit-fk",
        "title:str deleted_by:fk:User",
        ResourcePolicy(Scope.OWNED, Lifecycle.SOFT_DELETE, "deleted_by"),
        "deleted_by",
    ),
    (
        "redeclared-soft-delete-flag",
        "title:str is_active:bool",
        ResourcePolicy(lifecycle=Lifecycle.SOFT_DELETE),
        "is_active",
    ),
]


@pytest.mark.parametrize(
    ("spec", "policy", "fix"), [r[1:] for r in REFUSALS], ids=[r[0] for r in REFUSALS]
)
def test_policy_refuses_inferred_or_unsafe_ownership(
    tmp_path: Path, make_project: MakeProject, spec: str, policy: ResourcePolicy, fix: str
) -> None:
    backend = boilerplate(make_project, tmp_path)
    with pytest.raises(GenerateError, match=re.escape(fix)):
        resolve(backend, spec, policy)


def test_owned_scope_refuses_a_project_without_jwt(
    tmp_path: Path, make_project: MakeProject
) -> None:
    backend = boilerplate(make_project, tmp_path)
    (backend / "pyproject.toml").write_text('[project]\ndependencies = ["django-ninja-extra"]\n')
    with pytest.raises(GenerateError, match="uv add django-ninja-jwt"):
        resolve(backend, OWNED_SPEC, OWNED)


@pytest.mark.parametrize(
    ("base_source", "lifecycle", "fix"),
    [
        (None, Lifecycle.SOFT_DELETE, "--lifecycle timestamped"),
        (
            BASE_MODELS.replace("filter(is_active=True)", "all()"),
            Lifecycle.SOFT_DELETE,
            "filters is_active=True",
        ),
        (
            BASE_MODELS.replace("def soft_delete(", "def archive("),
            Lifecycle.SOFT_DELETE,
            "soft_delete()",
        ),
        (
            "class AbstractBaseModel(models.Model):\n    id = models.UUIDField(primary_key=True)\n",
            Lifecycle.TIMESTAMPED,
            "TimestampedModel",
        ),
    ],
    ids=["no-base-module", "manager-shows-deleted", "no-soft-delete", "no-timestamped"],
)
def test_lifecycle_refuses_a_base_module_that_cannot_honor_it(
    tmp_path: Path,
    make_project: MakeProject,
    base_source: str | None,
    lifecycle: Lifecycle,
    fix: str,
) -> None:
    backend = boilerplate(make_project, tmp_path)
    base = backend / "core" / "models" / "base.py"
    if base_source is None:
        base.unlink()
    else:
        base.write_text(base_source)
    with pytest.raises(GenerateError, match=re.escape(fix)):
        resolve(backend, "", ResourcePolicy(lifecycle=lifecycle))


def test_lifecycle_base_class_decides_the_primary_key(
    tmp_path: Path, make_project: MakeProject
) -> None:
    backend = boilerplate(make_project, tmp_path)
    (backend / "core" / "models" / "base.py").write_text(
        BASE_MODELS.replace(
            "AbstractBaseModel = SoftDeleteBaseModel",
            "class AbstractBaseModel(models.Model):\n    id = models.AutoField(primary_key=True)\n",
        )
    )
    layout, _ = policy_context(backend, None, [], ResourcePolicy())
    assert layout.pk_key == "int"
    layout, _ = policy_context(backend, None, [], ResourcePolicy(lifecycle=Lifecycle.TIMESTAMPED))
    assert layout.pk_key == "uuid"


def test_service_refuses_a_services_module(tmp_path: Path, make_project: MakeProject) -> None:
    backend = boilerplate(make_project, tmp_path)
    (backend / "core" / "services.py").write_text("")
    with pytest.raises(GenerateError, match="services/ package"):
        resolve(backend, "", ResourcePolicy(with_service=True))
