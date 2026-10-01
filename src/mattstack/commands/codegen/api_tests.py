"""Render focused API contract tests for generated CRUD resources."""

from __future__ import annotations

from mattstack.commands.codegen.backend_layout import DJANGO_MATT, BackendLayout
from mattstack.commands.codegen.django_api import KEY_BITS, resource_path
from mattstack.commands.codegen.fields import INT32_MAX, FieldSpec, to_snake, ts_key
from mattstack.commands.codegen.py_lines import bracketed, from_import, py_literal
from mattstack.commands.codegen.resource_policy import DEFAULT_POLICY, ResourcePolicy

SAMPLE_VALUES: dict[str, object] = {
    "int": 1,
    "float": 1.5,
    "decimal": "9.99",
    "bool": True,
    "date": "2024-01-01",
    "datetime": "2024-01-01T00:00:00Z",
    "email": "test@example.com",
    "url": "https://example.com",
    "uuid": "00000000-0000-0000-0000-000000000001",
}
JSON = 'content_type="application/json"'
BODY = " " * 8
LOGIN_HELPER = [
    "def _login(tag: str) -> tuple[Any, dict[str, str]]:",
    '    """Create a user; return it with its JWT Authorization header."""',
    "    user_model = get_user_model()",
    '    values = {user_model.USERNAME_FIELD: f"generated-{tag}@example.com"}',
    '    values.update({f: f"generated-{tag}-{f}" for f in user_model.REQUIRED_FIELDS})',
    "    user = user_model._default_manager.create(**values)",
    "    token = RefreshToken.for_user(user).access_token",
    '    return user, {"HTTP_AUTHORIZATION": f"Bearer {token}"}',
    "",
    "",
]


def _sample(field: FieldSpec) -> object:
    """A valid value; FK samples point at rows that do not exist."""
    if field.is_fk:
        return INT32_MAX if field.fk_key == "int" else KEY_BITS["uuid"][2].replace("0", "1")
    return SAMPLE_VALUES.get(field.type, f"test {field.name}")


def _call(target: str, method: str, *args: str) -> list[str]:
    """`target = self.client.<method>(args)` in a test body."""
    return bracketed(BODY, f"{target} = self.client.{method}", list(args))


def _post(target: str, base: str) -> list[str]:
    return _call(target, "post", f'"{base}"', "data=json.dumps(payload)", JSON, "**self.auth")


def _payload(values: dict[str, object]) -> list[str]:
    items = [f"{py_literal(key)}: {py_literal(value)}" for key, value in values.items()]
    return bracketed(BODY, "payload = ", items, brackets="{}")


def _test(name: str) -> list[str]:
    return ["", *bracketed("    ", f"def {name}", ["self"], " -> None:")]


def _write_tests(name: str, fields: list[FieldSpec], base: str, read: list[str]) -> list[str]:
    """Test a successful write or a missing foreign-key target."""
    payload = _payload({f.api_name: _sample(f) for f in fields})
    if any(f.is_fk for f in fields):
        return [
            *_test("test_create_with_missing_relation_returns_404"),
            *payload,
            *_post("response", base),
            f"{BODY}assert response.status_code == 404",
            f"{BODY}assert {name}.objects.count() == 0",
        ]
    return [
        *_test("test_create_then_get"),
        *payload,
        *_post("response", base),
        f"{BODY}assert response.status_code == 201",
        *_call("created", "get", f"f\"{base}{{response.json()['id']}}\"", *read),
        f"{BODY}assert created.status_code == 200",
    ]


def _owned_tests(name: str, fields: list[FieldSpec], base: str, owner: str) -> list[str]:
    """Another user cannot see or change a row, and a payload cannot pick the owner."""
    values = {f.api_name: _sample(f) for f in fields}
    other_id = "str(self.other_user.pk)"
    forged = dict.fromkeys([f"{owner}_id", ts_key(f"{owner}_id", True)], other_id)
    forged_items = [
        *(f"{py_literal(k)}: {py_literal(v)}" for k, v in values.items() if k not in forged),
        *(f"{py_literal(k)}: {v}" for k, v in forged.items()),
    ]
    return [
        *_test("test_rows_are_private_to_their_owner"),
        *_payload(values),
        *_post("created", base),
        f"{BODY}assert created.status_code == 201",
        f"{BODY}url = f\"{base}{{created.json()['id']}}\"",
        f"{BODY}assert self.client.get(url, **self.other_auth).status_code == 404",
        *_call("update", "put", "url", "data=json.dumps(payload)", JSON, "**self.other_auth"),
        f"{BODY}assert update.status_code == 404",
        f"{BODY}assert self.client.delete(url, **self.other_auth).status_code == 404",
        *_call("listed", "get", f'"{base}"', "**self.other_auth"),
        f'{BODY}assert listed.json()["count"] == 0',
        f"{BODY}assert self.client.get(url, **self.auth).status_code == 200",
        *_call("listed", "get", f'"{base}"', "**self.auth"),
        f'{BODY}assert listed.json()["count"] == 1',
        *_test("test_create_binds_owner_to_caller"),
        *bracketed(BODY, "payload = ", forged_items, brackets="{}"),
        *_post("response", base),
        f"{BODY}assert response.status_code == 201",
        *bracketed(BODY, f"row = {name}.objects.get", ['pk=response.json()["id"]']),
        f"{BODY}assert row.{owner}_id == self.user.pk",
    ]


def _soft_delete_tests(
    name: str, fields: list[FieldSpec], base: str, read: list[str], *, authed: bool
) -> list[str]:
    """Delete keeps the row inactive; reads and a second delete no longer find it."""
    lines = [
        *_test("test_delete_soft_deletes_and_hides_row"),
        *_payload({f.api_name: _sample(f) for f in fields}),
        *_post("created", base),
        f"{BODY}assert created.status_code == 201",
        f"{BODY}url = f\"{base}{{created.json()['id']}}\"",
        f"{BODY}assert self.client.delete(url, **self.auth).status_code == 204",
        *_call("hidden", "get", "url", *read),
        f"{BODY}assert hidden.status_code == 404",
        *_call("listed", "get", f'"{base}"', *read),
        f'{BODY}assert listed.json()["count"] == 0',
        f"{BODY}assert self.client.delete(url, **self.auth).status_code == 404",
        *bracketed(BODY, f"row = {name}._base_manager.get", ['pk=created.json()["id"]']),
        f"{BODY}assert row.is_active is False",
        f"{BODY}assert row.deleted_at is not None",
    ]
    if authed:
        lines.append(f"{BODY}assert row.deleted_by_id == self.user.pk")
    return lines


def render_api_tests(
    name: str,
    fields: list[FieldSpec],
    layout: BackendLayout,
    policy: ResourcePolicy = DEFAULT_POLICY,
) -> str:
    """Render API tests against the real mount prefix and resource path.

    *fields* are wire fields (`api_fields`). Ninja projects with JWT get
    tokens for real users; django-matt projects with auth only get the
    unauthenticated checks. Owned resources also prove that anonymous reads
    get 401 and that another user's rows answer 404; soft-delete resources
    prove that a deleted row stays stored but leaves every read.
    """
    snake, plural = to_snake(name), resource_path(name)
    base = f"{layout.mount_prefix}{plural}/"
    missing = KEY_BITS[layout.pk_key][2]
    ninja = layout.framework != DJANGO_MATT
    ninja_jwt = layout.has_jwt and ninja
    writes = ninja_jwt or not layout.has_jwt
    owned = policy.owned
    read = ["**self.auth"] if owned else []
    transitions = writes and ninja and not any(f.is_fk for f in fields)
    stdlib = ["import json"] if writes else []
    stdlib += ["from typing import Any"] if ninja_jwt else []
    third_party = [
        *(["from django.contrib.auth import get_user_model"] if ninja_jwt else []),
        "from django.test import TestCase",
        *(["from ninja_jwt.tokens import RefreshToken"] if ninja_jwt else []),
    ]
    imports = [*stdlib, *([""] if stdlib else []), *third_party]
    reads_rows = any(f.is_fk for f in fields) or (transitions and (owned or policy.soft_delete))
    if writes and reads_rows:
        imports += ["", *from_import(f"{layout.app_module}.models.{snake}", [name])]
    body: list[str] = []
    if ninja_jwt:
        body += [
            "    def setUp(self) -> None:",
            '        self.user, self.auth = _login("owner")',
            *(['        self.other_user, self.other_auth = _login("other")'] if owned else []),
        ]
    elif not layout.has_jwt:
        body.append("    auth: dict[str, str] = {}")
    if owned:
        body += [
            *_test("test_anonymous_reads_get_401"),
            *_call("response", "get", f'"{base}"'),
            f"{BODY}assert response.status_code == 401",
            *_call("response", "get", f'"{base}{missing}"'),
            f"{BODY}assert response.status_code == 401",
        ]
    if ninja_jwt or not owned:
        body += [
            *_test(f"test_list_{plural}_returns_page"),
            *_call("response", "get", f'"{base}"', *read),
            f"{BODY}assert response.status_code == 200",
            f'{BODY}assert set(response.json()) >= {{"count", "results"}}',
            *_test(f"test_get_missing_{snake}_returns_404"),
            *_call("response", "get", f'"{base}{missing}"', *read),
            f"{BODY}assert response.status_code == 404",
        ]
    if layout.has_jwt:
        body += [
            *_test(f"test_create_{snake}_requires_auth"),
            *_call("response", "post", f'"{base}"', 'data="{}"', JSON),
            f"{BODY}assert response.status_code == 401",
            *_test(f"test_delete_{snake}_requires_auth"),
            *_call("response", "delete", f'"{base}{missing}"'),
            f"{BODY}assert response.status_code == 401",
        ]
    if writes:
        body += _write_tests(name, fields, base, read)
    if transitions and owned:
        body += _owned_tests(name, fields, base, policy.owner_field or "")
    if transitions and policy.soft_delete:
        body += _soft_delete_tests(name, fields, base, read, authed=ninja_jwt)
    lines = [
        f'"""API tests for {name}, generated by mattstack generate crud."""',
        "",
        *imports,
        "",
        "",
        *(LOGIN_HELPER if ninja_jwt else []),
        f"class {name}APITest(TestCase):",
        *(body[1:] if body[:1] == [""] else body),
        "",
    ]
    return "\n".join(lines)
