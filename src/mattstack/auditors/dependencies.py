"""Dependency auditor — checks pyproject.toml and package.json for issues."""

from __future__ import annotations

from pathlib import Path

from mattstack.auditors.base import AuditFinding, AuditType, BaseAuditor, Severity
from mattstack.parsers.dependencies import (
    Dependency,
    DependencyManifest,
    find_dependency_files,
    parse_package_json,
    parse_pyproject_toml,
)

# Known deprecated packages
DEPRECATED_PYTHON: dict[str, str] = {
    "nose": "Use pytest instead",
    "mock": "Use unittest.mock (stdlib) instead",
    "six": "Python 2 compatibility layer — drop if Python 3 only",
    "future": "Python 2 compatibility layer — drop if Python 3 only",
}

DEPRECATED_JS: dict[str, str] = {
    "moment": "Use date-fns or dayjs instead",
    "request": "Use fetch (built-in) or axios instead",
    "tslint": "Use oxlint instead",
    "eslint": "Use oxlint instead",
    "prettier": "Use oxfmt instead",
}

# Scoped packages flagged by prefix; every match is replaced by oxlint
DEPRECATED_JS_PREFIXES = ("@typescript-eslint/",)

# Type checker packages that indicate type stubs may be needed
TYPE_CHECKERS = {"mypy", "pyright", "pytype"}


class DependencyAuditor(BaseAuditor):
    audit_type = AuditType.DEPENDENCIES

    def run(self) -> list[AuditFinding]:
        dep_files = find_dependency_files(self.config.project_path)
        manifests: list[DependencyManifest] = []
        for f in dep_files:
            if f.name == "pyproject.toml":
                manifest = parse_pyproject_toml(f)
                self._check_python_deps(manifest)
                manifests.append(manifest)
            elif f.name == "package.json":
                manifest = parse_package_json(f)
                self._check_node_deps(manifest)
                manifests.append(manifest)

        self._check_cross_manifest_conflicts(manifests)
        return self.findings

    def _check_python_deps(self, manifest: DependencyManifest) -> None:
        """Check Python dependency issues."""
        rel_file = self._rel(manifest.file)
        seen_names: dict[str, Dependency] = {}
        has_type_checker = False
        has_type_stubs: set[str] = set()

        for dep in manifest.dependencies:
            lower_name = dep.name.lower().replace("-", "_")

            # Track type checkers and stubs
            if lower_name in TYPE_CHECKERS:
                has_type_checker = True
            if lower_name.startswith("types_") or lower_name.startswith("types-"):
                has_type_stubs.add(lower_name)

            # Check for unpinned dependencies
            if not dep.version_constraint:
                self.add_finding(
                    Severity.WARNING,
                    rel_file,
                    dep.line,
                    f"Unpinned dependency: {dep.name}",
                    f"Add version constraint, e.g. {dep.name}>=1.0",
                )

            # Check for overly broad constraints (>= without upper bound)
            elif ">=" in dep.version_constraint and "<" not in dep.version_constraint:
                self.add_finding(
                    Severity.INFO,
                    rel_file,
                    dep.line,
                    f"Overly broad constraint: {dep.name}{dep.version_constraint}",
                    "Consider adding an upper bound version constraint",
                )

            # Check for deprecated packages
            if lower_name in DEPRECATED_PYTHON:
                self.add_finding(
                    Severity.WARNING,
                    rel_file,
                    dep.line,
                    f"Deprecated package: {dep.name}",
                    DEPRECATED_PYTHON[lower_name],
                )

            # Check for duplicates (same package in regular and dev)
            if lower_name in seen_names:
                prev = seen_names[lower_name]
                if prev.dev != dep.dev:
                    self.add_finding(
                        Severity.ERROR,
                        rel_file,
                        dep.line,
                        f"Duplicate dependency: {dep.name} in both regular and dev dependencies",
                        "Remove from one of the dependency lists",
                    )
            else:
                seen_names[lower_name] = dep

        # Check for missing type stubs if type checker is present
        if has_type_checker:
            stubs_map = {
                "django": "django-stubs",
                "requests": "types-requests",
                "pyyaml": "types-pyyaml",
            }
            stub_normalized = {s.replace("-", "_") for s in has_type_stubs}
            for pkg, stub in stubs_map.items():
                stub_key = stub.lower().replace("-", "_")
                if pkg in seen_names and stub_key not in stub_normalized:
                    self.add_finding(
                        Severity.INFO,
                        rel_file,
                        seen_names[pkg].line,
                        f"Missing type stubs for {pkg}",
                        f"Add {stub} to dev dependencies",
                    )

    def _check_node_deps(self, manifest: DependencyManifest) -> None:
        """Check Node.js dependency issues."""
        rel_file = self._rel(manifest.file)
        seen_names: dict[str, Dependency] = {}

        for dep in manifest.dependencies:
            lower_name = dep.name.lower()

            # Check for wildcard/any version
            if dep.version_constraint in ("*", "latest", ""):
                self.add_finding(
                    Severity.WARNING,
                    rel_file,
                    dep.line,
                    f"Unpinned dependency: {dep.name} ({dep.version_constraint or 'no version'})",
                    "Pin to a specific version range, e.g. ^1.0.0",
                )

            # Check for deprecated packages
            advice = DEPRECATED_JS.get(lower_name)
            if advice is None and lower_name.startswith(DEPRECATED_JS_PREFIXES):
                advice = "Use oxlint instead"
            if advice is not None:
                self.add_finding(
                    Severity.WARNING,
                    rel_file,
                    dep.line,
                    f"Deprecated package: {dep.name}",
                    advice,
                )

            # Check for duplicates
            if lower_name in seen_names:
                prev = seen_names[lower_name]
                if prev.dev != dep.dev:
                    self.add_finding(
                        Severity.ERROR,
                        rel_file,
                        dep.line,
                        f"Duplicate dependency: {dep.name} in deps and devDeps",
                        "Remove from one of the dependency objects",
                    )
            else:
                seen_names[lower_name] = dep

    def _check_cross_manifest_conflicts(self, manifests: list[DependencyManifest]) -> None:
        """Check for version conflicts across manifests."""
        # Collect shared tool versions (e.g., typescript)
        ts_versions: list[tuple[Path, str]] = []
        for manifest in manifests:
            for dep in manifest.dependencies:
                if dep.name.lower() == "typescript":
                    ts_versions.append((manifest.file, dep.version_constraint))

        if len(ts_versions) > 1:
            versions_set = {v for _, v in ts_versions}
            if len(versions_set) > 1:
                for file_path, version in ts_versions:
                    self.add_finding(
                        Severity.WARNING,
                        self._rel(file_path),
                        1,
                        f"TypeScript version conflict: {version}",
                        "Align TypeScript versions across packages",
                    )
