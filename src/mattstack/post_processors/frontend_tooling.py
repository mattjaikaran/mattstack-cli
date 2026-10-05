"""Use locked local quality tools for React, leaving Next.js tooling alone."""

from __future__ import annotations

import json
import re
from pathlib import Path

from mattstack.config import ProjectConfig
from mattstack.templates.frontend_runtime import RSBUILD_FRAMEWORKS, VITE_FRAMEWORKS
from mattstack.utils.console import print_info

REACT_TOOL_VERSIONS = {"oxlint": "1.87.0", "oxfmt": "0.72.0", "react-doctor": "0.9.14"}
REACT_SCRIPTS = {
    "lint": "oxlint .",
    "lint:strict": "oxlint . --deny-warnings",
    "lint:fix": "oxlint . --fix",
    "format": "oxfmt --write .",
    "format:check": "oxfmt --check .",
    "doctor": "react-doctor . --yes --no-telemetry --no-supply-chain --blocking error",
}


def configure_frontend_tooling(config: ProjectConfig) -> None:
    """Normalize React quality scripts without modifying application or design files."""
    if config.frontend_framework not in (*VITE_FRAMEWORKS, *RSBUILD_FRAMEWORKS):
        return
    manifest = config.frontend_dir / "package.json"
    if not manifest.is_file():
        return
    package = json.loads(manifest.read_text())
    scripts = package.setdefault("scripts", {})
    for section in ("dependencies", "devDependencies"):
        dependencies = package.get(section, {})
        for name in list(dependencies):
            if (
                name in REACT_TOOL_VERSIONS
                or name in ("prettier", "typescript-eslint", "@eslint/js", "@eslint/eslintrc")
                or name.startswith(
                    ("eslint", "@eslint/", "@typescript-eslint/", "prettier-plugin-")
                )
            ):
                del dependencies[name]
    package.setdefault("devDependencies", {}).update(REACT_TOOL_VERSIONS)
    # Migrate shell segments rather than replacing a whole gauntlet: build,
    # typecheck, tests and Doctor gates must survive the tool cutover.
    for name, command in list(scripts.items()):
        if not isinstance(command, str):
            continue
        command = command.replace("bun run prettier --check", "bun run format:check")
        command = command.replace("bun run prettier", "bun run format")
        command = command.replace("bun run eslint", "bun run lint")
        command = re.sub(
            r"(?:bunx |npx )?prettier\b[^&;|]*",
            lambda match: "oxfmt --check . " if "--check" in match[0] else "oxfmt --write . ",
            command,
        )
        command = re.sub(
            r"(?:bunx |npx )?eslint\b[^&;|]*",
            lambda match: "oxlint . --fix " if "--fix" in match[0] else "oxlint . ",
            command,
        )
        scripts[name] = command.rstrip()
    scripts.pop("prettier", None)
    scripts.pop("eslint", None)
    scripts.update(REACT_SCRIPTS)
    manifest.write_text(json.dumps(package, indent=2) + "\n")
    _remove_legacy_configs(config.frontend_dir)
    old_doctor_config = config.frontend_dir / "react-doctor.config.json"
    doctor_config = config.frontend_dir / "doctor.config.json"
    if old_doctor_config.is_file():
        if not doctor_config.exists():
            old_doctor_config.rename(doctor_config)
        else:
            old_doctor_config.unlink()
    lint_config = config.frontend_dir / ".oxlintrc.json"
    if not lint_config.exists():
        lint_config.write_text(
            json.dumps(
                {
                    "$schema": "./node_modules/oxlint/configuration_schema.json",
                    "plugins": ["react", "typescript", "jsx-a11y"],
                    "categories": {"correctness": "off"},
                    "rules": {
                        "react/rules-of-hooks": "error",
                        "react/exhaustive-deps": "warn",
                        "no-unused-vars": "warn",
                        "prefer-const": "warn",
                        "jsx-a11y/alt-text": "warn",
                        "jsx-a11y/anchor-has-content": "warn",
                        "jsx-a11y/aria-props": "warn",
                        "jsx-a11y/aria-proptypes": "warn",
                        "jsx-a11y/aria-unsupported-elements": "warn",
                        "jsx-a11y/role-has-required-aria-props": "warn",
                    },
                    "ignorePatterns": [
                        "node_modules/**",
                        "dist/**",
                        "build/**",
                        "coverage/**",
                        "**/routeTree.gen.ts",
                    ],
                },
                indent=2,
            )
            + "\n"
        )
    format_config = config.frontend_dir / ".oxfmtrc.json"
    if not format_config.exists():
        format_config.write_text(
            json.dumps(
                {
                    "$schema": "./node_modules/oxfmt/configuration_schema.json",
                    "ignorePatterns": [
                        "node_modules/**",
                        "dist/**",
                        "build/**",
                        "coverage/**",
                        "**/routeTree.gen.ts",
                    ],
                },
                indent=2,
            )
            + "\n"
        )
    print_info(
        "Configured Oxlint, Oxfmt and local React Doctor; "
        "run make setup to refresh the dependency lock"
    )


def _remove_legacy_configs(directory: Path) -> None:
    for pattern in (
        "eslint.config.*",
        ".eslintrc*",
        ".eslintignore",
        ".prettierrc*",
        "prettier.config.*",
        ".prettierignore",
    ):
        for path in directory.glob(pattern):
            if path.is_file():
                path.unlink()
