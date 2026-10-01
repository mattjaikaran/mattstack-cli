"""Vulnerability scanning auditor — checks dependencies for known CVEs."""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404 # Required CLI subprocess support.
from pathlib import Path
from typing import Any

import httpx

from mattstack.auditors.base import AuditFinding, AuditType, BaseAuditor, Severity
from mattstack.parsers.dependencies import (
    find_dependency_files,
    parse_package_json,
    parse_pyproject_toml,
)


class VulnerabilityAuditor(BaseAuditor):
    """Check dependencies for known vulnerabilities."""

    audit_type = AuditType.VULNERABILITIES

    def run(self) -> list[AuditFinding]:
        dep_files = find_dependency_files(self.config.project_path)
        for manifest_file in dep_files:
            if manifest_file.name == "pyproject.toml":
                self._check_python_vulns(manifest_file)
            elif manifest_file.name == "package.json":
                self._check_node_vulns(manifest_file)
        return self.findings

    def _check_python_vulns(self, manifest: Path) -> None:
        """Check Python deps via pip-audit, fallback to OSV API."""
        parsed = parse_pyproject_toml(manifest)
        if not parsed.dependencies:
            return

        # Try pip-audit first
        if self._try_pip_audit(manifest):
            return

        # Fallback: check via OSV API
        with httpx.Client(timeout=10) as client:
            for dep in parsed.dependencies:
                self._check_osv(
                    client, dep.name, dep.version_constraint, "PyPI", manifest, dep.line
                )

    def _check_node_vulns(self, manifest: Path) -> None:
        """Check Node deps via npm audit, fallback to OSV API."""
        parsed = parse_package_json(manifest)
        if not parsed.dependencies:
            return

        # Try npm/bun audit first
        if self._try_npm_audit(manifest):
            return

        # Fallback: check via OSV API
        with httpx.Client(timeout=10) as client:
            for dep in parsed.dependencies:
                self._check_osv(client, dep.name, dep.version_constraint, "npm", manifest, dep.line)

    def _try_pip_audit(self, manifest: Path) -> bool:
        """Run pip-audit if available. Returns True if it ran successfully."""
        try:
            result = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
                ["pip-audit", "--format=json", "--desc", "-r", str(manifest)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=manifest.parent,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

        if result.returncode not in (0, 1):
            return False

        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return False

        dependencies = data if isinstance(data, list) else data.get("dependencies", [])
        for entry in dependencies:
            vulns = entry.get("vulns", [])
            for vuln in vulns:
                severity = self._map_severity(vuln.get("fix_versions", []))
                self.add_finding(
                    severity,
                    self._rel(manifest),
                    0,
                    f"Vulnerability in {entry.get('name', '?')} {entry.get('version', '?')}: "
                    f"{vuln.get('id', 'unknown')} — {vuln.get('description', '')[:120]}",
                    f"Upgrade to: {', '.join(vuln.get('fix_versions', []))}",
                )
        return True

    def _try_npm_audit(self, manifest: Path) -> bool:
        """Run npm audit if available. Returns True if it ran successfully."""
        try:
            result = subprocess.run(  # nosec B603, B607 # Argv; trust project tools and PATH.
                ["npm", "audit", "--json"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=manifest.parent,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return False

        vulnerabilities = data.get("vulnerabilities", {})
        for pkg_name, info in vulnerabilities.items():
            severity_str = info.get("severity", "moderate")
            severity = self._npm_severity(severity_str)
            via = info.get("via", [])
            desc = ""
            if via and isinstance(via[0], dict):
                desc = via[0].get("title", "")
            self.add_finding(
                severity,
                self._rel(manifest),
                0,
                f"Vulnerability in {pkg_name}: {desc}" if desc else f"Vulnerability in {pkg_name}",
                f"Run 'npm audit fix' or update {pkg_name}",
            )
        return True

    def _check_osv(
        self,
        client: httpx.Client,
        package_name: str,
        version: str,
        ecosystem: str,
        manifest: Path,
        line: int,
    ) -> None:
        """Query OSV.dev API for known vulnerabilities."""
        # Strip version specifiers for query
        clean_version = re.sub(r"^[>=<~^!= ]+", "", version)
        if not clean_version:
            return

        payload = {
            "package": {"name": package_name, "ecosystem": ecosystem},
            "version": clean_version,
        }

        try:
            resp = client.post("https://api.osv.dev/v1/query", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return  # Silently skip on network, HTTP status, and malformed JSON errors

        vulns = data.get("vulns", [])
        for vuln in vulns:
            vuln_id = vuln.get("id", "unknown")
            summary = vuln.get("summary", "")[:120]
            sev = self._osv_severity(vuln)
            self.add_finding(
                sev,
                self._rel(manifest),
                line,
                f"Known vulnerability in {package_name} {clean_version}: {vuln_id} — {summary}",
                f"Check https://osv.dev/vulnerability/{vuln_id}",
            )

    @staticmethod
    def _map_severity(fix_versions: list[str]) -> Severity:
        """Map pip-audit finding to severity (has fix = ERROR, no fix = WARNING)."""
        return Severity.ERROR if fix_versions else Severity.WARNING

    @staticmethod
    def _npm_severity(severity_str: str) -> Severity:
        """Map npm severity string to our Severity enum."""
        if severity_str in ("critical", "high"):
            return Severity.ERROR
        elif severity_str == "moderate":
            return Severity.WARNING
        return Severity.INFO

    @staticmethod
    def _osv_severity(vuln: dict[str, Any]) -> Severity:
        """Map OSV vulnerability to severity based on CVSS or severity field."""
        severity_list = vuln.get("severity", [])
        for sev in severity_list:
            score = sev.get("score", "")
            # CVSS score parsing
            if ":" in score:
                try:
                    parts = score.split("/")
                    for part in parts:
                        if part.startswith("AV:"):
                            continue
                        # Try to find numeric score
                except (ValueError, IndexError):
                    pass
            sev_type = sev.get("type", "")
            if sev_type == "CVSS_V3":
                # High severity if present
                return Severity.ERROR
        # Default to WARNING if we can't determine
        return Severity.WARNING
