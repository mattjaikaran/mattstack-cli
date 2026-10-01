"""Render standalone React components, pages, and hooks for `generate`."""

from __future__ import annotations


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


def _page_body(pascal: str) -> str:
    return f"""function {pascal}Page() {{
  return (
    <div className="container mx-auto p-4">
      <h1>{pascal}</h1>
    </div>
  );
}}
"""


def render_tanstack_page(route_path: str, pascal: str) -> str:
    return (
        'import { createFileRoute } from "@tanstack/react-router";\n\n'
        f'export const Route = createFileRoute("{route_path}")({{\n'
        f"  component: {pascal}Page,\n}});\n\n" + _page_body(pascal)
    )


def render_nextjs_page(pascal: str) -> str:
    return "export default " + _page_body(pascal)


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
