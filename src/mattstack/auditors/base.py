"""Shared finding types for the version-drift audit."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class AuditType(StrEnum):
    TYPES = "types"
    QUALITY = "quality"
    ENDPOINTS = "endpoints"
    TESTS = "tests"
    DEPENDENCIES = "dependencies"
    VULNERABILITIES = "vulnerabilities"


@dataclass
class AuditFinding:
    category: AuditType
    severity: Severity
    file: Path
    line: int
    message: str
    suggestion: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "file": str(self.file),
            "line": self.line,
            "message": self.message,
            "suggestion": self.suggestion,
        }
