"""Render standalone React components, pages, and hooks for `generate`."""

from __future__ import annotations

from mattstack.commands.codegen.route_options import DEFAULT_ROUTE_OPTIONS, RouteOptions
from mattstack.commands.codegen.tanstack_routes import TanStackTarget


def render_component(name: str) -> str:
    return f"""interface {name}Props {{
  className?: string;
}}

export function {name}({{ className }}: {name}Props) {{
  return (
    <div className={{className}}>
      <h2>{name}</h2>
    </div>
  );
}}

export default {name};
"""


def render_component_test(name: str) -> str:
    return f"""import {{ render, screen }} from "@testing-library/react";
import {{ describe, expect, it }} from "vitest";

import {{ {name} }} from "./index";

describe("{name}", () => {{
  it("renders its heading", () => {{
    render(<{name} />);
    expect(screen.getByText("{name}")).toBeDefined();
  }});
}});
"""


def _page_body(pascal: str, params: tuple[str, ...] = ()) -> str:
    read = f"  const {{ {', '.join(params)} }} = Route.useParams();\n" if params else ""
    shown = "".join(f"\n      <p>{param}: {{{param}}}</p>" for param in params)
    return f"""function {pascal}Page() {{
{read}  return (
    <div className="container mx-auto p-4">
      <h1>{pascal}</h1>{shown}
    </div>
  );
}}
"""


def render_tanstack_module(
    target: TanStackTarget,
    component: str,
    body: str,
    options: RouteOptions = DEFAULT_ROUTE_OPTIONS,
    *,
    imports: tuple[str, ...] = (),
    loader: str | None = None,
    header: str = "",
) -> str:
    """Render a file route for *target*: guard, loader, pending, and error wiring included.

    The guard reads the app's auth store in `beforeLoad`, so a signed-out
    navigation redirects before the page or its loader runs. It is a browser
    redirect, not authorization.
    """
    router_names = ["createFileRoute"]
    lines: list[str] = []
    extra = list(imports)
    if target.auth is not None:
        router_names.append("redirect")
        extra.append(f'import {{ useStore }} from "{target.auth.store_spec}";')
        lines += [
            "  // Browser redirect only: the API must still authorize every request.",
            "  beforeLoad: () => {",
            "    if (!useStore.getState().isAuthenticated) {",
            f'      throw redirect({{ to: "{target.auth.login_path}" }});',
            "    }",
            "  },",
        ]
    if loader is not None:
        lines.append(f"  loader: {loader},")
    lines.append(f"  component: {component},")
    tail = ""
    if options.pending and loader is not None:
        lines.append(f"  pendingComponent: {component}Pending,")
        tail += f"""
function {component}Pending() {{
  return (
    <div className="container mx-auto p-4" role="status">
      Loading...
    </div>
  );
}}
"""
    if options.error:
        router_names.append("useRouter")
        lines.append(f"  errorComponent: {component}Error,")
        tail += f"""
function {component}Error({{ error }}: ErrorComponentProps) {{
  const router = useRouter();
  return (
    <div className="container mx-auto p-4" role="alert">
      <p>{{error.message}}</p>
      <button type="button" onClick={{() => void router.invalidate()}}>
        Try again
      </button>
    </div>
  );
}}
"""
    head = f'import {{ {", ".join(router_names)} }} from "@tanstack/react-router";\n'
    if options.error:
        head += 'import type { ErrorComponentProps } from "@tanstack/react-router";\n'
    if extra:
        head += "\n" + "\n".join(extra) + "\n"
    route = f'export const Route = createFileRoute("{target.route_id}")({{\n'
    return header + head + "\n" + route + "\n".join(lines) + "\n});\n\n" + body + tail


def render_tanstack_page(
    target: TanStackTarget, pascal: str, options: RouteOptions = DEFAULT_ROUTE_OPTIONS
) -> str:
    """Render a page file route; dynamic parameters are read with `Route.useParams()`."""
    return render_tanstack_module(
        target, f"{pascal}Page", _page_body(pascal, target.params), options
    )


def render_default_page(pascal: str, error_package: str | None = None) -> str:
    """Render a default-export page for Next.js `page.tsx` or React Router `src/pages`.

    With *error_package* (`react-router` or `react-router-dom`) the module also
    exports `<pascal>PageError`, the route's data-router error boundary.
    """
    page = "export default " + _page_body(pascal)
    if error_package is None:
        return page
    return f'import {{ isRouteErrorResponse, useRouteError }} from "{error_package}";\n\n' + (
        page + render_route_error(f"{pascal}Page")
    )


def render_route_error(component: str) -> str:
    """Render `<component>Error` for a React Router data route's ErrorBoundary."""
    return f"""
export function {component}Error() {{
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${{error.status}} ${{error.statusText}}`
    : error instanceof Error
      ? error.message
      : "Unexpected error";
  return (
    <div className="container mx-auto p-4" role="alert">
      <p>{{message}}</p>
    </div>
  );
}}
"""


def render_hook(name: str) -> str:
    """Render a hook that runs an async function and tracks its state."""
    return f"""import {{ useCallback, useState }} from "react";

export function {name}<TResult, TArgs extends unknown[]>(
  fn: (...args: TArgs) => Promise<TResult>,
) {{
  const [data, setData] = useState<TResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const execute = useCallback(
    async (...args: TArgs) => {{
      setLoading(true);
      setError(null);
      try {{
        const result = await fn(...args);
        setData(result);
        return result;
      }} catch (err) {{
        const failure = err instanceof Error ? err : new Error(String(err));
        setError(failure);
        throw failure;
      }} finally {{
        setLoading(false);
      }}
    }},
    [fn],
  );

  return {{ data, loading, error, execute }};
}}
"""
