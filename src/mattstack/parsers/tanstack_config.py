"""Read the TanStack Router generator options a frontend configures.

The router plugin merges ``tsr.config.json`` with the options passed inline to
the bundler plugin (inline options win), then resolves paths against the
frontend directory. Only string literals are read. A computed option, several
plugin calls, a virtual route config, or a file filter this module does not
model is reported in ``TanStackConfig.error`` so generators refuse to guess
where routes live.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from mattstack.parsers.js_literals import LiteralError, parse_object, skip_space, string_value

CONFIG_FILES = tuple(
    f"{tool}.config.{ext}"
    for tool in ("vite", "rsbuild", "rspack", "webpack")
    for ext in ("ts", "mts", "cts", "js", "mjs", "cjs")
)
PLUGIN_EXPORTS = (
    "tanstackRouter",
    "TanStackRouterVite",
    "TanStackRouterRspack",
    "TanStackRouterWebpack",
    "TanStackRouterEsbuild",
)
PATH_KEYS = ("routesDirectory", "generatedRouteTree")
TOKEN_KEYS = ("indexToken", "routeToken", "routeFileIgnorePrefix")
# Options that change which files are routes in ways this module does not model.
UNSUPPORTED_KEYS = ("virtualRouteConfig", "routeFilePrefix", "routeFileIgnorePattern")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]+")
_IMPORT_RE = re.compile(
    r"""import\s*\{([^}]*)\}\s*from\s*['"]@tanstack/router-(?:plugin(?:/[\w-]+)?|vite-plugin)['"]"""
)


class RouteNaming(NamedTuple):
    """File-name tokens of TanStack's file-based routing."""

    index_token: str = "index"
    route_token: str = "route"
    ignore_prefix: str = "-"


@dataclass(frozen=True)
class TanStackConfig:
    routes_dir: Path
    generated_route_tree: Path
    naming: RouteNaming = RouteNaming()
    source: Path | None = None  # config file that set an option; None for defaults
    error: str | None = None  # why the configuration cannot be trusted


def _plugin_names(text: str) -> set[str]:
    names: set[str] = set()
    for match in _IMPORT_RE.finditer(text):
        for spec in match.group(1).split(","):
            parts = spec.split()
            if parts and parts[0] in PLUGIN_EXPORTS:
                names.add(parts[-1] if len(parts) == 3 and parts[1] == "as" else parts[0])
    return names


def _inline_options(path: Path) -> tuple[dict[str, str], str | None]:
    """Return (literal options, error) from the router plugin call in *path*."""
    text = path.read_text(encoding="utf-8", errors="replace")
    names = _plugin_names(text)
    if not names:
        return {}, None
    pattern = re.compile(r"(?<![\w$.])(" + "|".join(map(re.escape, names)) + r")\s*\(")
    calls = list(pattern.finditer(text))
    if len(calls) != 1:
        return {}, (
            f"{path.name} calls the TanStack Router plugin {len(calls)} times; "
            "keep exactly one call so the route directory is unambiguous."
        )
    start = skip_space(text, calls[0].end())
    if text[start] == ")":
        return {}, None
    if text[start] != "{":
        return {}, f"{path.name} passes computed options to {calls[0].group(1)}()."
    try:
        obj = parse_object(text, start)
    except LiteralError as exc:
        return {}, f"{path.name}: cannot read {calls[0].group(1)}() options ({exc})."
    if obj.spread or obj.computed_key:
        return {}, f"{path.name} spreads or computes {calls[0].group(1)}() options."
    options: dict[str, str] = {}
    for key in (*PATH_KEYS, *TOKEN_KEYS, *UNSUPPORTED_KEYS):
        prop = obj.props.get(key)
        if prop is None:
            continue
        literal = None if prop.shorthand else string_value(prop.value)
        if literal is None:
            return {}, f"{path.name} sets {key} to a computed value ({prop.value.strip()})."
        options[key] = literal
    return options, None


def _file_options(frontend_dir: Path) -> tuple[dict[str, str], str | None]:
    path = frontend_dir / "tsr.config.json"
    if not path.is_file():
        return {}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"tsr.config.json is not valid JSON ({exc})."
    if not isinstance(data, dict):
        return {}, "tsr.config.json must contain a JSON object."
    options: dict[str, str] = {}
    for key in (*PATH_KEYS, *TOKEN_KEYS, *UNSUPPORTED_KEYS):
        if key in data:
            if not isinstance(data[key], str):
                return {}, f"tsr.config.json sets {key} to a non-string value."
            options[key] = data[key]
    return options, None


def read_tanstack_config(frontend_dir: Path) -> TanStackConfig:
    """Return the effective route generator options of *frontend_dir*."""
    frontend_dir = frontend_dir.resolve()
    options, error = _file_options(frontend_dir)
    source = frontend_dir / "tsr.config.json" if options else None
    configs = [frontend_dir / name for name in CONFIG_FILES if (frontend_dir / name).is_file()]
    for config in configs:
        if error:
            break
        inline, error = _inline_options(config)
        if inline:
            options = {**options, **inline}
            source = config
    defaults = TanStackConfig(
        routes_dir=frontend_dir / "src" / "routes",
        generated_route_tree=frontend_dir / "src" / "routeTree.gen.ts",
        source=source,
    )
    for key in UNSUPPORTED_KEYS:
        if key in options and not error:
            error = f"{key} is set; generate routes by hand or remove the option."
    naming = RouteNaming(
        options.get("indexToken", "index"),
        options.get("routeToken", "route"),
        options.get("routeFileIgnorePrefix", "-"),
    )
    if not error and not all(_TOKEN_RE.fullmatch(token) for token in naming):
        error = "indexToken, routeToken, and routeFileIgnorePrefix must be plain words."
    if not error and (naming.index_token == naming.route_token or naming.ignore_prefix == "_"):
        error = "indexToken must differ from routeToken, and the ignore prefix cannot be '_'."
    routes_dir = (frontend_dir / options.get("routesDirectory", "./src/routes")).resolve()
    tree = (frontend_dir / options.get("generatedRouteTree", "./src/routeTree.gen.ts")).resolve()
    if not error and not routes_dir.is_relative_to(frontend_dir):
        error = f"routesDirectory {options['routesDirectory']} is outside the frontend."
    if error:
        where = source or (configs[0] if configs else frontend_dir)
        return TanStackConfig(
            defaults.routes_dir, defaults.generated_route_tree, error=error, source=where
        )
    return TanStackConfig(routes_dir, tree, naming, source)
