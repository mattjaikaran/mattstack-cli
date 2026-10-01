"""Detect how a frontend imports modules, routes pages, and reaches the API.

Generated TypeScript must match the project it lands in: the `@/` alias root,
the router package, the bundler, and the shared HTTP transport that already
carries auth headers and key-case conversion.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

# A shared axios instance: `export const api = axios.create(` or the
# boilerplate's `export const api = createApiInstance();`.
TRANSPORT_EXPORT_RE = re.compile(
    r"^export\s+const\s+(\w+)\s*(?::\s*[\w.<>]+\s*)?=\s*(?:axios\.create|create\w*Instance)\s*\(",
    re.MULTILINE,
)
TRANSPORT_CANDIDATES = (
    "lib/api.ts",
    "api/client.ts",
    "lib/api/client.ts",
    "lib/axios.ts",
    "services/api.ts",
)
CAMEL_MARKERS = ("snakeToCamel", "camelizeKeys", "camelcase-keys", "toCamelCase(")


@dataclass(frozen=True)
class FrontendLayout:
    frontend_dir: Path
    src_dir: Path  # where components/, hooks/, api/ live
    alias_root: Path | None  # directory `@/` resolves to, when configured
    bundler: str  # "vite" | "rsbuild" | "next" | "unknown"
    router: str  # "tanstack" | "nextjs" | "react-router" | "unknown"
    app_dir: Path | None  # Next.js app router directory
    routes_dir: Path | None  # TanStack file-route directory
    transport_file: Path | None  # shared axios instance module
    transport_export: str | None
    camel_case_keys: bool  # transport converts keys to camelCase
    has_vitest: bool
    api_env_var: str | None = None  # browser env var holding the API base URL

    @property
    def env_expression(self) -> str | None:
        if not self.api_env_var:
            return None
        if self.bundler == "next":
            return f"process.env.{self.api_env_var}"
        return f"import.meta.env.{self.api_env_var}"

    def import_path(self, from_file: Path, target: Path) -> str:
        """Return the module specifier *from_file* uses to import *target*."""
        target = target.with_suffix("")
        if self.alias_root is not None:
            try:
                return "@/" + target.relative_to(self.alias_root).as_posix()
            except ValueError:
                pass
        rel = Path(os.path.relpath(target, from_file.parent)).as_posix()
        return rel if rel.startswith(".") else f"./{rel}"


def _read_json(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _dependencies(frontend_dir: Path) -> set[str]:
    data = _read_json(frontend_dir / "package.json")
    deps: set[str] = set()
    for key in ("dependencies", "devDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            deps.update(section)
    return deps


def _alias_root(frontend_dir: Path) -> Path | None:
    for name in ("tsconfig.app.json", "tsconfig.json"):
        path = frontend_dir / name
        if not path.is_file():
            continue
        # tsconfig allows comments and trailing commas; read the one key we need.
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r'"@/\*"\s*:\s*\[\s*"([^"]+)"', text)
        if match:
            target = match.group(1).removesuffix("*").removesuffix("/")
            return (frontend_dir / target).resolve()
    return None


def _transport(src_dir: Path) -> tuple[Path | None, str | None, bool]:
    for candidate in TRANSPORT_CANDIDATES:
        path = src_dir / candidate
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "axios" not in text:
            continue
        match = TRANSPORT_EXPORT_RE.search(text)
        if match:
            return path, match.group(1), any(marker in text for marker in CAMEL_MARKERS)
    return None, None, False


def detect_frontend_layout(frontend_dir: Path, api_env_var: str | None = None) -> FrontendLayout:
    """Inspect *frontend_dir* without modifying it.

    *api_env_var* is the browser variable the project's frontend reads for the
    API base URL; it comes from project config, not from guessing the bundler.
    """
    frontend_dir = frontend_dir.resolve()
    deps = _dependencies(frontend_dir)
    src_dir = frontend_dir / "src" if (frontend_dir / "src").is_dir() else frontend_dir

    if "next" in deps:
        bundler = "next"
    elif "@rsbuild/core" in deps:
        bundler = "rsbuild"
    elif "vite" in deps:
        bundler = "vite"
    else:
        bundler = "unknown"

    app_dir = next(
        (d for d in (frontend_dir / "app", frontend_dir / "src" / "app") if d.is_dir()), None
    )
    routes_dir = src_dir / "routes" if (src_dir / "routes").is_dir() else None
    if "next" in deps:
        router = "nextjs"
    elif "@tanstack/react-router" in deps:
        router = "tanstack"
    elif "react-router-dom" in deps or "react-router" in deps:
        router = "react-router"
    else:
        router = "unknown"

    transport_file, transport_export, camel = _transport(src_dir)
    return FrontendLayout(
        frontend_dir=frontend_dir,
        src_dir=src_dir,
        alias_root=_alias_root(frontend_dir),
        bundler=bundler,
        router=router,
        app_dir=app_dir if router == "nextjs" else None,
        routes_dir=routes_dir if router == "tanstack" else None,
        transport_file=transport_file,
        transport_export=transport_export,
        camel_case_keys=camel,
        has_vitest="vitest" in deps and "@testing-library/react" in deps,
        api_env_var=api_env_var,
    )
