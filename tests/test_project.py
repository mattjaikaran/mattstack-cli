"""Tests for project root, env, detection, and persisted stack metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from mattstack.config import BackendFramework, FrontendFramework, ProjectConfig, ProjectType
from mattstack.config_file import load_config
from mattstack.project import (
    EnvFileError,
    find_project_root,
    parse_env_file,
    project_environment,
    resolve_project,
    save_project_config,
)


def _django_backend(backend: Path, deps: str = "django-ninja>=1.0") -> None:
    backend.mkdir(parents=True, exist_ok=True)
    (backend / "manage.py").write_text(
        'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")\n'
    )
    (backend / "pyproject.toml").write_text(f'dependencies = ["{deps}"]\n')


def _frontend(frontend: Path, deps: dict[str, str], scripts: dict[str, str] | None = None) -> None:
    frontend.mkdir(parents=True, exist_ok=True)
    pkg = {"dependencies": deps, "scripts": scripts or {}}
    (frontend / "package.json").write_text(json.dumps(pkg))


class TestParseEnvFile:
    def test_parses_dotenv_syntax_without_interpolation(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text(
            "# comment\n"
            "\n"
            "export A=1\n"
            "B = two \n"
            'C="quoted # not comment"\n'
            "D='single'\n"
            "E=plain # trailing comment\n"
            "F=\n"
            "G=${A}\n"
            "H=$(touch pwned)\n"
            "not a line\n"
        )
        assert parse_env_file(env) == {
            "A": "1",
            "B": "two",
            "C": "quoted # not comment",
            "D": "single",
            "E": "plain",
            "F": "",
            "G": "${A}",
            "H": "$(touch pwned)",
        }
        assert not (tmp_path / "pwned").exists()

    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert parse_env_file(tmp_path / ".env") == {}


class TestProjectEnvironment:
    def test_shell_env_wins_over_root_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".env").write_text("DB_NAME=foo\nDB_HOST=localhost\n")
        monkeypatch.setenv("DB_NAME", "bar")
        monkeypatch.delenv("DB_HOST", raising=False)
        env = project_environment(tmp_path)
        assert env["DB_NAME"] == "bar"
        assert env["DB_HOST"] == "localhost"

    def test_expands_earlier_keys_and_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key in ("PW", "PORT", "UNSET", "EMPTY"):
            monkeypatch.delenv(key, raising=False)
        (tmp_path / ".env").write_text(
            "PW=secret\nEMPTY=\nPORT=${UNSET:-5433}\n"
            'URL="pg://u:${PW}@h:${PORT}/${EMPTY:-db}"\n'
            "LIT='${PW}'\nCOST=$5\n"
        )
        env = project_environment(tmp_path)
        assert env["URL"] == "pg://u:secret@h:5433/db"
        assert env["LIT"] == "${PW}"
        assert env["COST"] == "$5"

    def test_exported_value_wins_inside_references(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PW", "from-shell")
        (tmp_path / ".env").write_text("PW=from-file\nDB_PASSWORD=${PW}\n")
        assert project_environment(tmp_path)["DB_PASSWORD"] == "from-shell"

    @pytest.mark.parametrize(
        "content",
        [
            "A=${LATER}\nLATER=1\n",  # forward reference
            "A=${A}\n",  # self reference
            "A=${MISSING_VAR_X}\n",  # undefined
            "A=${B\n",  # unterminated
            "A=${B-x}\n",  # unsupported operator
            "A=$(echo hi)${B:?boom}\n",  # unsupported operator
        ],
    )
    def test_unresolvable_reference_raises_without_values(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str
    ) -> None:
        for key in ("A", "B", "LATER", "MISSING_VAR_X"):
            monkeypatch.delenv(key, raising=False)
        (tmp_path / ".env").write_text("SECRET=hunter2\n" + content)
        with pytest.raises(EnvFileError) as exc_info:
            project_environment(tmp_path)
        assert "A" in str(exc_info.value)
        assert "hunter2" not in str(exc_info.value)


class TestFindProjectRoot:
    def test_nested_cwd_resolves_monorepo_root(self, tmp_path: Path) -> None:
        _django_backend(tmp_path / "backend")
        _frontend(tmp_path / "frontend", {"vite": "^6"})
        nested = tmp_path / "frontend" / "src" / "components"
        nested.mkdir(parents=True)
        assert find_project_root(nested) == tmp_path
        assert find_project_root(tmp_path / "backend") == tmp_path

    def test_root_only_django_project(self, tmp_path: Path) -> None:
        _django_backend(tmp_path)
        (tmp_path / "api").mkdir()
        assert find_project_root(tmp_path / "api") == tmp_path

    def test_unmarked_path_is_kept(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        empty = tmp_path / "empty"
        empty.mkdir()
        assert find_project_root(empty) == empty


class TestResolveProject:
    def test_root_only_django_project(self, tmp_path: Path) -> None:
        _django_backend(tmp_path)
        project = resolve_project(tmp_path)
        assert project.backend_dir == tmp_path
        assert project.backend_framework == BackendFramework.DJANGO_NINJA
        assert project.frontend_framework is None
        assert project.config.project_type == ProjectType.BACKEND_ONLY
        assert project.settings_module == "api.settings"

    def test_root_only_frontend_project(self, tmp_path: Path) -> None:
        _frontend(tmp_path, {"@rsbuild/core": "^1", "recharts": "^2"})
        project = resolve_project(tmp_path)
        assert project.frontend_dir == tmp_path
        assert project.frontend_framework == FrontendFramework.REACT_RSBUILD_KIBO
        assert project.backend_framework is None
        assert project.config.project_type == ProjectType.FRONTEND_ONLY

    def test_unknown_backend_framework_is_none(self, tmp_path: Path) -> None:
        _django_backend(tmp_path / "backend", deps="django>=5")
        assert resolve_project(tmp_path).backend_framework is None

    def test_api_prefix_from_django_url_mount(self, tmp_path: Path) -> None:
        _django_backend(tmp_path / "backend")
        (tmp_path / "backend" / "api").mkdir()
        (tmp_path / "backend" / "api" / "urls.py").write_text(
            'urlpatterns = [path("admin/", admin.site.urls), path("api/", api.urls)]\n'
        )
        assert resolve_project(tmp_path).api_prefix == "/api"

    def test_env_ports_override_persisted_metadata(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("API_PORT", raising=False)
        monkeypatch.delenv("FRONTEND_PORT", raising=False)
        _django_backend(tmp_path / "backend")
        (tmp_path / "mattstack.yml").write_text(
            "project:\n  ports:\n    api: 8100\n    frontend: 3100\n"
        )
        (tmp_path / ".env").write_text("API_PORT=8010\n")
        project = resolve_project(tmp_path)
        assert project.api_port == 8010
        assert project.frontend_port == 3100

    def test_repr_hides_env_secrets(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("DB_PASSWORD=hunter2\n")
        assert "hunter2" not in repr(resolve_project(tmp_path))


class TestSaveProjectConfig:
    def _config(self, root: Path) -> ProjectConfig:
        return ProjectConfig(
            name="shop",
            path=root,
            backend_framework=BackendFramework.FASTAPI,
            frontend_framework=FrontendFramework.REACT_RSBUILD,
            use_celery=False,
            use_redis=False,
        )

    def test_round_trip_keeps_control_plane_and_comments(self, tmp_path: Path) -> None:
        config_file = tmp_path / "mattstack.yml"
        config_file.write_text("# keep me\nstrict: false\nboard:\n  backend: axis\n")
        _django_backend(tmp_path / "backend", deps="django>=5")  # undetectable on disk
        _frontend(tmp_path / "frontend", {"left-pad": "1"})

        save_project_config(self._config(tmp_path))
        save_project_config(self._config(tmp_path))  # idempotent rewrite

        text = config_file.read_text()
        assert text.startswith("# keep me\nstrict: false\nboard:\n  backend: axis\n")
        assert text.count("project:") == 1
        control = load_config(config_file)
        assert control.strict is False
        assert control.board.backend == "axis"

        project = resolve_project(tmp_path / "frontend")
        assert project.root == tmp_path
        assert project.backend_framework == BackendFramework.FASTAPI
        assert project.frontend_framework == FrontendFramework.REACT_RSBUILD
        assert project.config.name == "shop"
        assert project.config.use_celery is False
        assert project.config.use_redis is False

    def test_keeps_user_tuned_values(self, tmp_path: Path) -> None:
        config_file = tmp_path / "mattstack.yml"
        config_file.write_text("project:\n  execution_mode: container\n  ports:\n    api: 9000\n")
        save_project_config(self._config(tmp_path))
        project = yaml.safe_load(config_file.read_text())["project"]
        assert project["execution_mode"] == "container"
        assert project["ports"]["api"] == 9000
        assert project["ports"]["frontend"] == 3000

    def test_refuses_to_overwrite_invalid_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "mattstack.yml"
        config_file.write_text("strict: [unclosed\n")
        with pytest.raises(ValueError):
            save_project_config(self._config(tmp_path))
        assert config_file.read_text() == "strict: [unclosed\n"
