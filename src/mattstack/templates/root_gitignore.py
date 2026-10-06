"""Root .gitignore template for generated projects."""

from __future__ import annotations

from mattstack.config import ProjectConfig


def generate_gitignore(config: ProjectConfig) -> str:
    """Generate combined .gitignore for the monorepo."""
    sections: list[str] = [_general()]

    if config.has_backend:
        sections.append(_python())

    if config.has_frontend:
        sections.append(_node())

    if config.include_ios:
        sections.append(_swift())

    sections.append(_docker())

    return "\n".join(sections) + "\n"


def _general() -> str:
    return """\
# General
.DS_Store
.env
.env.production
*.log
.vscode/
.idea/
.claude/settings.local.json
*.swp
*.swo"""


def _python() -> str:
    return """
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
.venv/
venv/
.pytest_cache/
.ruff_cache/
.mypy_cache/
.hypothesis/
.coverage
.coverage.*
coverage.xml
htmlcov/
*.egg
db.sqlite3
# Backend gauntlet output (`just gauntlet-quick`, `just gauntlet-ci`)
test_db.sqlite3
gauntlet-report.json"""


def _node() -> str:
    return """
# Node
node_modules/
dist/
.cache/
*.tsbuildinfo"""


def _swift() -> str:
    return """
# Swift/Xcode
*.xcuserstate
xcuserdata/
DerivedData/
.build/
Pods/"""


def _docker() -> str:
    return """
# Docker
docker-compose.override.yml"""
