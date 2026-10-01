"""Tests for mattstack version command."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from mattstack.commands.version import (
    _parse_version,
    check_pypi_version,
)


class TestParseVersion:
    def test_parses_semver(self) -> None:
        assert _parse_version("0.1.0") == (0, 1, 0)
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_parses_single_part(self) -> None:
        assert _parse_version("5") == (5,)

    def test_parses_two_parts(self) -> None:
        assert _parse_version("2.1") == (2, 1)

    def test_stops_at_non_numeric(self) -> None:
        # Stops at first part that can't be parsed as int
        assert _parse_version("1.2.3a1") == (1, 2)
        assert _parse_version("1.0-dev") == (1,)


_PYPI_REQUEST = httpx.Request("GET", "https://pypi.org/pypi/mattstack/json")


class TestCheckPypiVersion:
    @pytest.mark.parametrize(
        "outcome",
        [
            httpx.ConnectError("connection refused"),
            httpx.ReadTimeout("timed out"),
            httpx.Response(404, request=_PYPI_REQUEST),
            httpx.Response(200, content=b"<html>", request=_PYPI_REQUEST),
        ],
    )
    def test_returns_none_on_failure(self, outcome: Exception | httpx.Response) -> None:
        get = (
            {"side_effect": outcome}
            if isinstance(outcome, Exception)
            else {"return_value": outcome}
        )
        with patch("mattstack.commands.version.httpx.get", **get):
            assert check_pypi_version() is None


class TestRunVersion:
    def test_outputs_version_string(self) -> None:
        from typer.testing import CliRunner

        from mattstack.cli import app

        with patch("mattstack.commands.version.check_pypi_version", return_value=None):
            runner = CliRunner()
            result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "mattstack" in result.output
