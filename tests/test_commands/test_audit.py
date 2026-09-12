"""Tests for the audit command and its formatter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mattstack.commands.audit import run_audit
from mattstack.gauntlet.html_report import generate_html_report
from mattstack.gauntlet.models import RunResult
from mattstack.gauntlet.report import (
    AUDIT_END,
    AUDIT_START,
    install_instructions,
    write_todo,
)


def _make_project(tmp_path: Path) -> Path:
    """Create a project directory with a gauntlet.toml."""
    project = tmp_path / "test-proj"
    project.mkdir()
    (project / "gauntlet.toml").write_text("[integrations]\nskip_if_absent = true\n")
    return project


def _two_findings(make_payload, make_finding):
    return make_payload(
        [
            make_finding(),
            make_finding(
                finding_id="GAUNTLET-REVIEW-READABILITY-003",
                check="review:readability",
                severity="info",
                title="Function name is unclear",
                blocking=False,
                suggested_fix=None,
            ),
        ]
    )


# ---------------------------------------------------------------------------
# run_audit: end to end over the real subprocess boundary
# ---------------------------------------------------------------------------


def test_audit_reports_gauntlet_findings(
    tmp_path: Path, fake_gauntlet: Path, fake_run, make_payload, make_finding
) -> None:
    project = _make_project(tmp_path)
    fake_run(make_payload([make_finding()]), exit_code=2)
    run_audit(project, no_todo=True)


def test_audit_json_output_is_gauntlet_shaped(
    tmp_path: Path, fake_gauntlet: Path, fake_run, make_payload, make_finding, capsys
) -> None:
    project = _make_project(tmp_path)
    fake_run(make_payload([make_finding()]), exit_code=2)
    run_audit(project, json_output=True, no_todo=True)
    captured = capsys.readouterr().out
    assert '"source": "gauntlet"' in captured.replace("\\", "")
    assert "GAUNTLET-SENTINEL-SECRET-001" in captured


def test_audit_skips_when_gauntlet_absent(tmp_path: Path, monkeypatch) -> None:
    """A project that opted in gets a one-line skip, not a crash."""
    project = _make_project(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    run_audit(project, no_todo=True)


def test_audit_fails_when_gauntlet_absent_and_not_opted_in(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "strict"
    project.mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    with pytest.raises(Exception):  # noqa: B017 - typer.Exit
        run_audit(project, no_todo=True)


def test_audit_skip_if_absent_override(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "strict"
    project.mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    run_audit(project, no_todo=True, skip_if_absent=True)


def test_audit_reports_usage_error(tmp_path: Path, fake_gauntlet: Path, fake_run) -> None:
    project = _make_project(tmp_path)
    fake_run({}, exit_code=1, stderr="unknown flag: --nope")
    with pytest.raises(Exception):  # noqa: B017 - typer.Exit
        run_audit(project, no_todo=True)


def test_audit_rejects_bad_type(tmp_path: Path, fake_gauntlet: Path) -> None:
    project = _make_project(tmp_path)
    with pytest.raises(Exception):  # noqa: B017 - typer.Exit
        run_audit(project, audit_types=["nonsense"], no_todo=True)


def test_audit_rejects_bad_severity(tmp_path: Path, fake_gauntlet: Path) -> None:
    project = _make_project(tmp_path)
    with pytest.raises(Exception):  # noqa: B017 - typer.Exit
        run_audit(project, min_severity="critical", no_todo=True)


def test_audit_type_filter_keeps_matching_engine(
    tmp_path: Path, fake_gauntlet: Path, fake_run, make_payload, make_finding, capsys
) -> None:
    project = _make_project(tmp_path)
    payload = make_payload(
        [
            make_finding(),
            make_finding(
                finding_id="B",
                check="review:readability",
                severity="warning",
                blocking=False,
            ),
        ]
    )
    fake_run(payload, exit_code=2)
    run_audit(project, audit_types=["review"], json_output=True, no_todo=True)
    captured = capsys.readouterr().out
    assert "review:readability" in captured
    assert "sentinel:secret" not in captured


def test_audit_severity_filter_drops_info(
    tmp_path: Path, fake_gauntlet: Path, fake_run, make_payload, make_finding, capsys
) -> None:
    project = _make_project(tmp_path)
    fake_run(_two_findings(make_payload, make_finding), exit_code=2)
    run_audit(project, min_severity="error", json_output=True, no_todo=True)
    captured = capsys.readouterr().out
    assert "GAUNTLET-SENTINEL-SECRET-001" in captured
    assert "GAUNTLET-REVIEW-READABILITY-003" not in captured


def test_audit_bad_path_exits() -> None:
    with pytest.raises(Exception):  # noqa: B017 - typer.Exit
        run_audit(Path("/nonexistent/path-xyz"), no_todo=True)


def test_audit_tier_passes_through(
    tmp_path: Path, fake_gauntlet: Path, fake_run, make_payload, capsys
) -> None:
    project = _make_project(tmp_path)
    fake_run(make_payload([], tier="fast", status="pass", exit_code=0))
    run_audit(project, tier="fast", json_output=True, no_todo=True)
    assert '"tier": "fast"' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# write_todo
# ---------------------------------------------------------------------------


def test_write_todo_uses_markers(make_payload, make_finding, tmp_path: Path) -> None:
    result = RunResult.from_json(make_payload([make_finding()]))
    todo_path = write_todo(result, tmp_path)
    assert todo_path is not None
    content = todo_path.read_text()
    assert AUDIT_START in content
    assert AUDIT_END in content
    assert "GAUNTLET-SENTINEL-SECRET-001" in content
    assert "app.py:42" in content


def test_write_todo_is_idempotent(make_payload, make_finding, tmp_path: Path) -> None:
    result = RunResult.from_json(make_payload([make_finding()]))
    write_todo(result, tmp_path)
    write_todo(result, tmp_path)
    assert (tmp_path / "tasks" / "todo.md").read_text().count(AUDIT_START) == 1


def test_write_todo_preserves_existing_content(make_payload, make_finding, tmp_path: Path) -> None:
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "todo.md").write_text("# Project TODO\n\nHand written work.\n")
    result = RunResult.from_json(make_payload([make_finding()]))
    write_todo(result, tmp_path)
    content = (tasks / "todo.md").read_text()
    assert "Hand written work." in content
    assert AUDIT_START in content


def test_write_todo_skips_when_nothing_actionable(
    make_payload, make_finding, tmp_path: Path
) -> None:
    result = RunResult.from_json(make_payload([make_finding(severity="info", blocking=False)]))
    assert write_todo(result, tmp_path) is None
    assert not (tmp_path / "tasks" / "todo.md").exists()


def test_write_todo_skips_when_no_findings(make_payload, tmp_path: Path) -> None:
    result = RunResult.from_json(make_payload([]))
    assert write_todo(result, tmp_path) is None


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------


def test_html_report_contains_findings(make_payload, make_finding, tmp_path: Path) -> None:
    result = RunResult.from_json(make_payload([make_finding()]))
    html = generate_html_report(result, tmp_path)
    assert "<!DOCTYPE html>" in html
    assert "GAUNTLET-SENTINEL-SECRET-001" not in html  # id is not shown
    assert "Hardcoded AWS access key" in html
    assert 'data-severity="error"' in html
    assert 'data-category="secret"' in html
    assert "blocking" in html
    assert "Generated by mattstack audit" in html


def test_html_report_escapes_content(make_payload, make_finding, tmp_path: Path) -> None:
    finding = make_finding(title="<script>alert(1)</script>")
    result = RunResult.from_json(make_payload([finding]))
    html = generate_html_report(result, tmp_path)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_html_report_lists_skipped_checks(make_payload, tmp_path: Path) -> None:
    result = RunResult.from_json(
        make_payload(
            [],
            checks=[
                {
                    "check": "sentinel:lint",
                    "tier": "fast",
                    "status": "skip",
                    "blocking": True,
                    "duration_ms": 1,
                    "findings_count": 0,
                    "note": "ruff not found on PATH",
                }
            ],
        )
    )
    html = generate_html_report(result, tmp_path)
    assert "Skipped checks" in html
    assert "ruff not found on PATH" in html


def test_html_report_empty_state(make_payload, tmp_path: Path) -> None:
    html = generate_html_report(RunResult.from_json(make_payload([])), tmp_path)
    assert "No findings" in html


# ---------------------------------------------------------------------------
# install instructions
# ---------------------------------------------------------------------------


def test_install_instructions_name_the_binary() -> None:
    message = install_instructions("gauntlet")
    assert "gauntlet" in message
    assert "github.com/mattjaikaran/gauntlet" in message


def test_audit_json_skipped_run_is_valid_json(tmp_path: Path, monkeypatch, capsys) -> None:
    project = _make_project(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    run_audit(project, json_output=True, no_todo=True)
    document = json.loads(capsys.readouterr().out)
    assert document["source"] == "gauntlet"
    assert document["summary"]["total"] == 0


def test_audit_json_skipped_run_declares_itself(tmp_path: Path, monkeypatch, capsys) -> None:
    """A skipped run must not look like a clean pass to a JSON consumer."""
    project = _make_project(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    run_audit(project, json_output=True, no_todo=True)
    document = json.loads(capsys.readouterr().out)
    assert document["skipped"] is True
    assert "Gauntlet is not installed" in document["skip_reason"]


def test_audit_json_real_run_is_not_skipped(
    tmp_path: Path, fake_gauntlet: Path, fake_run, make_payload, capsys
) -> None:
    project = _make_project(tmp_path)
    fake_run(make_payload([], status="pass", exit_code=0))
    run_audit(project, json_output=True, no_todo=True)
    document = json.loads(capsys.readouterr().out)
    assert document["skipped"] is False
    assert document["skip_reason"] is None
