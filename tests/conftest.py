"""Test fixtures for mattstack."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from mattstack.config import ProjectConfig, ProjectType, Variant

# A stand-in for the real Gauntlet binary. It echoes the JSON document in
# the FAKE_GAUNTLET_PAYLOAD environment variable and exits with
# FAKE_GAUNTLET_EXIT. This exercises the real subprocess boundary.
FAKE_GAUNTLET_SCRIPT = """\
#!/usr/bin/env python3
import os
import sys
import time

sleep_for = float(os.environ.get("FAKE_GAUNTLET_SLEEP", "0"))
if sleep_for:
    time.sleep(sleep_for)
sys.stdout.write(os.environ.get("FAKE_GAUNTLET_PAYLOAD", ""))
sys.stderr.write(os.environ.get("FAKE_GAUNTLET_STDERR", ""))
sys.exit(int(os.environ.get("FAKE_GAUNTLET_EXIT", "0")))
"""


def gauntlet_finding(
    *,
    finding_id: str = "GAUNTLET-SENTINEL-SECRET-001",
    check: str = "sentinel:secret",
    severity: str = "error",
    title: str = "Hardcoded AWS access key",
    body: str = "A value matching the AWS access key pattern appears in app.py.",
    file: str | None = "app.py",
    line: int | None = 42,
    suggested_fix: str | None = "Read the key from the environment.",
    blocking: bool = True,
    suppression: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one Finding object for a fake Gauntlet run."""
    return {
        "id": finding_id,
        "check": check,
        "severity": severity,
        "title": title,
        "body": body,
        "file": file,
        "line": line,
        "column": 15,
        "suggested_fix": suggested_fix,
        "doc_url": None,
        "provenance": {"commit": "abc123", "adapter": {"name": "python", "version": "0.4.0"}},
        "blocking": blocking,
        "suppression": suppression,
    }


def gauntlet_payload(
    findings: list[dict[str, Any]] | None = None,
    *,
    tier: str = "full",
    status: str = "fail",
    exit_code: int = 2,
    checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a whole `gauntlet check --json` document."""
    items = findings if findings is not None else [gauntlet_finding()]
    return {
        "schema_version": 1,
        "gauntlet_version": "0.4.0-alpha",
        "tier": tier,
        "commit": "5b8c1d9a4e2f3c7b6a5d4e3f2c1b0a9d8e7f6c5b",
        "branch": "main",
        "started_at": "2025-01-15T10:30:00Z",
        "duration_ms": 4218,
        "status": status,
        "exit_code": exit_code,
        "findings": items,
        "probes": [],
        "checks": checks or [],
        "summary": {
            "total": len(items),
            "pass": 0,
            "fail": len(items),
            "skip": 0,
            "error": 0,
            "blocking": sum(1 for f in items if f.get("blocking")),
            "advisory": 0,
        },
    }


@pytest.fixture
def fake_gauntlet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write an executable fake Gauntlet and put it first on PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    binary = bin_dir / "gauntlet"
    binary.write_text(FAKE_GAUNTLET_SCRIPT, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return binary


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch):
    """Return a helper that stages one fake Gauntlet run.

    ``payload`` accepts a document dict or a raw string, so a test can
    stage output that is not valid JSON.
    """

    def _stage(
        payload: dict[str, Any] | str,
        *,
        exit_code: int = 0,
        stderr: str = "",
        sleep: float = 0.0,
    ) -> None:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        monkeypatch.setenv("FAKE_GAUNTLET_PAYLOAD", text)
        monkeypatch.setenv("FAKE_GAUNTLET_EXIT", str(exit_code))
        monkeypatch.setenv("FAKE_GAUNTLET_STDERR", stderr)
        monkeypatch.setenv("FAKE_GAUNTLET_SLEEP", str(sleep))

    return _stage


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def starter_fullstack_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="test-project",
        path=tmp_path / "test-project",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.STARTER,
    )


@pytest.fixture
def b2b_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="test-b2b",
        path=tmp_path / "test-b2b",
        project_type=ProjectType.FULLSTACK,
        variant=Variant.B2B,
    )


@pytest.fixture
def backend_only_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="test-api",
        path=tmp_path / "test-api",
        project_type=ProjectType.BACKEND_ONLY,
        variant=Variant.STARTER,
    )


@pytest.fixture
def frontend_only_config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        name="test-frontend",
        path=tmp_path / "test-frontend",
        project_type=ProjectType.FRONTEND_ONLY,
        variant=Variant.STARTER,
        use_celery=False,
        use_redis=False,
    )


@pytest.fixture
def make_finding():
    """Return the Finding builder."""
    return gauntlet_finding


@pytest.fixture
def make_payload():
    """Return the run-document builder."""
    return gauntlet_payload
