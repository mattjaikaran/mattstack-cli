"""Tests for the Gauntlet wire models."""

from __future__ import annotations

import pytest

from mattstack.gauntlet.models import (
    ENGINES,
    CheckStatus,
    Finding,
    RunResult,
    SchemaError,
    Severity,
)


def test_finding_derives_engine_and_category() -> None:
    finding = Finding.from_json(
        {"id": "X", "check": "sentinel:secret", "severity": "error", "title": "t", "body": "b"}
    )
    assert finding.engine == "sentinel"
    assert finding.category == "secret"


def test_finding_location_without_file_is_repo() -> None:
    finding = Finding.from_json(
        {
            "id": "X",
            "check": "conformance:plan",
            "severity": "warning",
            "title": "t",
            "body": "b",
            "file": None,
            "line": None,
        }
    )
    assert finding.location == "(repo)"


def test_finding_location_without_line_is_file() -> None:
    finding = Finding.from_json(
        {
            "id": "X",
            "check": "sentinel:coverage",
            "severity": "info",
            "title": "t",
            "body": "b",
            "file": "src/cache.py",
            "line": None,
        }
    )
    assert finding.location == "src/cache.py"


def test_finding_marks_suppression() -> None:
    finding = Finding.from_json(
        {
            "id": "X",
            "check": "sentinel:secret",
            "severity": "error",
            "title": "t",
            "body": "b",
            "suppression": {"by": "matt@example.com", "profile": "staff_engineer"},
        }
    )
    assert finding.suppressed is True


def test_finding_actionable_covers_error_and_warning() -> None:
    base = {"id": "X", "check": "sentinel:lint", "title": "t", "body": "b"}
    assert Finding.from_json({**base, "severity": "error"}).actionable is True
    assert Finding.from_json({**base, "severity": "warning"}).actionable is True
    assert Finding.from_json({**base, "severity": "info"}).actionable is False


def test_finding_unknown_severity_falls_back_to_info() -> None:
    finding = Finding.from_json(
        {"id": "X", "check": "sentinel:lint", "severity": "critical", "title": "t", "body": "b"}
    )
    assert finding.severity is Severity.INFO


def test_run_result_requires_schema_version() -> None:
    with pytest.raises(SchemaError, match="schema_version"):
        RunResult.from_json({"status": "pass"})


def test_run_result_rejects_unknown_schema_version() -> None:
    with pytest.raises(SchemaError, match="Unsupported"):
        RunResult.from_json({"schema_version": 2, "status": "pass"})


def test_run_result_counts_by_severity(make_payload, make_finding) -> None:
    payload = make_payload(
        [
            make_finding(),
            make_finding(finding_id="A", severity="warning", blocking=False),
            make_finding(finding_id="B", severity="info", blocking=False),
        ]
    )
    result = RunResult.from_json(payload)
    assert result.error_count == 1
    assert result.warning_count == 1
    assert result.info_count == 1
    assert result.blocking_count == 1


def test_run_result_skips_malformed_finding_entries(make_payload, make_finding) -> None:
    payload = make_payload([make_finding()])
    payload["findings"] = [*payload["findings"], "not-an-object", 42]
    result = RunResult.from_json(payload)
    assert len(result.findings) == 1


def test_filter_severity_keeps_floor(make_payload, make_finding) -> None:
    payload = make_payload(
        [
            make_finding(),
            make_finding(finding_id="A", severity="warning", blocking=False),
            make_finding(finding_id="B", severity="info", blocking=False),
        ]
    )
    result = RunResult.from_json(payload).filter_severity(Severity.WARNING)
    assert {f.severity for f in result.findings} == {Severity.ERROR, Severity.WARNING}


def test_filter_severity_none_keeps_all(make_payload, make_finding) -> None:
    payload = make_payload([make_finding(severity="info", blocking=False)])
    assert len(RunResult.from_json(payload).filter_severity(None).findings) == 1


def test_filter_checks_accepts_engine_and_category(make_payload, make_finding) -> None:
    payload = make_payload(
        [
            make_finding(),
            make_finding(
                finding_id="B",
                check="review:security",
                severity="warning",
                blocking=False,
            ),
        ]
    )
    result = RunResult.from_json(payload)
    assert len(result.filter_checks({"sentinel"}).findings) == 1
    assert len(result.filter_checks({"secret"}).findings) == 1
    assert len(result.filter_checks({"sentinel:secret"}).findings) == 1
    assert len(result.filter_checks({"review"}).findings) == 1
    assert len(result.filter_checks(None).findings) == 2


def test_run_result_reads_summary_and_checks(make_payload) -> None:
    payload = make_payload(
        [],
        checks=[
            {
                "check": "sentinel:lint",
                "tier": "fast",
                "status": "skip",
                "blocking": True,
                "duration_ms": 3,
                "findings_count": 0,
                "threshold": None,
                "measured": None,
                "note": "ruff not found on PATH",
            }
        ],
    )
    result = RunResult.from_json(payload)
    assert result.summary["total"] == 0
    assert result.skipped_checks[0].status is CheckStatus.SKIP
    assert result.skipped_checks[0].note == "ruff not found on PATH"


def test_to_audit_dict_shape(make_payload, make_finding) -> None:
    result = RunResult.from_json(make_payload([make_finding()]))
    document = result.to_audit_dict()
    assert document["source"] == "gauntlet"
    assert document["summary"]["errors"] == 1
    assert document["findings"][0]["check"] == "sentinel:secret"


def test_empty_result_has_no_findings() -> None:
    result = RunResult.empty(tier="full")
    assert result.findings == []
    assert result.status.value == "pass"
    assert result.to_audit_dict()["summary"]["total"] == 0


def test_engines_match_the_frozen_contract() -> None:
    assert ENGINES == ("sentinel", "conformance", "review", "quality")
