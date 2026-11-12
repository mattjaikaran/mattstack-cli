"""``scripts/smoke_scaffold.py`` scaffolds each preset and runs ``just ci`` in it."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

from mattstack.presets import PRESETS

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "smoke_scaffold.py"


class Call(NamedTuple):
    cmd: list[str]
    cwd: Path
    env: dict[str, str]
    step: str
    preset: str


class FakeRunner:
    """Record every step and answer with the configured exit code."""

    def __init__(self, codes: dict[tuple[str, str], int] | None = None) -> None:
        self.codes = codes or {}
        self.calls: list[Call] = []

    def __call__(
        self,
        cmd: list[str],
        cwd: Path,
        env: dict[str, str],
        text: bool,
        capture_output: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        if cmd[0] == "just":
            step, preset = "just ci", Path(cwd).name.removeprefix("smoke-")
        else:
            step, preset = "init", cmd[cmd.index("-p") + 1]
        self.calls.append(Call(list(cmd), Path(cwd), dict(env), step, preset))
        code = self.codes.get((step, preset), 0)
        return subprocess.CompletedProcess(cmd, code, f"{step} output\n", "")


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("smoke_scaffold_script", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    return _load_script()


def test_default_run_scaffolds_then_runs_ci_for_each_default_preset(
    script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeRunner()

    assert script.main([], runner=runner) == 0

    expected = [(step, preset) for preset in script.DEFAULT_PRESETS for step in ("init", "just ci")]
    assert [(call.step, call.preset) for call in runner.calls] == expected
    init = runner.calls[0]
    assert init.cmd == [
        sys.executable,
        "-m",
        "mattstack",
        "init",
        "smoke-starter-fullstack",
        "-p",
        "starter-fullstack",
        "-o",
        str(init.cwd),
    ]
    ci = runner.calls[1]
    assert ci.cmd == ["just", "ci"]
    assert ci.cwd == init.cwd / "smoke-starter-fullstack"
    for call in runner.calls:
        assert call.env["GIT_CONFIG_GLOBAL"] == "/dev/null"
        assert call.env["GIT_CONFIG_COUNT"] == "0"
    out = capsys.readouterr().out
    for preset in script.DEFAULT_PRESETS:
        assert f"PASS {preset}" in out


def test_failing_ci_fails_the_run_and_other_presets_still_run(
    script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeRunner({("just ci", "starter-fullstack"): 1})

    assert script.main([], runner=runner) == 1

    assert [call.preset for call in runner.calls if call.step == "just ci"] == list(
        script.DEFAULT_PRESETS
    )
    out = capsys.readouterr().out
    assert "FAIL starter-fullstack: just ci exited 1" in out
    assert "    just ci output" in out
    assert "PASS starter-api" in out


def test_failing_init_skips_ci_for_that_preset(
    script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeRunner({("init", "starter-api"): 1})

    assert script.main([], runner=runner) == 1

    assert not any(call.step == "just ci" and call.preset == "starter-api" for call in runner.calls)
    assert any(
        call.step == "just ci" and call.preset == "starter-frontend" for call in runner.calls
    )
    out = capsys.readouterr().out
    assert "FAIL starter-api: init exited 1" in out
    assert "    init output" in out


def test_unknown_preset_returns_two_and_runs_nothing(
    script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeRunner()

    assert script.main(["--preset", "nope"], runner=runner) == 2

    assert runner.calls == []
    err = capsys.readouterr().err
    assert "nope" in err
    for preset in PRESETS:
        assert preset in err


def test_all_covers_every_preset(script: ModuleType) -> None:
    runner = FakeRunner()

    assert script.main(["--all"], runner=runner) == 0

    assert [call.preset for call in runner.calls if call.step == "init"] == list(PRESETS)
    assert len(runner.calls) == 2 * len(PRESETS)


def test_missing_just_returns_two_and_runs_nothing(
    monkeypatch: pytest.MonkeyPatch, script: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    runner = FakeRunner()

    assert script.main([], runner=runner) == 2

    assert runner.calls == []
    assert "just" in capsys.readouterr().err
