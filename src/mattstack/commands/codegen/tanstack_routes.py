"""Plan TanStack Router file routes without breaking existing routes.

A new file can silently change the route tree: a flat `x.tsx` next to an
`x/` directory becomes the layout of every child, and a layout without
`<Outlet />` hides the pages under it. Those cases are refused.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mattstack.commands.codegen.backend_layout import GenerateError
from mattstack.commands.codegen.plan import FilePlan
from mattstack.parsers.frontend_routes import tanstack_route_id, tanstack_routes

TANSTACK_NEXT_STEPS = (
    "Next: run `bun run dev` or `bun run build` to regenerate routeTree.gen.ts "
    "before you typecheck."
)


def _tanstack_conflict(routes_dir: Path, target: Path, route_id: str) -> str | None:
    """Describe how *route_id* at *target* would clash with existing routes, if it would."""
    for route in tanstack_routes(routes_dir):
        other = route.route_id
        if route.file == target or not other:
            continue
        rel = route.file.relative_to(routes_dir).as_posix()
        if other == route_id:
            return f"{rel} already defines route {route_id}."
        if not route_id.endswith("/") and other.startswith(route_id + "/"):
            return (
                f"{rel} is nested under {route_id}; a flat {target.name} would become its "
                "layout and hide it. Generate a section index instead."
            )
        is_parent_layout = (
            other != "/" and not other.endswith("/") and route_id.startswith(other + "/")
        )
        text = route.file.read_text(encoding="utf-8", errors="replace")
        if is_parent_layout and "Outlet" not in text:
            return f"{rel} would be the layout of {route_id} but renders no <Outlet />."
    return None


def plan_tanstack_route(
    plan: FilePlan, routes_dir: Path, target: Path, render: Callable[[str], str]
) -> None:
    """Create a TanStack file route at *target*, refusing ids that clash with existing routes."""
    target = target.resolve()
    try:
        rel = target.relative_to(routes_dir).as_posix()
    except ValueError as exc:
        raise GenerateError(f"TanStack routes must live under {routes_dir}") from exc
    route_id = tanstack_route_id(routes_dir, target)
    if route_id is None:
        raise GenerateError(f"{rel} is not a TanStack route file name.")
    conflict = _tanstack_conflict(routes_dir, target, route_id)
    if conflict:
        raise GenerateError(f"Refusing to add {rel}: {conflict}")
    plan.create(target, render(route_id))
