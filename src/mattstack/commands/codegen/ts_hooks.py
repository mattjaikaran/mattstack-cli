"""Render TanStack Query hooks for backend routes (`sync api-client`).

Paths are the mounted paths from `collect_api_routes`; response and body types
come from the declared contract (`response=`, return annotations, `payload:`)
before falling back to naming conventions. Mutations take their inputs as
`mutate()` variables, so values known only at submit time reach the request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from mattstack.commands.codegen.fields import to_pascal
from mattstack.commands.codegen.ts_schemas import resolve_ts_type
from mattstack.commands.codegen.ts_transport import ts_path_expression
from mattstack.parsers.api_routes import split_args
from mattstack.parsers.django_routes import Route

# ninja-extra PageNumberPaginationExtra: {count, next, previous, results}.
RESULTS_PAGE_RE = re.compile(r"^(?:\w+\.)?PaginatedResponseSchema\[(.+)\]$")
# django-ninja paginators (LimitOffset, PageNumber): {items, count}.
ITEMS_PAGE_RE = re.compile(r"^(?:\w+\.)?NinjaPaginationResponseSchema\[(.+)\]$")
LIST_ANNOTATION_RE = re.compile(r"^(?:list|List)\[(.+)\]$")
STATUS_MAP_RE = re.compile(r"^\{(.*)\}$", re.DOTALL)
SUCCESS_CODES = ("200", "201", "202", "204")
PAGE_INTERFACES = {
    "Paginated": """export interface Paginated<T> {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: T[];
}""",
    "PagedItems": """export interface PagedItems<T> {
  count: number;
  items: T[];
}""",
}


@dataclass
class HookSet:
    hooks: list[str] = field(default_factory=list)
    used_types: set[str] = field(default_factory=set)
    tanstack: set[str] = field(default_factory=lambda: {"useQuery"})
    page_shapes: set[str] = field(default_factory=set)  # keys of PAGE_INTERFACES
    # Schema name -> interface keyed by validation aliases, for request bodies.
    request_names: dict[str, str] = field(default_factory=dict)

    def page_interfaces(self) -> list[str]:
        return [PAGE_INTERFACES[shape] for shape in sorted(self.page_shapes)]


def _success_annotation(response: str) -> str | None:
    """Pick the 2xx entry of `{200: X, 404: Y}`; return other annotations as-is."""
    mapping = STATUS_MAP_RE.match(response.strip())
    if not mapping:
        return response.strip()
    for entry in split_args(mapping.group(1)):
        code, _, value = entry.partition(":")
        if code.strip() in SUCCESS_CODES:
            return value.strip()
    return None


def _resource(function_name: str) -> tuple[str, bool]:
    for prefix in ("list_", "get_", "create_", "update_", "partial_update_", "delete_", "patch_"):
        if function_name.startswith(prefix):
            resource = function_name[len(prefix) :]
            is_list = prefix == "list_"
            if is_list and resource.endswith("s"):
                resource = resource[:-1]
            return to_pascal(resource), is_list
    return "", False


def _by_convention(resource: str, suffixes: tuple[str, ...], known: set[str]) -> str | None:
    return next((resource + s for s in suffixes if resource + s in known), None)


def response_type(route: Route, known: set[str]) -> tuple[str, str | None]:
    """Return (TypeScript type, page query style) for the route's success response.

    The query style is "page" (page/page_size), "limit" (limit/offset), or None
    for an unpaginated response. `@paginate` with a plain `list[X]` response is
    rewritten by Ninja to its paginator's output shape.
    """
    pagination = route.pagination or ""
    query = "limit" if "LimitOffset" in pagination else "page"
    if route.response:
        annotation = _success_annotation(route.response)
        if annotation is None or annotation in ("None", "none"):
            return "void", None
        if page := RESULTS_PAGE_RE.match(annotation):
            return f"Paginated<{resolve_ts_type(page.group(1), known)}>", query
        if page := ITEMS_PAGE_RE.match(annotation):
            return f"PagedItems<{resolve_ts_type(page.group(1), known)}>", query
        if pagination and (items := LIST_ANNOTATION_RE.match(annotation)):
            shape = "Paginated" if pagination.endswith("Extra") else "PagedItems"
            return f"{shape}<{resolve_ts_type(items.group(1), known)}>", query
        return resolve_ts_type(annotation, known), None
    if route.method == "DELETE":
        return "void", None
    resource, is_list = _resource(route.function_name)
    name = _by_convention(resource, ("ResponseSchema", "Schema", "Response", ""), known)
    if name is None:
        return "unknown", None
    return (f"{name}[]" if is_list else name), None


def body_type(route: Route, known: set[str], request_names: dict[str, str] | None = None) -> str:
    """TypeScript type of the request body, keyed the way the backend validates it."""
    if route.body_type:
        resolved = resolve_ts_type(route.body_type, known)
    else:
        resource, _ = _resource(route.function_name)
        suffixes = (
            ("CreateSchema", "Create", "Input")
            if route.method == "POST"
            else ("UpdateSchema", "Update", "Input")
        )
        resolved = _by_convention(resource, suffixes, known) or "unknown"
    for name, request_name in (request_names or {}).items():
        resolved = re.sub(rf"\b{name}\b", request_name, resolved)
    return resolved


def _collection(path: str) -> str:
    """Path prefix whose cached queries a mutation on *path* invalidates."""
    head = path.split("{", 1)[0]
    return head if head.endswith("/") else head.rsplit("/", 1)[0] + "/"


def _hook_name(route: Route, taken: set[str]) -> str:
    name = "use" + to_pascal(route.function_name)
    if name in taken:
        qualifier = to_pascal("_".join(re.findall(r"[a-z0-9]+", route.path.split("{", 1)[0])))
        name = f"use{qualifier}{to_pascal(route.function_name)}"
    suffix = 2
    base = name
    while name in taken:
        name, suffix = f"{base}{suffix}", suffix + 1
    taken.add(name)
    return name


def render_route_hook(route: Route, known: set[str], hooks: HookSet, taken: set[str]) -> None:
    """Append the hook for *route* to *hooks*."""
    name = _hook_name(route, taken)
    params = re.findall(r"\{(\w+)\}", route.path)
    path_expr = ts_path_expression(route.path)
    result, page_query = response_type(route, known)
    hooks.used_types.update(re.findall(r"\b[A-Z]\w*", result))
    hooks.page_shapes.update(s for s in PAGE_INTERFACES if result.startswith(f"{s}<"))

    if route.method == "GET":
        args = [f"{p}: string" for p in params]
        options = ""
        key = [f'"{route.path}"', *params]
        if page_query == "limit":
            args += ["limit = 20", "offset = 0"]
            options = ", { params: { limit, offset } }"
            key += ["limit", "offset"]
        elif page_query == "page":
            args += ["page = 1", "pageSize = 20"]
            options = ", { params: { page, page_size: pageSize } }"
            key += ["page", "pageSize"]
        lines = [
            f"export function {name}({', '.join(args)}) {{",
            "  return useQuery({",
            f"    queryKey: [{', '.join(key)}],",
            f'    queryFn: () => request<{result}>("GET", {path_expr}{options}),',
        ]
        if page_query:
            lines.append("    placeholderData: keepPreviousData,")
            hooks.tanstack.add("keepPreviousData")
        if params:
            lines.append(f"    enabled: {' && '.join(f'Boolean({p})' for p in params)},")
        hooks.hooks.append("\n".join([*lines, "  });", "}"]))
        return

    hooks.tanstack.update({"useMutation", "useQueryClient"})
    has_body = route.method != "DELETE"
    data_type = body_type(route, known, hooks.request_names) if has_body else ""
    hooks.used_types.update(re.findall(r"\b[A-Z]\w*", data_type))
    if params:
        fields = [f"{p}: string" for p in params] + ([f"data: {data_type}"] if has_body else [])
        names = [*params, "data"] if has_body else params
        variables = f"{{ {', '.join(names)} }}: {{ {'; '.join(fields)} }}"
    else:
        variables = f"data: {data_type}" if has_body else ""
    body = ", { body: data }" if has_body else ""
    hooks.hooks.append(
        "\n".join(
            [
                f"export function {name}() {{",
                "  const queryClient = useQueryClient();",
                "  return useMutation({",
                f"    mutationFn: ({variables}) => request<{result}>("
                f'"{route.method}", {path_expr}{body}),',
                "    onSuccess: () =>",
                "      queryClient.invalidateQueries({",
                "        predicate: (query) => String(query.queryKey[0])"
                f'.startsWith("{_collection(route.path)}"),',
                "      }),",
                "  });",
                "}",
            ]
        )
    )


def render_hooks(
    routes: list[Route], known: set[str], request_names: dict[str, str] | None = None
) -> HookSet:
    hooks = HookSet(request_names=dict(request_names or {}))
    taken: set[str] = set()
    for route in routes:
        if not route.is_stub:
            render_route_hook(route, known, hooks, taken)
    return hooks
