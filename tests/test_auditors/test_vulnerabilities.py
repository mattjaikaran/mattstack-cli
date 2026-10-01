"""Tests for vulnerability scanning auditor."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from mattstack.auditors.base import AuditConfig, AuditType, Severity
from mattstack.auditors.vulnerabilities import VulnerabilityAuditor


def _make_config(path: Path) -> AuditConfig:
    return AuditConfig(project_path=path)


def test_audit_type() -> None:
    """VulnerabilityAuditor should have correct audit type."""
    assert VulnerabilityAuditor.audit_type == AuditType.VULNERABILITIES


def test_no_dependency_files(tmp_path: Path) -> None:
    """No findings when no dependency files exist."""
    auditor = VulnerabilityAuditor(_make_config(tmp_path))
    findings = auditor.run()
    assert findings == []


def test_empty_pyproject(tmp_path: Path) -> None:
    """No findings for pyproject.toml with no dependencies."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"\n')
    auditor = VulnerabilityAuditor(_make_config(tmp_path))
    with patch.object(auditor, "_try_pip_audit", return_value=False):
        findings = auditor.run()
    # No deps, so no OSV queries either
    assert findings == []


def test_empty_package_json(tmp_path: Path) -> None:
    """No findings for package.json with no dependencies."""
    (tmp_path / "package.json").write_text('{"name": "test", "version": "1.0.0"}')
    auditor = VulnerabilityAuditor(_make_config(tmp_path))
    with patch.object(auditor, "_try_npm_audit", return_value=False):
        findings = auditor.run()
    assert findings == []


def test_pip_audit_success(tmp_path: Path) -> None:
    """pip-audit returning vulnerabilities should produce findings."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\ndependencies = [\n  "django>=4.0",\n]\n'
    )
    pip_audit_output = json.dumps(
        [
            {
                "name": "django",
                "version": "4.0",
                "vulns": [
                    {
                        "id": "PYSEC-2023-001",
                        "description": "SQL injection in Django 4.0",
                        "fix_versions": ["4.0.1"],
                    }
                ],
            }
        ]
    )
    mock_result = MagicMock()
    mock_result.returncode = 1  # pip-audit returns 1 when vulns found
    mock_result.stdout = pip_audit_output

    with patch("subprocess.run", return_value=mock_result):
        auditor = VulnerabilityAuditor(_make_config(tmp_path))
        findings = auditor.run()

    assert len(findings) == 1
    assert "django" in findings[0].message
    assert "PYSEC-2023-001" in findings[0].message
    assert findings[0].severity == Severity.ERROR


def test_npm_audit_success(tmp_path: Path) -> None:
    """npm audit returning vulnerabilities should produce findings."""
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "test",
                "version": "1.0.0",
                "dependencies": {"lodash": "^4.17.0"},
            }
        )
    )
    npm_audit_output = json.dumps(
        {
            "vulnerabilities": {
                "lodash": {
                    "severity": "high",
                    "via": [{"title": "Prototype Pollution"}],
                },
            },
        }
    )
    mock_result = MagicMock()
    mock_result.stdout = npm_audit_output

    with patch("subprocess.run", return_value=mock_result):
        auditor = VulnerabilityAuditor(_make_config(tmp_path))
        findings = auditor.run()

    assert len(findings) == 1
    assert "lodash" in findings[0].message
    assert findings[0].severity == Severity.ERROR


def test_npm_severity_mapping() -> None:
    """Test npm severity string to Severity enum mapping."""
    assert VulnerabilityAuditor._npm_severity("critical") == Severity.ERROR
    assert VulnerabilityAuditor._npm_severity("high") == Severity.ERROR
    assert VulnerabilityAuditor._npm_severity("moderate") == Severity.WARNING
    assert VulnerabilityAuditor._npm_severity("low") == Severity.INFO


def test_pip_audit_timeout(tmp_path: Path) -> None:
    """pip-audit timeout should fall back gracefully."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\ndependencies = [\n  "django>=4.0",\n]\n'
    )
    import subprocess

    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pip-audit", 60)),
        patch.object(VulnerabilityAuditor, "_check_osv") as mock_osv,
    ):
        auditor = VulnerabilityAuditor(_make_config(tmp_path))
        auditor.run()
        # Should fall back to OSV
        mock_osv.assert_called()


_OSV_URL = "https://api.osv.dev/v1/query"


@pytest.mark.parametrize(
    "outcome",
    [
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out"),
        httpx.Response(500, request=httpx.Request("POST", _OSV_URL)),
        httpx.Response(200, content=b"not json", request=httpx.Request("POST", _OSV_URL)),
    ],
)
def test_osv_failures_are_skipped(tmp_path: Path, outcome: Exception | httpx.Response) -> None:
    """OSV network, HTTP status, and malformed-JSON errors produce no findings."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\ndependencies = [\n  "django>=4.0",\n]\n'
    )
    post = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}

    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch.object(httpx.Client, "post", **post),
    ):
        findings = VulnerabilityAuditor(_make_config(tmp_path)).run()
    assert findings == []


def test_osv_reports_known_vulnerability(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\ndependencies = [\n  "django>=4.0",\n]\n'
    )
    response = httpx.Response(
        200,
        json={"vulns": [{"id": "GHSA-1", "summary": "SQL injection", "severity": []}]},
        request=httpx.Request("POST", _OSV_URL),
    )

    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch.object(httpx.Client, "post", return_value=response),
    ):
        findings = VulnerabilityAuditor(_make_config(tmp_path)).run()
    assert len(findings) == 1
    assert "django 4.0: GHSA-1 — SQL injection" in findings[0].message


def test_auditor_registered_in_audit_command() -> None:
    """VulnerabilityAuditor should be in AUDITOR_CLASSES."""
    from mattstack.commands.audit import AUDITOR_CLASSES

    assert AuditType.VULNERABILITIES in AUDITOR_CLASSES


def test_vulnerability_audit_type_in_enum() -> None:
    """VULNERABILITIES should be a valid AuditType."""
    assert AuditType.VULNERABILITIES == "vulnerabilities"
    assert AuditType("vulnerabilities") == AuditType.VULNERABILITIES
