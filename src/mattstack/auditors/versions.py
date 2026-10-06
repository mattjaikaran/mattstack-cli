"""Version drift across a project's components and generated root files.

Each tool or service version comes from the files that pin it (lockfiles,
manifests, Compose images, Dockerfiles; see ``utils.versions``). Two pins
disagree when they differ at the precision both record, so ``3.13`` and
``3.13.15`` agree, and ``17`` and ``16`` do not. A range such as
``requires-python = ">=3.13"`` is a floor: only a pin below it disagrees.
"""

from __future__ import annotations

from pathlib import Path

from mattstack.auditors.base import AuditFinding, AuditType, Severity
from mattstack.utils.versions import FLOOR_SUFFIX, is_floor, version_sources


def _parts(version: str) -> list[int]:
    return [int(part) for part in version.split(".")]


def _agree(left: str, right: str) -> bool:
    a, b = _parts(left), _parts(right)
    width = min(len(a), len(b))
    return a[:width] == b[:width]


def _below(pin: str, floor: str) -> bool:
    a, b = _parts(pin), _parts(floor)
    width = min(len(a), len(b))
    return a[:width] < b[:width]


def _finding(root: Path, key: str, source: str, message: str) -> AuditFinding:
    return AuditFinding(
        category=AuditType.DEPENDENCIES,
        severity=Severity.WARNING,
        file=root / source.removesuffix(FLOOR_SUFFIX),
        line=0,
        message=message,
        suggestion=f"Pin one {key} version in every file that records it",
    )


def audit_versions(root: Path) -> tuple[dict[str, dict[str, str]], list[AuditFinding]]:
    """Return every recorded version by source, and one finding per disagreement."""
    sources = version_sources(root)
    findings: list[AuditFinding] = []
    for key, found in sorted(sources.items()):
        pins = [(source, version) for source, version in found.items() if not is_floor(source)]
        floors = [(source, version) for source, version in found.items() if is_floor(source)]
        for source, version in pins[1:]:
            first_source, first = pins[0]
            if not _agree(first, version):
                message = f"{key} {version} in {source} disagrees with {first} in {first_source}"
                findings.append(_finding(root, key, source, message))
        for floor_source, floor in floors:
            for source, version in pins:
                if _below(version, floor):
                    label = floor_source.removesuffix(FLOOR_SUFFIX)
                    message = f"{key} {version} in {source} is below the {label} floor {floor}"
                    findings.append(_finding(root, key, source, message))
    return sources, findings
