"""Align react-vite-boilerplate's TanStack Router packages and app code.

The boilerplate pins router-plugin 1.58.4, which resolves a router-generator
that no longer exports ``generator``, and its vite.config.ts imports
``tanstackRouter``, which 1.58.4 does not export. Align it to the line the
Rsbuild boilerplates ship. Leave react-vite-starter alone: it uses React
Router (``react-router-dom``) by design.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from mattstack.config import ProjectConfig
from mattstack.utils.console import print_info

# Exact published versions with compatible peers. Devtools does not publish
# the router's patch numbers: react-router-devtools 1.166.13 declares
# react-router ^1.168.15 and router-core ^1.168.11, which 1.169.2 satisfies;
# 1.167.x requires react-router ^1.170.
_ROUTER_LINE: dict[str, str] = {
    "@tanstack/react-router": "1.169.2",
    "@tanstack/router-plugin": "1.167.34",
}
_DEVTOOLS = "@tanstack/react-router-devtools"
_DEVTOOLS_VERSION = "1.166.13"
# Deprecated: it now only re-exports react-router-devtools at the newest line,
# whose peer range excludes the aligned router.
_LEGACY_DEVTOOLS = "@tanstack/router-devtools"

_SECTIONS = ("dependencies", "devDependencies")
_LEGACY_IMPORT = re.compile(r"""(['"])@tanstack/router-devtools\1""")


def align_tanstack_router(config: ProjectConfig) -> None:
    """Pin the coherent router line, migrate devtools, and fix route-id casts."""
    manifest = config.frontend_dir / "package.json"
    if manifest.is_file() and _align_manifest(manifest):
        print_info(
            "Aligned TanStack Router to the Rsbuild line; "
            "`make setup` regenerates frontend/bun.lock to match"
        )
    _migrate_devtools_imports(config.frontend_dir)
    _fix_route_casts(config.frontend_dir / "src" / "routes")


def _version_tuple(spec: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"[\^~]?(\d+)\.(\d+)\.(\d+)", spec.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def _raise_to(deps: dict[str, str], name: str, target: str) -> bool:
    """Raise a pinned version to ``target``; never downgrade or touch ranges."""
    current = _version_tuple(deps.get(name, ""))
    wanted = _version_tuple(target)
    if current is None or wanted is None or current >= wanted:
        return False
    deps[name] = target
    return True


def _align_manifest(manifest: Path) -> bool:
    data = json.loads(manifest.read_text())
    changed = False
    for section in _SECTIONS:
        deps = data.get(section)
        if not isinstance(deps, dict):
            continue
        for name, target in _ROUTER_LINE.items():
            changed |= _raise_to(deps, name, target)
        if _LEGACY_DEVTOOLS in deps:
            del deps[_LEGACY_DEVTOOLS]
            deps.setdefault(_DEVTOOLS, _DEVTOOLS_VERSION)
            changed = True
        if _DEVTOOLS in deps:
            changed |= _raise_to(deps, _DEVTOOLS, _DEVTOOLS_VERSION)
    if changed:
        manifest.write_text(json.dumps(data, indent=2) + "\n")
    return changed


def _source_files(frontend_dir: Path) -> list[Path]:
    files = [p for p in frontend_dir.glob("*.ts*") if p.is_file()]
    src = frontend_dir / "src"
    if src.is_dir():
        files.extend(p for p in src.rglob("*.ts*") if p.is_file())
    return sorted(files)


def _migrate_devtools_imports(frontend_dir: Path) -> None:
    """Point imports at react-router-devtools, which exports the same names."""
    migrated = 0
    for path in _source_files(frontend_dir):
        text = path.read_text()
        patched = _LEGACY_IMPORT.sub(lambda m: f"{m.group(1)}{_DEVTOOLS}{m.group(1)}", text)
        if patched != text:
            path.write_text(patched)
            migrated += 1
    if migrated:
        print_info(f"Migrated {migrated} file(s) to {_DEVTOOLS}")


def _route_id(routes_dir: Path, path: Path) -> str | None:
    """Return the TanStack route id the generator derives from a file path."""
    relative = path.relative_to(routes_dir).with_suffix("")
    parts = [segment for part in relative.parts for segment in part.split(".")]
    if not all(re.fullmatch(r"[\w$-]+", part) for part in parts):
        return None
    if parts[-1] == "index":
        return "/" + "/".join(parts[:-1]) + ("/" if len(parts) > 1 else "")
    return "/" + "/".join(parts)


def _fix_route_casts(routes_dir: Path) -> None:
    """Remove ``as any`` casts the newer router rejects in route ids.

    ``createFileRoute('/dashboard' as any)`` fails the route transform with
    "expected route id to be a string literal". Write the id the generator
    derives from the file, which also matches the generated route tree.
    """
    if not routes_dir.is_dir():
        return
    file_route = re.compile(r"createFileRoute\(\s*(['\"])([^'\"]*)\1\s+as\s+any\s*\)")
    link_target = re.compile(r"\{\s*(['\"])(/[^'\"]*)\1\s+as\s+any\s*\}")
    fixed = 0
    for path in sorted(routes_dir.rglob("*.ts*")):
        text = path.read_text()
        route_id = _route_id(routes_dir, path)

        def replace_route(match: re.Match[str], value: str | None = route_id) -> str:
            return f"createFileRoute('{value or match.group(2)}')"

        patched = file_route.sub(replace_route, text)
        patched = link_target.sub(lambda m: f'"{m.group(2)}"', patched)
        if patched != text:
            path.write_text(patched)
            fixed += 1
    if fixed:
        print_info(f"Removed route-id casts from {fixed} route file(s)")
