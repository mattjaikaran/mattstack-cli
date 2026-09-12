"""Tests for mattstack protect (branch protection)."""

from __future__ import annotations

from pathlib import Path

from mattstack.commands.protect import (
    _enable_no_commit_to_branch,
    build_ruleset_payload,
    generate_codeowners,
    run_protect,
)


def _write_config(tmp_path: Path, *, protect_main: bool, required_reviews: int = 2) -> None:
    (tmp_path / "mattstack.yml").write_text(
        f"protect_main: {str(protect_main).lower()}\nrequired_reviews: {required_reviews}\n",
        encoding="utf-8",
    )


def test_build_ruleset_payload() -> None:
    payload = build_ruleset_payload(2, ["gauntlet", "test"])

    assert payload["name"] == "mattstack-protect-main"
    assert payload["target"] == "branch"
    assert payload["enforcement"] == "active"
    assert payload["conditions"]["ref_name"]["include"] == [
        "refs/heads/main",
        "refs/heads/master",
    ]

    rule_types = [rule["type"] for rule in payload["rules"]]
    assert "pull_request" in rule_types
    assert "required_linear_history" in rule_types

    reviews = next(r for r in payload["rules"] if r["type"] == "required_reviews")
    assert reviews["parameters"]["required_approving_review_count"] == 2

    checks = next(r for r in payload["rules"] if r["type"] == "required_status_checks")
    assert checks["parameters"]["required_status_checks"] == [
        {"context": "gauntlet"},
        {"context": "test"},
    ]


def test_generate_codeowners_with_owner() -> None:
    assert "* @alice" in generate_codeowners("alice")


def test_generate_codeowners_placeholder() -> None:
    assert "your-github-handle" in generate_codeowners(None)


def test_enable_hook_absent(tmp_path: Path) -> None:
    f = tmp_path / ".pre-commit-config.yaml"
    f.write_text(
        "repos:\n"
        "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        "    rev: v0.9.0\n"
        "    hooks:\n"
        "      - id: ruff\n",
        encoding="utf-8",
    )

    changed = _enable_no_commit_to_branch(f)

    assert changed is True
    text = f.read_text(encoding="utf-8")
    assert "no-commit-to-branch" in text
    assert "--branch" in text and "master" in text


def test_enable_hook_already_active(tmp_path: Path) -> None:
    f = tmp_path / ".pre-commit-config.yaml"
    f.write_text(
        "repos:\n"
        "  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: v5.0.0\n"
        "    hooks:\n"
        "      - id: no-commit-to-branch\n"
        "        args: [--branch, main, --branch, master]\n",
        encoding="utf-8",
    )

    changed = _enable_no_commit_to_branch(f)

    assert changed is False


def test_enable_hook_updates_args(tmp_path: Path) -> None:
    f = tmp_path / ".pre-commit-config.yaml"
    f.write_text(
        "repos:\n"
        "  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: v5.0.0\n"
        "    hooks:\n"
        "      - id: no-commit-to-branch\n"
        "        args: [--branch, main]\n",
        encoding="utf-8",
    )

    changed = _enable_no_commit_to_branch(f)

    assert changed is True
    assert "master" in f.read_text(encoding="utf-8")


def test_run_protect_skips_when_disabled(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, protect_main=False)
    monkeypatch.setattr("mattstack.commands.protect._repo_slug", lambda *a, **k: None)

    run_protect(tmp_path)

    assert not (tmp_path / "CODEOWNERS").exists()


def test_run_protect_writes_files(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, protect_main=True, required_reviews=1)
    (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")

    calls: dict[str, object] = {}

    def fake_slug(*args: object, **kwargs: object) -> str:
        return "alice/repo"

    def fake_apply(slug: str, payload: dict, gh_bin: str = "gh") -> bool:
        calls["slug"] = slug
        calls["payload"] = payload
        return True

    monkeypatch.setattr("mattstack.commands.protect._repo_slug", fake_slug)
    monkeypatch.setattr("mattstack.commands.protect._apply_ruleset", fake_apply)

    run_protect(tmp_path)

    assert (tmp_path / "CODEOWNERS").exists()
    assert "alice" in (tmp_path / "CODEOWNERS").read_text(encoding="utf-8")
    assert calls["slug"] == "alice/repo"
    assert calls["payload"]["name"] == "mattstack-protect-main"
