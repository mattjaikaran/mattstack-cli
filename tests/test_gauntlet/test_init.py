"""Tests for the gauntlet.toml generator."""

from __future__ import annotations

import tomllib
from pathlib import Path

from mattstack.gauntlet.init import CONFIG_FILENAME, generate_config, write_config


def _load(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_generated_python_config_is_valid_toml(tmp_path: Path) -> None:
    text = generate_config(tmp_path, has_python=True, has_typescript=False, has_rust=False)
    config = tomllib.loads(text)
    assert config["project"]["schema_version"] == 1
    assert config["project"]["name"] == tmp_path.name
    assert config["adapters"]["python"]["enabled"] is True
    assert config["adapters"]["python"]["package_manager"] == "uv"
    assert config["integrations"]["binary_path"] == "gauntlet"
    assert config["integrations"]["skip_if_absent"] is True


def test_generated_config_enables_exactly_one_adapter(tmp_path: Path) -> None:
    """Gauntlet rejects an unused adapter, so never enable two by default."""
    text = generate_config(tmp_path, has_python=True, has_typescript=True, has_rust=False)
    config = tomllib.loads(text)
    enabled = [name for name, block in config["adapters"].items() if block.get("enabled")]
    assert enabled == ["python"]


def test_frontend_only_project_uses_rust_block_as_placeholder(tmp_path: Path) -> None:
    """A TypeScript-only project still produces a loadable config."""
    text = generate_config(tmp_path, has_python=False, has_typescript=True, has_rust=False)
    config = tomllib.loads(text)
    assert config["adapters"]["rust"]["enabled"] is False
    assert "TypeScript" in text


def test_rust_project_enables_rust_adapter(tmp_path: Path) -> None:
    text = generate_config(tmp_path, has_python=False, has_typescript=False, has_rust=True)
    config = tomllib.loads(text)
    assert config["adapters"]["rust"]["enabled"] is True


def test_tier_gate_defaults_match_the_spec(tmp_path: Path) -> None:
    config = tomllib.loads(
        generate_config(tmp_path, has_python=True, has_typescript=False, has_rust=False)
    )
    assert config["tiers"]["fast"]["gates"] == ["deterministic"]
    assert config["tiers"]["full"]["gates"] == ["deterministic", "conformance", "review"]
    assert config["tiers"]["release"]["gates"] == [
        "deterministic",
        "conformance",
        "review",
        "mutation",
        "perf",
    ]


def test_config_omits_disputed_per_check_tables(tmp_path: Path) -> None:
    """No per-check table, because Gauntlet's spec disagrees on the key form.

    Gauntlet documents `[checks.coverage]` in gauntlet-toml.md and
    `[checks.sentinel:coverage]` in init.md. An unrecognized key is a hard
    error, so the generator relies on Gauntlet's documented defaults instead.
    """
    config = tomllib.loads(
        generate_config(tmp_path, has_python=True, has_typescript=False, has_rust=False)
    )
    checks = config["checks"]
    assert set(checks) == {"deterministic"}
    assert checks["deterministic"]["enabled"] == ["all"]


def test_write_config_creates_file(tmp_path: Path) -> None:
    written = write_config(tmp_path, has_python=True, has_typescript=False, has_rust=False)
    assert written == tmp_path / CONFIG_FILENAME
    assert written is not None and written.exists()


def test_write_config_never_overwrites(tmp_path: Path) -> None:
    existing = tmp_path / CONFIG_FILENAME
    existing.write_text("# hand written\n")
    assert write_config(tmp_path, has_python=True, has_typescript=False, has_rust=False) is None
    assert existing.read_text() == "# hand written\n"


def test_config_declares_no_unknown_top_level_sections(tmp_path: Path) -> None:
    """Every section must exist in the Gauntlet schema."""
    documented = {
        "project",
        "tiers",
        "adapters",
        "checks",
        "conformance",
        "review",
        "authority",
        "vault",
        "models",
        "integrations",
        "output",
        "budget",
    }
    config = tomllib.loads(
        generate_config(tmp_path, has_python=True, has_typescript=False, has_rust=False)
    )
    assert set(config) <= documented
