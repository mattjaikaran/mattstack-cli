"""Tests for package manager detection and command building."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mattstack.utils.package_manager import (
    DEFAULT_PM,
    PackageManager,
    build_add_cmd,
    build_exec_cmd,
    build_install_cmd,
    build_remove_cmd,
    build_run_cmd,
    build_update_cmd,
    detect_package_manager,
    parse_audit,
    parse_outdated,
    resolve_package_manager,
    resolve_package_manager_source,
)


class TestDetectPackageManager:
    def test_detect_bun_lockb(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "bun.lockb").write_text("")
        assert detect_package_manager(tmp_path) == PackageManager.BUN

    def test_detect_bun_lock(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "bun.lock").write_text("")
        assert detect_package_manager(tmp_path) == PackageManager.BUN

    def test_detect_npm(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "package-lock.json").write_text("{}")
        assert detect_package_manager(tmp_path) == PackageManager.NPM

    def test_detect_yarn(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "yarn.lock").write_text("")
        assert detect_package_manager(tmp_path) == PackageManager.YARN

    def test_detect_pnpm(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "pnpm-lock.yaml").write_text("")
        assert detect_package_manager(tmp_path) == PackageManager.PNPM

    def test_default_to_bun(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}")
        assert detect_package_manager(tmp_path) == DEFAULT_PM

    def test_detect_from_frontend_subdir(self, tmp_path: Path) -> None:
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text("{}")
        (frontend / "yarn.lock").write_text("")
        assert detect_package_manager(tmp_path) == PackageManager.YARN

    def test_frontend_subdir_takes_priority(self, tmp_path: Path) -> None:
        (tmp_path / "package-lock.json").write_text("{}")
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text("{}")
        (frontend / "bun.lockb").write_text("")
        assert detect_package_manager(tmp_path) == PackageManager.BUN


class TestResolvePackageManager:
    def test_explicit_override(self, tmp_path: Path) -> None:
        assert resolve_package_manager(tmp_path, override="npm") == PackageManager.NPM

    def test_invalid_override_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="invalid"):
            resolve_package_manager(tmp_path, override="invalid")

    @patch("mattstack.user_config.load_user_config")
    def test_user_default_applies_without_lockfile(self, mock_config, tmp_path: Path) -> None:
        mock_config.return_value = {"defaults": {"package_manager": "yarn"}}
        resolution = resolve_package_manager_source(tmp_path)
        assert resolution.manager == PackageManager.YARN
        assert "user default" in resolution.source

    @patch("mattstack.user_config.load_user_config")
    def test_project_lockfile_beats_user_default(self, mock_config, tmp_path: Path) -> None:
        mock_config.return_value = {"defaults": {"package_manager": "yarn"}}
        (tmp_path / "pnpm-lock.yaml").write_text("")
        resolution = resolve_package_manager_source(tmp_path)
        assert resolution.manager == PackageManager.PNPM
        assert str(tmp_path / "pnpm-lock.yaml") in resolution.source

    @patch("mattstack.user_config.load_user_config")
    def test_explicit_override_beats_lockfile(self, mock_config, tmp_path: Path) -> None:
        mock_config.return_value = {}
        (tmp_path / "pnpm-lock.yaml").write_text("")
        assert resolve_package_manager(tmp_path, override="npm") == PackageManager.NPM

    @pytest.mark.parametrize("value", ["invalid", False, ["bun"]])
    def test_invalid_user_default_requires_correction(self, tmp_path: Path, value: object) -> None:
        with patch("mattstack.user_config.load_user_config") as config:
            config.return_value = {"defaults": {"package_manager": value}}
            with pytest.raises(ValueError, match="defaults.package_manager"):
                resolve_package_manager(tmp_path)
            assert resolve_package_manager(tmp_path, override="bun") == PackageManager.BUN
            (tmp_path / "bun.lock").write_text("")
            assert resolve_package_manager(tmp_path) == PackageManager.BUN

    def test_component_dir_uses_workspace_root_lockfile(self, tmp_path: Path) -> None:
        frontend = tmp_path / "frontend"
        frontend.mkdir()
        (tmp_path / "pnpm-lock.yaml").write_text("")
        assert resolve_package_manager(frontend) == PackageManager.PNPM

    def test_lockfile_detection_over_default(self, tmp_path: Path) -> None:
        (tmp_path / "pnpm-lock.yaml").write_text("")
        assert resolve_package_manager(tmp_path) == PackageManager.PNPM


class TestBuildAddCmd:
    def test_bun_add(self) -> None:
        cmd = build_add_cmd(PackageManager.BUN, ["react", "react-dom"])
        assert cmd.full == ["bun", "add", "react", "react-dom"]

    def test_bun_add_dev(self) -> None:
        cmd = build_add_cmd(PackageManager.BUN, ["vitest"], dev=True)
        assert cmd.full == ["bun", "add", "-d", "vitest"]

    def test_npm_install(self) -> None:
        cmd = build_add_cmd(PackageManager.NPM, ["axios"])
        assert cmd.full == ["npm", "install", "axios"]

    def test_npm_install_dev(self) -> None:
        cmd = build_add_cmd(PackageManager.NPM, ["jest"], dev=True)
        assert "--save-dev" in cmd.full

    def test_yarn_add(self) -> None:
        cmd = build_add_cmd(PackageManager.YARN, ["lodash"])
        assert cmd.full == ["yarn", "add", "lodash"]

    def test_yarn_add_dev(self) -> None:
        cmd = build_add_cmd(PackageManager.YARN, ["eslint"], dev=True)
        assert "--dev" in cmd.full

    def test_pnpm_add(self) -> None:
        cmd = build_add_cmd(PackageManager.PNPM, ["zod"])
        assert cmd.full == ["pnpm", "add", "zod"]

    def test_pnpm_add_dev(self) -> None:
        cmd = build_add_cmd(PackageManager.PNPM, ["typescript"], dev=True)
        assert "-D" in cmd.full


class TestBuildRemoveCmd:
    def test_bun_remove(self) -> None:
        cmd = build_remove_cmd(PackageManager.BUN, ["axios"])
        assert cmd.full == ["bun", "remove", "axios"]

    def test_npm_uninstall(self) -> None:
        cmd = build_remove_cmd(PackageManager.NPM, ["axios"])
        assert cmd.full == ["npm", "uninstall", "axios"]

    def test_yarn_remove(self) -> None:
        cmd = build_remove_cmd(PackageManager.YARN, ["axios"])
        assert cmd.full == ["yarn", "remove", "axios"]


class TestBuildInstallCmd:
    def test_bun_install(self) -> None:
        cmd = build_install_cmd(PackageManager.BUN)
        assert cmd.full == ["bun", "install"]

    def test_npm_install(self) -> None:
        cmd = build_install_cmd(PackageManager.NPM)
        assert cmd.full == ["npm", "install"]


class TestBuildRunCmd:
    def test_run_script(self) -> None:
        cmd = build_run_cmd(PackageManager.BUN, "dev")
        assert cmd.full == ["bun", "run", "dev"]

    def test_run_script_with_args(self) -> None:
        cmd = build_run_cmd(PackageManager.NPM, "test", ["--watch"])
        assert cmd.full == ["npm", "run", "test", "--watch"]


class TestBuildExecCmd:
    def test_bunx(self) -> None:
        cmd = build_exec_cmd(PackageManager.BUN, "create-next-app")
        assert cmd.full == ["bunx", "create-next-app"]

    def test_npx(self) -> None:
        cmd = build_exec_cmd(PackageManager.NPM, "create-next-app")
        assert cmd.full == ["npx", "create-next-app"]

    def test_yarn_dlx(self) -> None:
        cmd = build_exec_cmd(PackageManager.YARN, "create-next-app")
        assert cmd.full == ["yarn", "dlx", "create-next-app"]

    def test_pnpm_dlx(self) -> None:
        cmd = build_exec_cmd(PackageManager.PNPM, "create-next-app")
        assert cmd.full == ["pnpm", "dlx", "create-next-app"]

    def test_exec_with_extra_args(self) -> None:
        cmd = build_exec_cmd(PackageManager.BUN, "tsc", ["--noEmit"])
        assert cmd.full == ["bunx", "tsc", "--noEmit"]


class TestPMCommandStr:
    def test_str_representation(self) -> None:
        cmd = build_add_cmd(PackageManager.BUN, ["react"])
        assert str(cmd) == "bun add react"


@pytest.mark.parametrize(
    ("pm", "flag"),
    [
        (PackageManager.BUN, "--exact"),
        (PackageManager.NPM, "--save-exact"),
        (PackageManager.YARN, "--exact"),
        (PackageManager.PNPM, "--save-exact"),
    ],
)
def test_exact_add_pins_for_every_manager(pm: PackageManager, flag: str) -> None:
    cmd = build_add_cmd(pm, ["oxlint@1.2.3"], dev=True, exact=True)
    assert flag in cmd.full
    assert "oxlint@1.2.3" in cmd.full
    assert flag not in build_add_cmd(pm, ["oxlint"]).full


def test_npm_cannot_update_across_majors() -> None:
    assert build_update_cmd(PackageManager.NPM, latest=True) is None
    assert build_update_cmd(PackageManager.BUN, latest=True).full == ["bun", "update", "--latest"]


class TestParseOutdated:
    def test_npm_json(self) -> None:
        out = '{"react": {"current": "18.2.0", "wanted": "18.3.1", "latest": "19.0.0"}}'
        assert parse_outdated(PackageManager.NPM, out) == [("react", "18.2.0", "19.0.0")]

    def test_bun_box_table(self) -> None:
        out = (
            "bun outdated v1.2.0 (abc)\n"
            "| Package | Current | Update | Latest |\n"
            "|---------|---------|--------|--------|\n"
            "| react   | 18.2.0  | 18.3.1 | 19.0.0 |\n"
        )
        assert parse_outdated(PackageManager.BUN, out) == [("react", "18.2.0", "19.0.0")]

    def test_yarn_ndjson_table(self) -> None:
        out = (
            '{"type":"info","data":"Color legend"}\n'
            '{"type":"table","data":{"head":["Package","Current","Wanted","Latest"],'
            '"body":[["react","18.2.0","18.3.1","19.0.0","dependencies",""]]}}\n'
        )
        assert parse_outdated(PackageManager.YARN, out) == [("react", "18.2.0", "19.0.0")]


class TestParseAudit:
    def test_npm_vulnerabilities(self) -> None:
        out = '{"vulnerabilities": {"lodash": {"severity": "high", "via": [{"title": "Proto"}]}}}'
        assert parse_audit(PackageManager.NPM, out) == [("lodash", "high", "Proto")]

    def test_pnpm_advisories(self) -> None:
        out = '{"advisories": {"1": {"module_name": "lodash", "severity": "high", "title": "P"}}}'
        assert parse_audit(PackageManager.PNPM, out) == [("lodash", "high", "P")]

    def test_yarn_ndjson(self) -> None:
        out = (
            '{"type":"auditAdvisory","data":{"advisory":'
            '{"module_name":"lodash","severity":"low","title":"P"}}}\n'
            '{"type":"auditSummary","data":{}}\n'
        )
        assert parse_audit(PackageManager.YARN, out) == [("lodash", "low", "P")]
