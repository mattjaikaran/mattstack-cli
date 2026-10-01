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

from mattstack.parsers.react_router_source import RouteSource, locate_react_router
from mattstack.parsers.tanstack_config import TanStackConfig, read_tanstack_config

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
    routes_dir: Path | None  # TanStack file-route directory (plugin routesDirectory)
    transport_file: Path | None  # shared axios instance module
    transport_export: str | None
    camel_case_keys: bool  # transport converts keys to camelCase
    has_vitest: bool
    api_env_var: str | None = None  # browser env var holding the API base URL
    pages_dir: Path | None = None  # React Router page components (src/pages)
    app_entry: Path | None = None  # React Router module declaring the route tree
    route_source: RouteSource | None = None  # React Router declaration style and module
    tanstack: TanStackConfig | None = None  # TanStack generator options
    router_issue: str | None = None  # why routes cannot be located or edited safely

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


def package_dependencies(frontend_dir: Path) -> set[str]:
    """Return dependency and devDependency names from *frontend_dir*/package.json."""
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
    deps = package_dependencies(frontend_dir)
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
    tanstack = read_tanstack_config(frontend_dir) if "@tanstack/react-router" in deps else None
    routes_dir = tanstack.routes_dir if tanstack and tanstack.routes_dir.is_dir() else None
    if "next" in deps:
        router = "nextjs"
    elif "@tanstack/react-router" in deps:
        router = "tanstack"
    elif "react-router-dom" in deps or "react-router" in deps:
        router = "react-router"
    else:
        router = "unknown"

    transport_file, transport_export, camel = _transport(src_dir)
    is_react_router = router == "react-router"
    pages_dir = src_dir / "pages" if is_react_router and (src_dir / "pages").is_dir() else None
    alias_root = _alias_root(frontend_dir)
    route_source, issue = (
        locate_react_router(src_dir, alias_root) if is_react_router else (None, None)
    )
    if router == "tanstack" and tanstack is not None and tanstack.error:
        issue = f"{tanstack.source.name if tanstack.source else 'TanStack'}: {tanstack.error}"
    return FrontendLayout(
        frontend_dir=frontend_dir,
        src_dir=src_dir,
        alias_root=alias_root,
        bundler=bundler,
        router=router,
        app_dir=app_dir if router == "nextjs" else None,
        routes_dir=routes_dir if router == "tanstack" else None,
        transport_file=transport_file,
        transport_export=transport_export,
        camel_case_keys=camel,
        has_vitest="vitest" in deps and "@testing-library/react" in deps,
        api_env_var=api_env_var,
        pages_dir=pages_dir,
        app_entry=route_source.entry if route_source else None,
        route_source=route_source,
        tanstack=tanstack if router == "tanstack" else None,
        router_issue=issue,
    )
