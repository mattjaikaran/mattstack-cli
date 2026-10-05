"""Generated frontend tooling keeps the starter design and framework boundaries."""

from __future__ import annotations

import json
from pathlib import Path

from mattstack.config import FrontendFramework, ProjectConfig, ProjectType
from mattstack.post_processors.frontend_tooling import configure_frontend_tooling


def test_react_migration_preserves_user_design_and_removes_obsolete_tooling(
    tmp_path: Path,
) -> None:
    config = ProjectConfig(
        name="design-app",
        path=tmp_path,
        project_type=ProjectType.FRONTEND_ONLY,
        frontend_framework=FrontendFramework.REACT_VITE,
    )
    config.frontend_dir.mkdir()
    manifest = config.frontend_dir / "package.json"
    manifest.write_text(
        json.dumps(
            {
                "scripts": {
                    "lint": "eslint .",
                    "format:check": "prettier --check .",
                    "build": "vite build",
                    "gauntlet": "prettier --check . && eslint . && bun run build",
                },
                "devDependencies": {"eslint": "9", "prettier": "3", "react": "19"},
            }
        )
    )
    (config.frontend_dir / "eslint.config.js").write_text("export default []")
    (config.frontend_dir / ".prettierrc").write_text("{}")
    (config.frontend_dir / "react-doctor.config.json").write_text('{"ignore": {}}')
    design = config.frontend_dir / "DESIGN.md"
    design.write_text("Edit tokens in src/index.css")
    theme = config.frontend_dir / "src/index.css"
    theme.parent.mkdir()
    theme.write_text(":root { --primary: blue; }")
    configure_frontend_tooling(config)
    package = json.loads(manifest.read_text())
    assert package["scripts"]["build"] == "vite build"
    assert (config.frontend_dir / "doctor.config.json").read_text() == '{"ignore": {}}'
    assert not (config.frontend_dir / "react-doctor.config.json").exists()
    assert package["devDependencies"]["react"] == "19"
    assert "eslint" not in package["devDependencies"]
    assert "prettier" not in package["devDependencies"]
    assert not (config.frontend_dir / "eslint.config.js").exists()
    assert not (config.frontend_dir / ".prettierrc").exists()
    assert design.read_text() == "Edit tokens in src/index.css"
    assert theme.read_text() == ":root { --primary: blue; }"


def test_nextjs_keeps_its_toolchain(tmp_path: Path) -> None:
    config = ProjectConfig(
        name="next-app",
        path=tmp_path,
        project_type=ProjectType.FRONTEND_ONLY,
        frontend_framework=FrontendFramework.NEXTJS,
    )
    config.frontend_dir.mkdir()
    manifest = config.frontend_dir / "package.json"
    original = '{"scripts":{"lint":"next lint"},"devDependencies":{"eslint":"9"}}'
    manifest.write_text(original)
    configure_frontend_tooling(config)
    assert manifest.read_text() == original
