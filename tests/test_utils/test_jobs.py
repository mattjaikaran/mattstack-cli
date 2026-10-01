"""Tests for labeled parallel job execution."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from rich.console import Console

from mattstack.utils import jobs
from mattstack.utils.jobs import COMMAND_NOT_FOUND, LabeledJob, run_labeled_jobs


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    buffer = io.StringIO()
    monkeypatch.setattr(jobs, "console", Console(file=buffer, width=200, color_system=None))
    return buffer


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_labels_and_bracketed_output_render_literally(
    tmp_path: Path, captured: io.StringIO
) -> None:
    codes = run_labeled_jobs(
        [
            LabeledJob("[backend]", [_py("print('test_x[/tmp/y] PASSED')")], tmp_path),
            LabeledJob("[frontend]", [_py("print('[bold]ok')")], tmp_path),
        ]
    )
    assert codes == [0, 0]
    out = captured.getvalue()
    assert "[backend] test_x[/tmp/y] PASSED" in out
    assert "[frontend] [bold]ok" in out


def test_any_failing_step_fails_the_job(tmp_path: Path, captured: io.StringIO) -> None:
    job = LabeledJob("[backend]", [_py("raise SystemExit(3)"), _py("print('after')")], tmp_path)
    assert run_labeled_jobs([job]) == [3]
    assert "after" in captured.getvalue()


def test_missing_executable_fails_only_that_job(
    tmp_path: Path, captured: io.StringIO, capsys: pytest.CaptureFixture[str]
) -> None:
    codes = run_labeled_jobs(
        [
            LabeledJob("[backend]", [["mattstack-no-such-tool-xyz"]], tmp_path),
            LabeledJob("[frontend]", [_py("print('ran')")], tmp_path),
        ]
    )
    assert codes == [COMMAND_NOT_FOUND, 0]
    assert "[frontend] ran" in captured.getvalue()
    assert "Command not found: mattstack-no-such-tool-xyz" in capsys.readouterr().err
