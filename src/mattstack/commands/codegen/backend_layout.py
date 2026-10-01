"""Inspect a Django backend before generating code into it.

Generation refuses rather than guesses: the API instance, its URL mount, the
target app, and the package layout must all be found in the project, so every
generated import resolves and every controller is registered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from mattstack.parsers.utils import find_files


class GenerateError(Exception):
    """Generation cannot proceed safely; nothing has been written."""


API_INSTANCE_RE = re.compile(
    r"^(\w+)\s*(?::\s*\w+\s*)?=\s*(NinjaExtraAPI|NinjaAPI|DjangoMattAPI|MattAPI)\s*\(",
    re.MULTILINE,
)
APP_LABEL_RE = re.compile(r"""^\s+label\s*=\s*['"](\w+)['"]""", re.MULTILINE)
SKIP_PARTS = frozenset({"tests", "migrations", "node_modules", ".venv", "venv"})
NINJA_EXTRA = "django-ninja"
DJANGO_MATT = "django-matt"


@dataclass(frozen=True)
class BackendLayout:
    backend_dir: Path
    framework: str  # NINJA_EXTRA or DJANGO_MATT
    app_dir: Path
    app_module: str  # dotted import path of the app package
    app_label: str
    controllers_dir: Path
    base_model_module: str | None  # module defining AbstractBaseModel
    api_file: Path
    api_var: str
    mount_prefix: str  # URL prefix of the API, e.g. "/api/"
    has_jwt: bool
    has_unfold: bool
    # Primary key type of generated models ("uuid" | "int" | "str"); set by
    # model_pk.with_model_key once the base model's key is verified.
    pk_key: str = "uuid"

    @property
    def models_dir(self) -> Path:
        return self.app_dir / "models"

    @property
    def schemas_dir(self) -> Path:
        return self.app_dir / "schemas"

    @property
    def admin_package(self) -> bool:
        return (self.app_dir / "admin").is_dir() or not (self.app_dir / "admin.py").exists()

    def module_of(self, path: Path) -> str:
        return ".".join(path.relative_to(self.backend_dir).with_suffix("").parts)


def _dotted(backend_dir: Path, path: Path) -> str:
    return ".".join(path.relative_to(backend_dir).parts)


def _python_files(backend_dir: Path) -> list[Path]:
    return [
        f
        for f in find_files(backend_dir, ["*.py", "*/*.py", "*/*/*.py"])
        if not SKIP_PARTS.intersection(f.relative_to(backend_dir).parts)
    ]


def _manifest_text(backend_dir: Path) -> str:
    texts = []
    for name in ("pyproject.toml", "requirements.txt"):
        path = backend_dir / name
        if path.is_file():
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(texts)


def find_api_instance(backend_dir: Path) -> tuple[Path, str, str]:
    """Return (file, variable, class) for the project's API object."""
    found: list[tuple[Path, str, str]] = []
    for f in _python_files(backend_dir):
        text = f.read_text(encoding="utf-8", errors="replace")
        found.extend((f, m.group(1), m.group(2)) for m in API_INSTANCE_RE.finditer(text))
    if not found:
        raise GenerateError(
            f"No NinjaExtraAPI or DjangoMattAPI instance found under {backend_dir}; "
            "cannot register a generated controller."
        )
    if len(found) > 1:
        listed = ", ".join(f"{f.relative_to(backend_dir)}:{var}" for f, var, _ in found)
        raise GenerateError(f"Several API instances found ({listed}); cannot choose one safely.")
    return found[0]


def find_mount_prefix(backend_dir: Path, api_file: Path, api_var: str) -> str:
    """Return the URL prefix the API is mounted under, from urls.py."""
    module = _dotted(backend_dir, api_file.with_suffix(""))
    pattern = re.compile(r"""path\(\s*['"]([^'"]*)['"]\s*,\s*(?:include\(\s*)?(\w+)\.urls\b""")
    for urls in find_files(backend_dir, ["urls.py", "*/urls.py", "*/*/urls.py"]):
        text = urls.read_text(encoding="utf-8", errors="replace")
        local = urls.resolve() == api_file.resolve()
        imported = re.search(rf"from\s+{re.escape(module)}\s+import\s+.*\b{api_var}\b", text)
        if not (local or imported):
            continue
        for prefix, var in pattern.findall(text):
            if var == api_var:
                return "/" + prefix.strip("/") + "/" if prefix.strip("/") else "/"
    raise GenerateError(f"Could not find where `{api_var}.urls` is mounted in any urls.py.")


APPS_LIST_RE = re.compile(r"\b\w*APPS\s*\+?=\s*[\[(](.*?)[\])]", re.DOTALL)
APP_LITERAL_RE = re.compile(r"""['"]([A-Za-z_][\w.]*)['"]""")


def settings_texts(backend_dir: Path) -> list[str]:
    """Text of every Django settings module, with comments removed."""
    settings = [
        f
        for f in find_files(backend_dir, ["*/settings.py", "*/settings/*.py", "*/*/settings.py"])
        if not SKIP_PARTS.intersection(f.relative_to(backend_dir).parts)
    ]
    return [re.sub(r"#.*", "", f.read_text(encoding="utf-8", errors="replace")) for f in settings]


def installed_apps(backend_dir: Path) -> list[Path]:
    """Return project app packages listed in INSTALLED_APPS (or *_APPS lists)."""
    texts = settings_texts(backend_dir)
    if not any("INSTALLED_APPS" in text for text in texts):
        raise GenerateError(
            "No settings module with INSTALLED_APPS found; cannot find Django apps."
        )
    apps: list[Path] = []
    for text in texts:
        for block in APPS_LIST_RE.findall(text):
            for literal in APP_LITERAL_RE.findall(block):
                module = re.sub(r"\.apps\.\w+$", "", literal)
                app_dir = backend_dir.joinpath(*module.split("."))
                if (app_dir / "__init__.py").is_file() and app_dir not in apps:
                    apps.append(app_dir)
    return sorted(apps)


def _select_app(backend_dir: Path, app: str | None) -> Path:
    """Pick an installed app; Django never migrates models of an uninstalled one."""
    candidates = installed_apps(backend_dir)
    names = ", ".join(_dotted(backend_dir, c) for c in candidates) or "none"
    if app:
        matches = [c for c in candidates if app in (c.name, _dotted(backend_dir, c))]
        if len(matches) == 1:
            return matches[0]
        raise GenerateError(f"Django app '{app}' is not in INSTALLED_APPS. Installed apps: {names}")
    usable = [c for c in candidates if not (c / "models.py").exists()]
    if len(usable) == 1:
        return usable[0]
    core = [c for c in usable if c.name == "core"]
    if len(core) == 1:
        return core[0]
    raise GenerateError(f"Cannot choose a Django app; pass --app. Installed apps: {names}")


def _base_model_module(backend_dir: Path) -> str | None:
    for path in find_files(backend_dir, ["*/models/base.py", "*/*/models/base.py"]):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^(?:class AbstractBaseModel\b|AbstractBaseModel\s*=)", text, re.MULTILINE):
            return _dotted(backend_dir, path.with_suffix(""))
    return None


def _check_packages(app_dir: Path) -> Path:
    for package in ("models", "schemas"):
        if (app_dir / f"{package}.py").exists():
            raise GenerateError(
                f"{app_dir / package}.py is a module; generation needs a {package}/ package. "
                "Convert it or choose another --app."
            )
    for name in ("controllers", "api"):
        if (app_dir / name).is_dir():
            return app_dir / name
    if (app_dir / "controllers.py").exists():
        raise GenerateError(
            f"{app_dir}/controllers.py is a module; expected a controllers/ package."
        )
    return app_dir / "controllers"


def app_label(app_dir: Path) -> str:
    """Django app label: AppConfig.label when set, else the package name."""
    apps_py = app_dir / "apps.py"
    text = apps_py.read_text(encoding="utf-8", errors="replace") if apps_py.is_file() else ""
    label = APP_LABEL_RE.search(text)
    return label.group(1) if label else app_dir.name


def detect_backend_layout(backend_dir: Path, app: str | None) -> BackendLayout:
    """Inspect *backend_dir* and return where and how to generate code."""
    if not backend_dir.is_dir():
        raise GenerateError(f"No backend directory found at {backend_dir}")
    api_file, api_var, api_class = find_api_instance(backend_dir)
    if api_class == "NinjaAPI":
        raise GenerateError(
            f"{api_file.relative_to(backend_dir)} uses plain NinjaAPI; generated controllers "
            "need NinjaExtraAPI (django-ninja-extra)."
        )
    framework = DJANGO_MATT if api_class in ("DjangoMattAPI", "MattAPI") else NINJA_EXTRA
    app_dir = _select_app(backend_dir, app)
    controllers_dir = _check_packages(app_dir)
    label = app_label(app_dir)
    manifest = _manifest_text(backend_dir)
    if framework == DJANGO_MATT:
        has_jwt = bool(re.search(r"django-matt\[[^\]]*\bauth\b", manifest))
    else:
        has_jwt = "django-ninja-jwt" in manifest
    return BackendLayout(
        backend_dir=backend_dir,
        framework=framework,
        app_dir=app_dir,
        app_module=_dotted(backend_dir, app_dir),
        app_label=label,
        controllers_dir=controllers_dir,
        base_model_module=_base_model_module(backend_dir),
        api_file=api_file,
        api_var=api_var,
        mount_prefix=find_mount_prefix(backend_dir, api_file, api_var),
        has_jwt=has_jwt,
        has_unfold="django-unfold" in manifest,
    )


def _import_insert_index(lines: list[str]) -> int:
    index = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(("import ", "from ")):
            if "(" in line and ")" not in line:
                while i < len(lines) and ")" not in lines[i]:
                    i += 1
            index = i + 1
        i += 1
    return index


def register_controller(text: str, api_var: str, import_line: str, controller: str) -> str:
    """Return *text* with *controller* imported and registered on *api_var*.

    The registration goes after the last existing `register_controllers(...)`
    call, or before `urlpatterns`: Ninja builds its URL list when `api.urls`
    is read, so a later registration would never be routed.
    """
    if re.search(rf"\b{re.escape(controller)}\b", text) and import_line in text:
        return text
    lines = text.split("\n")
    lines.insert(_import_insert_index(lines), import_line)
    text = "\n".join(lines)
    call = f"{api_var}.register_controllers({controller})"
    calls = list(
        re.finditer(rf"^{re.escape(api_var)}\.register_controllers\s*\(", text, re.MULTILINE)
    )
    if calls:
        depth, index = 0, calls[-1].end() - 1
        for index in range(calls[-1].end() - 1, len(text)):
            depth += {"(": 1, ")": -1}.get(text[index], 0)
            if depth == 0:
                break
        line_end = text.find("\n", index)
        line_end = len(text) if line_end == -1 else line_end
        return text[:line_end] + f"\n{call}" + text[line_end:]
    urlpatterns = re.search(r"^urlpatterns\b", text, re.MULTILINE)
    if urlpatterns:
        return text[: urlpatterns.start()] + f"{call}\n\n" + text[urlpatterns.start() :]
    return text.rstrip("\n") + f"\n\n{call}\n"
