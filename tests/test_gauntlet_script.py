"""Gate 10 builds the wheel and smoke-tests it in a clean virtual environment."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "gauntlet.py"
SDIST_NAME = "mattstack-0.9.1.tar.gz"
WHEEL_NAME = "mattstack-0.9.1-py3-none-any.whl"


def _load_gauntlet() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gauntlet_script", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(
    monkeypatch: pytest.MonkeyPatch, gauntlet: ModuleType, fail_at: int | None = None
) -> list[tuple[list[str], Path | None, int]]:
    """Replace ``_run`` with a recorder that writes the artifacts a build would."""
    calls: list[tuple[list[str], Path | None, int]] = []

    def fake_run(cmd: list[str], cwd: Path | None = None, timeout: int = 120) -> tuple[int, str]:
        calls.append((list(cmd), cwd, timeout))
        if fail_at is not None and len(calls) - 1 == fail_at:
            return 1, "boom"
        if "-o" in cmd:
            out_dir = Path(cmd[cmd.index("-o") + 1])
            if "--sdist" in cmd:
                (out_dir / SDIST_NAME).write_text("sdist")
            elif "--wheel" in cmd:
                (out_dir / WHEEL_NAME).write_text("wheel")
        return 0, ""

    monkeypatch.setattr(gauntlet, "_run", fake_run)
    return calls


def test_install_gate_builds_the_wheel_and_runs_help(monkeypatch: pytest.MonkeyPatch) -> None:
    gauntlet = _load_gauntlet()
    calls = _record(monkeypatch, gauntlet)

    assert gauntlet._gate_install() is True

    assert [cmd[1] for cmd, _, _ in calls[:4]] == ["build", "build", "venv", "pip"]
    assert len(calls) == 6
    sdist_call, wheel_call = calls[0][0], calls[1][0]
    assert sdist_call[2] == "--sdist"
    assert wheel_call[2] == "--wheel"
    assert wheel_call[-1] == str(Path(sdist_call[sdist_call.index("-o") + 1]) / SDIST_NAME)
    work = Path(sdist_call[sdist_call.index("-o") + 1])
    assert wheel_call[wheel_call.index("-o") + 1] == str(work)
    venv = Path(calls[2][0][2])
    assert venv.parent == work
    install_call = calls[3][0]
    python = str(venv / "bin" / "python")
    assert install_call[3:5] == ["--python", python]
    assert install_call[-1] == str(work / WHEEL_NAME)
    executable = str(venv / "bin" / "mattstack")
    assert calls[4][0] == [executable, "--help"]
    assert calls[5][0] == [executable, "sync", "--help"]
    assert all(timeout > 120 for _, _, timeout in calls)
    assert not work.exists()


@pytest.mark.parametrize("fail_at", range(6))
def test_install_gate_fails_when_a_step_fails(
    monkeypatch: pytest.MonkeyPatch, fail_at: int
) -> None:
    gauntlet = _load_gauntlet()
    calls = _record(monkeypatch, gauntlet, fail_at=fail_at)

    assert gauntlet._gate_install() is False
    assert len(calls) == fail_at + 1


def test_install_gate_fails_when_the_build_produces_no_wheel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gauntlet = _load_gauntlet()

    def fake_run(cmd: list[str], cwd: Path | None = None, timeout: int = 120) -> tuple[int, str]:
        if "--sdist" in cmd:
            Path(cmd[cmd.index("-o") + 1], SDIST_NAME).write_text("sdist")
        return 0, ""

    monkeypatch.setattr(gauntlet, "_run", fake_run)

    assert gauntlet._gate_install() is False
