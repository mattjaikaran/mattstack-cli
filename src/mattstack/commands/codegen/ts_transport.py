"""Render the `request` helper generated TypeScript modules call the API with.

When the frontend already has a shared axios instance, generated code goes
through it so auth headers, refresh, and key-case conversion stay in one
place. Otherwise a fetch helper reads the bundler's API base URL env var and
falls back to the backend's real mount prefix.
"""

from __future__ import annotations

from pathlib import Path

from mattstack.parsers.frontend_layout import FrontendLayout

REQUEST_TYPES = [
    'type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";',
    "type QueryParams = Record<string, string | number | boolean | undefined>;",
    "interface RequestOptions {",
    "  params?: QueryParams;",
    "  body?: unknown;",
    "}",
]


def render_request_helper(layout: FrontendLayout, module_file: Path, api_prefix: str) -> str:
    """Return imports plus a module-local `request<T>(method, path, options)` helper."""
    if layout.transport_file is not None and layout.transport_export:
        spec = layout.import_path(module_file, layout.transport_file)
        lines = [
            f'import {{ {layout.transport_export} as http }} from "{spec}";',
            "",
            *REQUEST_TYPES,
            "",
            "async function request<T>(method: HttpMethod, path: string, "
            "options: RequestOptions = {}): Promise<T> {",
            "  const response = await http.request<T>({ method, url: path, "
            "params: options.params, data: options.body });",
            "  return response.data;",
            "}",
        ]
        return "\n".join(lines) + "\n"

    fallback = api_prefix.rstrip("/") or ""
    env = layout.env_expression
    base = f'({env} ?? "{fallback}")' if env else f'"{fallback}"'
    lines = [
        f'const API_BASE_URL = String({base}).replace(/\\/+$/, "");',
        "",
        *REQUEST_TYPES,
        "",
        "async function request<T>(method: HttpMethod, path: string, "
        "options: RequestOptions = {}): Promise<T> {",
        "  const query = new URLSearchParams();",
        "  for (const [key, value] of Object.entries(options.params ?? {})) {",
        "    if (value !== undefined) query.set(key, String(value));",
        "  }",
        '  const search = query.toString() ? `?${query.toString()}` : "";',
        "  const hasBody = options.body !== undefined;",
        "  const response = await fetch(`${API_BASE_URL}${path}${search}`, {",
        "    method,",
        '    credentials: "include",',
        '    headers: hasBody ? { "Content-Type": "application/json" } : undefined,',
        "    body: hasBody ? JSON.stringify(options.body) : undefined,",
        "  });",
        "  if (!response.ok) {",
        "    throw new Error(`${method} ${path} failed with status ${response.status}`);",
        "  }",
        "  if (response.status === 204) return undefined as T;",
        "  return (await response.json()) as T;",
        "}",
    ]
    return "\n".join(lines) + "\n"
