"""Typed models for the Gauntlet JSON contract.

Gauntlet writes one JSON document to stdout when you pass `--json`. This
module parses that document. It does not run Gauntlet; see `client.py`.

The shapes follow `docs/spec/finding-schema.md` in the Gauntlet repository.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

# The only schema version this module understands.
SUPPORTED_SCHEMA_VERSION = 1


class SchemaError(ValueError):
    """The JSON document does not match the Gauntlet wire format."""


class Severity(StrEnum):
    """Finding severity. Gauntlet defines exactly three levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class RunStatus(StrEnum):
    """Status of a whole Gauntlet run."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


class CheckStatus(StrEnum):
    """Status of one check inside a run."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


# The four Gauntlet engines. Every check id is `<engine>:<category>`, for
# example `sentinel:secret`. See `docs/spec/check-spec.md` in the Gauntlet
# repository.
ENGINES = ("sentinel", "conformance", "review", "quality")

SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
}


def _text(data: Mapping[str, Any], key: str, default: str = "") -> str:
    """Read a string field, falling back to ``default`` on a bad type."""
    value = data.get(key)
    return value if isinstance(value, str) else default


def _optional_text(data: Mapping[str, Any], key: str) -> str | None:
    """Read a nullable string field. An empty string becomes ``None``."""
    value = data.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _optional_int(data: Mapping[str, Any], key: str) -> int | None:
    """Read a nullable integer field. Booleans are rejected."""
    value = data.get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _flag(data: Mapping[str, Any], key: str, default: bool = False) -> bool:
    """Read a boolean field."""
    value = data.get(key)
    return value if isinstance(value, bool) else default


@dataclass(frozen=True)
class Finding:
    """One Gauntlet finding. Mirrors the Finding object in the wire format."""

    id: str
    check: str
    severity: Severity
    title: str
    body: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    suggested_fix: str | None = None
    doc_url: str | None = None
    blocking: bool = False
    suppressed: bool = False

    @property
    def engine(self) -> str:
        """Engine part of the check id, for example ``sentinel``."""
        return self.check.split(":", 1)[0]

    @property
    def category(self) -> str:
        """Category part of the check id, for example ``secret``."""
        parts = self.check.split(":", 1)
        return parts[1] if len(parts) == 2 else parts[0]

    @property
    def location(self) -> str:
        """Root-relative ``file:line`` for display. ``(repo)`` when global."""
        if self.file is None:
            return "(repo)"
        if self.line is None:
            return self.file
        return f"{self.file}:{self.line}"

    @property
    def actionable(self) -> bool:
        """Whether this finding is worth writing to a task list."""
        return self.severity in (Severity.ERROR, Severity.WARNING)

    def to_dict(self) -> dict[str, object]:
        """Render this finding in mattstack's audit JSON shape."""
        return {
            "id": self.id,
            "check": self.check,
            "engine": self.engine,
            "category": self.category,
            "severity": self.severity.value,
            "title": self.title,
            "body": self.body,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "suggested_fix": self.suggested_fix,
            "doc_url": self.doc_url,
            "blocking": self.blocking,
            "suppressed": self.suppressed,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Finding:
        """Parse one Finding object."""
        raw_severity = _text(data, "severity", Severity.INFO.value)
        try:
            severity = Severity(raw_severity)
        except ValueError:
            severity = Severity.INFO
        return cls(
            id=_text(data, "id"),
            check=_text(data, "check"),
            severity=severity,
            title=_text(data, "title"),
            body=_text(data, "body"),
            file=_optional_text(data, "file"),
            line=_optional_int(data, "line"),
            column=_optional_int(data, "column"),
            suggested_fix=_optional_text(data, "suggested_fix"),
            doc_url=_optional_text(data, "doc_url"),
            blocking=_flag(data, "blocking"),
            suppressed=data.get("suppression") is not None,
        )


@dataclass(frozen=True)
class CheckSummary:
    """One entry from the run's ``checks`` array."""

    check: str
    tier: str
    status: CheckStatus
    blocking: bool
    duration_ms: int
    findings_count: int
    threshold: float | None = None
    measured: float | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Render this summary in the audit JSON shape."""
        return {
            "check": self.check,
            "tier": self.tier,
            "status": self.status.value,
            "blocking": self.blocking,
            "duration_ms": self.duration_ms,
            "findings_count": self.findings_count,
            "threshold": self.threshold,
            "measured": self.measured,
            "note": self.note,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> CheckSummary:
        """Parse one CheckSummary object."""
        raw_status = _text(data, "status", CheckStatus.ERROR.value)
        try:
            status = CheckStatus(raw_status)
        except ValueError:
            status = CheckStatus.ERROR
        threshold = data.get("threshold")
        measured = data.get("measured")
        return cls(
            check=_text(data, "check"),
            tier=_text(data, "tier"),
            status=status,
            blocking=_flag(data, "blocking"),
            duration_ms=_optional_int(data, "duration_ms") or 0,
            findings_count=_optional_int(data, "findings_count") or 0,
            threshold=float(threshold) if isinstance(threshold, int | float) else None,
            measured=float(measured) if isinstance(measured, int | float) else None,
            note=_optional_text(data, "note"),
        )


@dataclass(frozen=True)
class RunResult:
    """A parsed ``gauntlet check --json`` document."""

    schema_version: int
    gauntlet_version: str
    tier: str
    status: RunStatus
    exit_code: int
    findings: list[Finding] = field(default_factory=list)
    checks: list[CheckSummary] = field(default_factory=list)
    commit: str = ""
    branch: str | None = None
    started_at: str = ""
    duration_ms: int = 0
    summary: dict[str, int] = field(default_factory=dict)
    # True when mattstack skipped the run and produced no findings itself.
    # A skipped run is not a pass; consumers must read this field before
    # they treat an empty finding list as clean.
    skipped: bool = False
    skip_reason: str | None = None

    @classmethod
    def empty(cls, *, tier: str = "", reason: str = "") -> RunResult:
        """Build a result with no findings, for a run that did not happen.

        The result is marked ``skipped``. Use this when mattstack skips the
        audit, for example when you did not install Gauntlet.
        """
        return cls(
            schema_version=SUPPORTED_SCHEMA_VERSION,
            gauntlet_version="",
            tier=tier,
            status=RunStatus.PASS,
            exit_code=0,
            skipped=True,
            skip_reason=reason or None,
        )

    @property
    def error_count(self) -> int:
        """Number of error-severity findings."""
        return sum(1 for f in self.findings if f.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        """Number of warning-severity findings."""
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        """Number of info-severity findings."""
        return sum(1 for f in self.findings if f.severity == Severity.INFO)

    @property
    def blocking_count(self) -> int:
        """Number of findings that block a commit."""
        return sum(1 for f in self.findings if f.blocking)

    @property
    def skipped_checks(self) -> list[CheckSummary]:
        """Checks that did not run because a tool was missing."""
        return [c for c in self.checks if c.status == CheckStatus.SKIP]

    def filter_severity(self, minimum: Severity | None) -> RunResult:
        """Return a copy with findings below ``minimum`` removed."""
        if minimum is None:
            return self
        floor = SEVERITY_ORDER[minimum]
        kept = [f for f in self.findings if SEVERITY_ORDER[f.severity] >= floor]
        return replace(self, findings=kept)

    def filter_checks(self, checks: set[str] | None) -> RunResult:
        """Return a copy holding only findings from ``checks``.

        Matches on the full check id (``sentinel:secret``), the engine
        (``sentinel``), or the category (``secret``). ``None`` means keep all.
        """
        if checks is None:
            return self
        kept = [
            f
            for f in self.findings
            if f.check in checks or f.engine in checks or f.category in checks
        ]
        return replace(self, findings=kept)

    def to_audit_dict(self) -> dict[str, object]:
        """Render the run in mattstack's audit JSON shape."""
        return {
            "schema_version": SUPPORTED_SCHEMA_VERSION,
            "source": "gauntlet",
            "tier": self.tier,
            "gauntlet_version": self.gauntlet_version,
            "status": self.status.value,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "exit_code": self.exit_code,
            "commit": self.commit,
            "branch": self.branch,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "summary": {
                "errors": self.error_count,
                "warnings": self.warning_count,
                "info": self.info_count,
                "blocking": self.blocking_count,
                "total": len(self.findings),
            },
            "checks": [c.to_dict() for c in self.checks],
            "findings": [f.to_dict() for f in self.findings],
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> RunResult:
        """Parse a whole ``gauntlet check --json`` document."""
        version = _optional_int(data, "schema_version")
        if version is None:
            msg = "Gauntlet output has no schema_version field"
            raise SchemaError(msg)
        if version != SUPPORTED_SCHEMA_VERSION:
            msg = (
                f"Unsupported Gauntlet schema_version {version}; "
                f"this mattstack understands {SUPPORTED_SCHEMA_VERSION}"
            )
            raise SchemaError(msg)

        raw_status = _text(data, "status", RunStatus.ERROR.value)
        try:
            status = RunStatus(raw_status)
        except ValueError:
            status = RunStatus.ERROR

        raw_findings = data.get("findings")
        findings = (
            [Finding.from_json(item) for item in raw_findings if isinstance(item, Mapping)]
            if isinstance(raw_findings, list)
            else []
        )

        raw_checks = data.get("checks")
        checks = (
            [CheckSummary.from_json(item) for item in raw_checks if isinstance(item, Mapping)]
            if isinstance(raw_checks, list)
            else []
        )

        raw_summary = data.get("summary")
        summary: dict[str, int] = {}
        if isinstance(raw_summary, Mapping):
            for key, value in raw_summary.items():
                if isinstance(value, int) and not isinstance(value, bool):
                    summary[str(key)] = value

        return cls(
            schema_version=version,
            gauntlet_version=_text(data, "gauntlet_version"),
            tier=_text(data, "tier"),
            status=status,
            exit_code=_optional_int(data, "exit_code") or 0,
            findings=findings,
            checks=checks,
            commit=_text(data, "commit"),
            branch=_optional_text(data, "branch"),
            started_at=_text(data, "started_at"),
            duration_ms=_optional_int(data, "duration_ms") or 0,
            summary=summary,
        )
