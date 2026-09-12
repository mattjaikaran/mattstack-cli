"""Tests for the Gauntlet subprocess boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mattstack.gauntlet.client import (
    GauntletConfig,
    GauntletError,
    GauntletUnavailableError,
    check,
    find_config_file,
    load_config,
    resolve_binary,
)


def test_load_config_defaults_when_no_file(tmp_path: Path) -> None:
    """A project with no gauntlet.toml does not opt in to skipping."""
    config = load_config(tmp_path)
    assert config.binary_path == "gauntlet"
    assert config.skip_if_absent is False


def test_load_config_reads_integrations(tmp_path: Path) -> None:
    (tmp_path / "gauntlet.toml").write_text(
        "[integrations]\n"
        'binary_path = "/opt/gauntlet"\n'
        "skip_if_absent = false\n"
        'default_target = "backend"\n'
    )
    config = load_config(tmp_path)
    assert config.binary_path == "/opt/gauntlet"
    assert config.skip_if_absent is False
    assert config.default_target == "backend"


def test_load_config_ignores_bad_toml(tmp_path: Path) -> None:
    (tmp_path / "gauntlet.toml").write_text("this is not = = toml")
    assert load_config(tmp_path).skip_if_absent is False


def test_find_config_file_prefers_root(tmp_path: Path) -> None:
    (tmp_path / ".gauntlet").mkdir()
    (tmp_path / ".gauntlet" / "gauntlet.toml").write_text("[project]\n")
    assert find_config_file(tmp_path) == tmp_path / ".gauntlet" / "gauntlet.toml"
    (tmp_path / "gauntlet.toml").write_text("[project]\n")
    assert find_config_file(tmp_path) == tmp_path / "gauntlet.toml"


def test_resolve_binary_finds_path_entry(fake_gauntlet: Path, tmp_path: Path) -> None:
    assert resolve_binary(GauntletConfig(), tmp_path) == str(fake_gauntlet)


def test_resolve_binary_relative_to_project(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    binary = tools / "gauntlet"
    binary.write_text("#!/bin/sh\n")
    resolved = resolve_binary(GauntletConfig(binary_path="tools/gauntlet"), tmp_path)
    assert resolved == str(binary)


def test_resolve_binary_missing_returns_none(tmp_path: Path) -> None:
    config = GauntletConfig(binary_path="definitely-not-installed-xyz")
    assert resolve_binary(config, tmp_path) is None


def test_check_raises_when_binary_absent(tmp_path: Path) -> None:
    config = GauntletConfig(binary_path="definitely-not-installed-xyz")
    with pytest.raises(GauntletUnavailableError):
        check(tmp_path, config=config)


def test_check_parses_findings(
    fake_gauntlet: Path, fake_run, make_payload, make_finding, tmp_path: Path
) -> None:
    payload = make_payload(
        [
            make_finding(),
            make_finding(
                finding_id="GAUNTLET-SENTINEL-COVERAGE-002",
                check="sentinel:coverage",
                severity="warning",
                title="line coverage 74.2% (threshold 80%)",
                blocking=False,
            ),
        ]
    )
    fake_run(payload, exit_code=2)

    result = check(tmp_path)

    assert result.status.value == "fail"
    assert result.exit_code == 2
    assert result.tier == "full"
    assert len(result.findings) == 2
    assert result.error_count == 1
    assert result.warning_count == 1
    assert result.blocking_count == 1
    assert result.findings[0].id == "GAUNTLET-SENTINEL-SECRET-001"
    assert result.findings[0].location == "app.py:42"
    assert result.findings[0].engine == "sentinel"
    assert result.findings[0].category == "secret"


def test_check_accepts_pass_exit_code(
    fake_gauntlet: Path, fake_run, make_payload, tmp_path: Path
) -> None:
    fake_run(make_payload([], status="pass", exit_code=0), exit_code=0)
    result = check(tmp_path)
    assert result.status.value == "pass"
    assert result.findings == []


def test_check_raises_on_unparsable_output(fake_gauntlet: Path, fake_run, tmp_path: Path) -> None:
    fake_run("gauntlet: unrecognized subcommand\n", exit_code=1, stderr="unknown flag: --nope")
    with pytest.raises(GauntletError, match="usage error"):
        check(tmp_path)


def test_check_raises_on_empty_output(fake_gauntlet: Path, fake_run, tmp_path: Path) -> None:
    fake_run("", exit_code=4, stderr="panicked at parser.rs")
    with pytest.raises(GauntletError, match="internal error"):
        check(tmp_path)


def test_check_raises_on_unsupported_schema(
    fake_gauntlet: Path, fake_run, make_payload, tmp_path: Path
) -> None:
    payload = make_payload([])
    payload["schema_version"] = 99
    fake_run(payload)
    with pytest.raises(GauntletError, match="schema_version"):
        check(tmp_path)


def test_check_tolerates_leading_noise(
    fake_gauntlet: Path, fake_run, make_payload, make_finding, tmp_path: Path
) -> None:
    document = json.dumps(make_payload([make_finding()]))
    fake_run(f"warning: cache is cold\n{document}\n")
    assert len(check(tmp_path).findings) == 1


def test_check_uses_configured_tier(
    fake_gauntlet: Path, fake_run, make_payload, tmp_path: Path
) -> None:
    fake_run(make_payload([], tier="fast", status="pass", exit_code=0))
    assert check(tmp_path, tier="fast").tier == "fast"


def test_check_raises_on_timeout(
    fake_gauntlet: Path, fake_run, make_payload, tmp_path: Path
) -> None:
    fake_run(make_payload([]), exit_code=0, sleep=2.0)
    with pytest.raises(GauntletError, match="did not finish"):
        check(tmp_path, timeout=0.3)


def test_check_raises_on_internal_error_even_with_json(
    fake_gauntlet: Path, fake_run, make_payload, make_finding, tmp_path: Path
) -> None:
    """Exit code 4 invalidates the run, so partial findings are not a result."""
    fake_run(make_payload([make_finding()]), exit_code=4, stderr="panicked at parser.rs")
    with pytest.raises(GauntletError, match="internal error"):
        check(tmp_path)


def test_check_raises_on_timeout_exit_code_with_json(
    fake_gauntlet: Path, fake_run, make_payload, tmp_path: Path
) -> None:
    fake_run(make_payload([]), exit_code=5, stderr="budget exceeded")
    with pytest.raises(GauntletError, match="timeout"):
        check(tmp_path)


def test_check_raises_when_status_is_error(
    fake_gauntlet: Path, fake_run, make_payload, tmp_path: Path
) -> None:
    fake_run(make_payload([], status="error", exit_code=4), exit_code=4, stderr="boom")
    with pytest.raises(GauntletError):
        check(tmp_path)
