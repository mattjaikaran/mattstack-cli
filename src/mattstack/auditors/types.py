"""Type parity auditor: the OpenAPI contract against the generated Zod schemas."""

from __future__ import annotations

from pathlib import Path

from mattstack.auditors.base import AuditFinding, AuditType, BaseAuditor, Severity
from mattstack.auditors.types_parity import find_drift
from mattstack.parsers.openapi_spec import (
    GENERATED_DIR,
    ZOD_FILE,
    component_schemas,
    find_contract,
    load_contract,
)
from mattstack.parsers.zod_schemas import parse_zod_file

REGENERATE = "Run `mattstack sync openapi` and commit the generated output"


class TypeSafetyAuditor(BaseAuditor):
    audit_type = AuditType.TYPES

    def run(self) -> list[AuditFinding]:
        found = find_contract(self.config.project_path)
        if found is None:
            self.add_finding(
                Severity.INFO,
                Path("."),
                0,
                "No OpenAPI contract found",
                "Export the backend schema (Django Ninja: `uv run python manage.py "
                "export_openapi`) or save it as openapi.json",
            )
            return self.findings
        project, source = found
        if not (project.frontend_dir / "package.json").is_file():
            return self.findings
        try:
            contract = load_contract(source)
        except (OSError, ValueError) as exc:
            self.add_finding(Severity.ERROR, self._rel(source), 0, str(exc), "Export it again")
            return self.findings
        zod_file = project.frontend_dir / GENERATED_DIR / ZOD_FILE
        if not zod_file.is_file():
            self.add_finding(
                Severity.WARNING,
                self._rel(zod_file),
                0,
                "No generated Zod schemas to compare with the OpenAPI contract",
                REGENERATE,
            )
            return self.findings
        for drift in find_drift(component_schemas(contract), parse_zod_file(zod_file)):
            self.add_finding(
                Severity.ERROR,
                self._rel(zod_file),
                drift.zod.line if drift.zod else 0,
                f"Zod drift: {drift.message}",
                REGENERATE,
            )
        return self.findings
