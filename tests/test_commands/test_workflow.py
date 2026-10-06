"""Tests for commands/workflow.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer
import yaml

from mattstack.commands.workflow import (
    _generate_github_actions,
    _generate_gitlab_ci,
    run_generate_workflow,
)
from mattstack.config import BackendFramework, FrontendFramework, ProjectConfig, ProjectType


def _config(
    tmp_path: Path,
    project_type: ProjectType = ProjectType.FULLSTACK,
    backend: BackendFramework = BackendFramework.DJANGO_NINJA,
    frontend: FrontendFramework = FrontendFramework.REACT_VITE,
) -> ProjectConfig:
    return ProjectConfig(
        name="app",
        path=tmp_path,
        project_type=project_type,
        backend_framework=backend,
        frontend_framework=frontend,
        init_git=False,
    )


# ---------------------------------------------------------------------------
# _generate_github_actions
# ---------------------------------------------------------------------------


class TestGenerateGithubActions:
    def test_fullstack_includes_all_jobs(self, tmp_path: Path) -> None:
        content = _generate_github_actions(_config(tmp_path), with_gauntlet=False)
        for job in ("backend-lint", "backend-test", "frontend-lint", "frontend-test"):
            assert f"{job}:" in content
        assert "frontend-typecheck:" in content

    def test_backend_only_excludes_frontend_jobs(self, tmp_path: Path) -> None:
        config = _config(tmp_path, ProjectType.BACKEND_ONLY)
        content = _generate_github_actions(config, with_gauntlet=False)
        assert "backend-test:" in content
        assert "frontend-lint:" not in content

    def test_frontend_only_excludes_backend_jobs(self, tmp_path: Path) -> None:
        config = _config(tmp_path, ProjectType.FRONTEND_ONLY)
        content = _generate_github_actions(config, with_gauntlet=False)
        assert "frontend-lint:" in content
        assert "backend-lint:" not in content
        assert "astral-sh/setup-uv" not in content

    def test_python_backend_uses_uv_postgres_and_redis(self, tmp_path: Path) -> None:
        config = _config(tmp_path, ProjectType.BACKEND_ONLY)
        content = _generate_github_actions(config, with_gauntlet=False)
        assert "uv run pytest" in content
        assert "POSTGRES_DB:" in content
        assert "REDIS_URL:" in content

    def test_fastapi_backend_installs_dev_extra_and_async_driver(self, tmp_path: Path) -> None:
        config = _config(tmp_path, ProjectType.BACKEND_ONLY, BackendFramework.FASTAPI)
        content = _generate_github_actions(config, with_gauntlet=False)
        assert "uv sync --frozen --python 3.13 --extra dev" in content
        assert "postgresql+asyncpg://" in content

    def test_nestjs_backend_runs_bun_scripts_not_python(self, tmp_path: Path) -> None:
        config = _config(tmp_path, ProjectType.BACKEND_ONLY, BackendFramework.NESTJS)
        jobs = yaml.safe_load(_generate_github_actions(config, with_gauntlet=False))["jobs"]
        steps = [step.get("run", "") for step in jobs["backend-test"]["steps"]]
        assert "bun run test" in steps
        assert jobs["backend-test"]["defaults"]["run"]["working-directory"] == "backend"
        assert "uv" not in json.dumps(jobs)

    def test_output_is_valid_yaml(self, tmp_path: Path) -> None:
        content = _generate_github_actions(_config(tmp_path), with_gauntlet=True)
        document = yaml.safe_load(content)
        assert document["concurrency"]["cancel-in-progress"] is True
        assert "gauntlet" in document["jobs"]


class TestJavaScriptPackageManager:
    def _frontend(self, tmp_path: Path, lockfile: str, where: str = "frontend") -> ProjectConfig:
        (tmp_path / "frontend").mkdir()
        (tmp_path / where / lockfile).write_text("{}")
        return _config(tmp_path, ProjectType.FRONTEND_ONLY, frontend=FrontendFramework.REACT_VITE)

    def test_no_lockfile_keeps_bun(self, tmp_path: Path) -> None:
        config = _config(tmp_path, ProjectType.FRONTEND_ONLY)
        content = _generate_github_actions(config, with_gauntlet=False)
        assert "oven-sh/setup-bun" in content
        assert "bun install --frozen-lockfile" in content

    def test_npm_lockfile_uses_npm_everywhere(self, tmp_path: Path) -> None:
        config = self._frontend(tmp_path, "package-lock.json")
        jobs = yaml.safe_load(_generate_github_actions(config, with_gauntlet=False))["jobs"]
        runs = [step.get("run") for job in jobs.values() for step in job["steps"]]
        assert "npm ci" in runs
        assert "npm run lint" in runs
        assert "npx vitest run" in runs
        assert not any("bun" in json.dumps(step) for job in jobs.values() for step in job["steps"])

    def test_workspace_pnpm_lockfile_installs_at_root(self, tmp_path: Path) -> None:
        config = self._frontend(tmp_path, "pnpm-lock.yaml", where=".")
        github = _generate_github_actions(config, with_gauntlet=False)
        assert "corepack enable" in github
        assert "(cd .. && pnpm install --frozen-lockfile)" in github
        gitlab = yaml.safe_load(_generate_gitlab_ci(config, with_gauntlet=False))
        assert gitlab["frontend-lint"]["image"] == "node:22"
        assert gitlab["frontend-lint"]["script"] == ["pnpm run lint"]


# ---------------------------------------------------------------------------
# _generate_gitlab_ci
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("backend", "expects_db_parts"),
    [
        (BackendFramework.DJANGO_NINJA, True),
        (BackendFramework.DJANGO_MATT, True),
        (BackendFramework.FASTAPI, False),
    ],
)
def test_backend_test_env_matches_settings_variables(
    tmp_path: Path, backend: BackendFramework, expects_db_parts: bool
) -> None:
    """Django settings read DB_*; without them tests hit the default database name."""
    config = _config(tmp_path, ProjectType.BACKEND_ONLY, backend)
    github = yaml.safe_load(_generate_github_actions(config, with_gauntlet=False))
    gitlab = yaml.safe_load(_generate_gitlab_ci(config, with_gauntlet=False))
    gh_env = github["jobs"]["backend-test"]["env"]
    gl_env = gitlab["backend-test"]["variables"]
    if expects_db_parts:
        expected = {"DB_NAME": "test_db", "DB_USER": "postgres", "DB_PASSWORD": "postgres"}
        assert expected.items() <= gh_env.items()
        assert expected.items() <= gl_env.items()
        assert (gh_env["DB_HOST"], gl_env["DB_HOST"]) == ("localhost", "postgres")
        assert gh_env["DB_PORT"] == gl_env["DB_PORT"] == "5432"
    else:
        assert "DB_NAME" not in gh_env
        assert gl_env["DATABASE_URL"].startswith("postgresql+asyncpg://postgres:postgres@postgres")


class TestGenerateGitlabCi:
    def test_fullstack_has_all_jobs(self, tmp_path: Path) -> None:
        document = yaml.safe_load(_generate_gitlab_ci(_config(tmp_path), with_gauntlet=False))
        for job in ("backend-lint", "backend-test", "frontend-lint", "frontend-typecheck"):
            assert job in document

    def test_nestjs_backend_jobs_run_in_backend_with_bun(self, tmp_path: Path) -> None:
        config = _config(tmp_path, ProjectType.BACKEND_ONLY, BackendFramework.NESTJS)
        document = yaml.safe_load(_generate_gitlab_ci(config, with_gauntlet=False))
        assert document["backend-test"]["before_script"] == [
            "cd backend && bun install --frozen-lockfile"
        ]
        assert document["backend-test"]["script"] == ["bun run test"]


# ---------------------------------------------------------------------------
# run_generate_workflow
# ---------------------------------------------------------------------------


def _make_fullstack(tmp_path: Path, pyproject_deps: str = '["django-ninja"]') -> Path:
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "pyproject.toml").write_text(
        f'[project]\nname = "api"\ndependencies = {pyproject_deps}\n'
    )
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text(
        json.dumps({"scripts": {"type-check": "tsc"}, "devDependencies": {"vite": "6"}})
    )
    return tmp_path


class TestRunGenerateWorkflow:
    def test_invalid_path_exits_1(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            run_generate_workflow(tmp_path / "does_not_exist", ci="github")
        assert exc_info.value.exit_code == 1

    def test_unknown_project_type_exits_1(self, tmp_path: Path) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            run_generate_workflow(tmp_path, ci="github")
        assert exc_info.value.exit_code == 1

    def test_unknown_backend_framework_exits_1_without_writing(self, tmp_path: Path) -> None:
        _make_fullstack(tmp_path, pyproject_deps="[]")
        with pytest.raises(typer.Exit) as exc_info:
            run_generate_workflow(tmp_path, ci="github")
        assert exc_info.value.exit_code == 1
        assert not (tmp_path / ".github").exists()

    @pytest.mark.parametrize("ci", [None, "circleci", "github-actions"])
    def test_hosted_ci_is_opt_in(self, tmp_path: Path, ci: str | None) -> None:
        _make_fullstack(tmp_path)
        with pytest.raises(typer.Exit) as exc_info:
            run_generate_workflow(tmp_path, ci=ci)
        assert exc_info.value.exit_code == 2
        assert not (tmp_path / ".github").exists()
        assert not (tmp_path / ".gitlab-ci.yml").exists()

    def test_dry_run_prints_yaml_verbatim_without_writing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _make_fullstack(tmp_path)
        run_generate_workflow(tmp_path, ci="github", dry_run=True)
        assert not (tmp_path / ".github" / "workflows" / "ci.yml").exists()
        assert "branches: [main]" in capsys.readouterr().out

    def test_existing_workflow_is_kept_without_force(self, tmp_path: Path) -> None:
        _make_fullstack(tmp_path)
        ci_file = tmp_path / ".github" / "workflows" / "ci.yml"
        ci_file.parent.mkdir(parents=True)
        ci_file.write_bytes(b"# mine\n")
        with pytest.raises(typer.Exit) as exc_info:
            run_generate_workflow(tmp_path, ci="github")
        assert exc_info.value.exit_code == 1
        assert ci_file.read_bytes() == b"# mine\n"

    def test_force_replaces_existing_workflow(self, tmp_path: Path) -> None:
        _make_fullstack(tmp_path)
        ci_file = tmp_path / ".gitlab-ci.yml"
        ci_file.write_text("# mine\n")
        run_generate_workflow(tmp_path, ci="gitlab", force=True)
        assert "stages:" in ci_file.read_text()

    def _workdirs(self, root: Path) -> dict[str, str]:
        run_generate_workflow(root, ci="github")
        jobs = yaml.safe_load((root / ".github" / "workflows" / "ci.yml").read_text())["jobs"]
        return {
            name: job["defaults"]["run"]["working-directory"]
            for name, job in jobs.items()
            if "defaults" in job
        }

    def test_root_only_django_runs_in_repository_root(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["django-ninja"]\n')
        (tmp_path / "manage.py").write_text("")
        assert self._workdirs(tmp_path) == {"backend-lint": ".", "backend-test": "."}
        run_generate_workflow(tmp_path, ci="gitlab")
        gitlab = yaml.safe_load((tmp_path / ".gitlab-ci.yml").read_text())
        assert gitlab["backend-test"]["before_script"][-1].startswith("cd . && uv sync")

    def test_root_only_frontend_uses_its_own_lockfile(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"type-check": "tsc"}, "devDependencies": {"vite": "6"}})
        )
        (tmp_path / "package-lock.json").write_text("{}")
        workdirs = self._workdirs(tmp_path)
        assert set(workdirs.values()) == {"."}
        assert "npm ci" in (tmp_path / ".github" / "workflows" / "ci.yml").read_text()

    def test_unusual_metadata_dirs_survive_yaml_and_shell(self, tmp_path: Path) -> None:
        api = tmp_path / "api server: v2"
        api.mkdir()
        (api / "pyproject.toml").write_text('[project]\nname = "api"\n')
        (tmp_path / "mattstack.yml").write_text(
            "project:\n  backend:\n    framework: django-ninja\n    dir: 'api server: v2'\n"
        )
        assert self._workdirs(tmp_path)["backend-test"] == "api server: v2"
        run_generate_workflow(tmp_path, ci="gitlab")
        gitlab = yaml.safe_load((tmp_path / ".gitlab-ci.yml").read_text())
        install = gitlab["backend-test"]["before_script"][-1]
        assert install.startswith("cd 'api server: v2' && uv sync")

    def test_metadata_component_dirs_are_used(self, tmp_path: Path) -> None:
        api = tmp_path / "services" / "api"
        api.mkdir(parents=True)
        (api / "pyproject.toml").write_text('[project]\nname = "api"\n')
        web = tmp_path / "web"
        web.mkdir()
        (web / "package.json").write_text('{"devDependencies": {"vite": "6"}}')
        (web / "yarn.lock").write_text("")
        (tmp_path / "mattstack.yml").write_text(
            "project:\n"
            "  backend:\n    framework: fastapi\n    dir: services/api\n"
            "  frontend:\n    framework: react-vite-starter\n    dir: web\n"
        )
        workdirs = self._workdirs(tmp_path)
        assert workdirs["backend-test"] == "services/api"
        assert workdirs["frontend-lint"] == "web"
        assert (
            "yarn install --frozen-lockfile"
            in (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
        )

    def test_github_actions_uses_detected_backend(self, tmp_path: Path) -> None:
        _make_fullstack(tmp_path, pyproject_deps='["fastapi"]')
        run_generate_workflow(tmp_path, ci="github")
        content = (tmp_path / ".github" / "workflows" / "ci.yml").read_text()
        assert "--extra dev" in content

    def test_gitlab_ci_creates_gitlab_ci_yml(self, tmp_path: Path) -> None:
        _make_fullstack(tmp_path)
        run_generate_workflow(tmp_path, ci="gitlab")
        assert "stages:" in (tmp_path / ".gitlab-ci.yml").read_text()

    def test_nested_path_writes_at_project_root(self, tmp_path: Path) -> None:
        _make_fullstack(tmp_path)
        (tmp_path / "frontend" / "src").mkdir()
        run_generate_workflow(tmp_path / "frontend" / "src", ci="gitlab")
        assert (tmp_path / ".gitlab-ci.yml").exists()
