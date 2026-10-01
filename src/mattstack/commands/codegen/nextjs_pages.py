"""Place generated Next.js App Router pages, optionally inside route groups.

A `(group)` folder changes layout nesting but not the URL, so a page in a new
group can collide with an existing page or route handler at the same URL;
Next.js fails the build on that. Collisions and groups that would render
without any root layout are refused before the page is planned.
"""

from __future__ import annotations

import re
from pathlib import Path

from mattstack.commands.codegen.backend_layout import GenerateError
from mattstack.commands.codegen.plan import FilePlan
from mattstack.parsers.frontend_layout import FrontendLayout
from mattstack.parsers.nextjs_routes import parse_nextjs_routes

_GROUP_RE = re.compile(r"\([a-z0-9][a-z0-9-]*\)")
_SEGMENT_RE = re.compile(r"[a-z0-9][a-z0-9-]*|\[(?:\.\.\.)?[A-Za-z_]\w*\]")
LAYOUT_NAMES = tuple(f"layout{suffix}" for suffix in (".tsx", ".ts", ".jsx", ".js"))


def next_group_segments(value: str) -> list[str]:
    """Parse `--app-group`: `dashboard`, `(dashboard)`, or `(app)/(dashboard)`."""
    groups = []
    for part in value.strip("/").split("/"):
        group = part if part.startswith("(") else f"({part})"
        if not _GROUP_RE.fullmatch(group):
            raise GenerateError(
                f"Route group {part!r} is not valid; use lowercase-kebab names such as "
                "dashboard or (dashboard)."
            )
        groups.append(group)
    return groups


def next_route_segments(route: str) -> list[str]:
    """Parse a Next.js route such as `/(app)/reports/[reportId]` into folder names."""
    if not route.startswith("/"):
        raise GenerateError(f"Route {route!r} must start with '/', e.g. /reports/[reportId].")
    segments = [s for s in route.strip("/").split("/") if s]
    for segment in segments:
        if not (_GROUP_RE.fullmatch(segment) or _SEGMENT_RE.fullmatch(segment)):
            raise GenerateError(
                f"Route segment {segment!r} is not supported. Use lowercase-kebab segments, "
                "(group), [param], or a final [...slug]."
            )
    dynamic = [s for s in segments if s.startswith("[...")]
    if len(dynamic) > 1 or (dynamic and segments[-1] != dynamic[0]):
        raise GenerateError("A [...catch-all] segment must be the last segment of the route.")
    return segments


def next_segments_for_dir(layout: FrontendLayout, directory: Path, segment: str) -> list[str]:
    """Return the folders of page *segment* in *directory* (for `--path`)."""
    if layout.app_dir is None:
        raise GenerateError("The Next.js app directory does not exist.")
    try:
        parts = directory.resolve().relative_to(layout.app_dir.resolve()).parts
    except ValueError as exc:
        raise GenerateError(
            f"--path {directory} is outside the Next.js app directory {layout.app_dir}; "
            "pass a directory under it, or use --route."
        ) from exc
    return next_route_segments("/" + "/".join([*parts, segment]))


def _url_key(segments: list[str] | tuple[str, ...]) -> str:
    parts = [s for s in segments if not _GROUP_RE.fullmatch(s) and not s.startswith("@")]
    keyed = ["[...]" if s.startswith("[...") else "[]" if s.startswith("[") else s for s in parts]
    return "/" + "/".join(keyed)


def plan_nextjs_page(
    plan: FilePlan, layout: FrontendLayout, segments: list[str], content: str
) -> Path:
    """Plan `app/<segments>/page.tsx`, refusing URL collisions; return the page path."""
    app_dir = layout.app_dir
    if app_dir is None:
        raise GenerateError("Next.js page generation needs an app/ or src/app/ directory.")
    target = app_dir.joinpath(*segments, "page.tsx")
    url = _url_key(segments)
    for route in parse_nextjs_routes(app_dir):
        folders = route.file.parent.relative_to(app_dir).parts
        if route.file.parent == target.parent or _url_key(folders) != url:
            continue
        kind = "page" if route.route_type == "page" else "route handler"
        raise GenerateError(
            f"Refusing to add {target.relative_to(app_dir)}: "
            f"{route.file.relative_to(app_dir)} is a {kind} for the same URL {route.path}. "
            "Pick another name or route group."
        )
    groups = [i for i, s in enumerate(segments) if _GROUP_RE.fullmatch(s)]
    has_root_layout = any((app_dir / name).is_file() for name in LAYOUT_NAMES)
    if groups and not has_root_layout:
        chain = [app_dir.joinpath(*segments[: i + 1]) for i in groups]
        if not any((d / name).is_file() for d in chain for name in LAYOUT_NAMES):
            named = "/".join(segments[i] for i in groups)
            raise GenerateError(
                f"{app_dir.name}/ has no root layout and the groups {named} have none "
                "either; Next.js needs a root layout for every page. Add layout.tsx to "
                "the group first."
            )
    plan.create(target, content)
    return target
