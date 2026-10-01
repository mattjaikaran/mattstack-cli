"""Context renderers: markdown, JSON, and Claude XML, plus token budgeting."""

from __future__ import annotations

import json
from typing import Any
from xml.sax.saxutils import escape as xml_escape  # nosec B406 # Serialize XML; never parse.
from xml.sax.saxutils import quoteattr  # nosec B406 # Serialize XML; never parse.

FORMATS = ("markdown", "json", "claude")


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


def format_context_markdown(ctx: dict[str, Any]) -> str:
    lines = [f"# Project: {ctx.get('project_name', 'unknown')}", ""]
    comps = ctx.get("components", {})
    active = [k for k, v in comps.items() if v]
    if active:
        lines += [f"**Components:** {', '.join(active)}", ""]
    if "backend" in ctx:
        lines.append("## Backend")
        for k, v in ctx["backend"].items():
            lines.append(f"- **{k}:** {'unknown' if v is None else v}")
        lines.append("")
    if "frontend" in ctx:
        lines.append("## Frontend")
        for k, v in ctx["frontend"].items():
            if k == "scripts":
                lines.append(f"- **scripts:** {', '.join(v)}")
            else:
                lines.append(f"- **{k}:** {'unknown' if v is None else v}")
        lines.append("")
    if "env_vars" in ctx:
        lines += ["## Environment Variables", f"`{', '.join(ctx['env_vars'])}`", ""]
    if "makefile_targets" in ctx:
        lines += ["## Makefile Targets", f"`{', '.join(ctx['makefile_targets'])}`", ""]
    if "tools" in ctx:
        lines.append("## Dev Tools")
        for tool, ver in ctx["tools"].items():
            lines.append(f"- **{tool}:** {ver}")
        lines.append("")
    if "models" in ctx and ctx["models"]:
        lines.append("## Models")
        for m in ctx["models"]:
            field_names = ", ".join(f["name"] for f in m.get("fields", []))
            inherits = m["inherits"]
            flds = field_names or "none"
            lines.append(f"- **{m['name']}** ({m['app']}) inherits `{inherits}` — fields: {flds}")
        lines.append("")
    if "routes" in ctx and ctx["routes"]:
        lines.append("## API Routes")
        for c in ctx["routes"]:
            lines.append(f"### {c['controller']} — `{c['prefix']}`")
            for ep in c.get("endpoints", []):
                auth_mark = " 🔒" if ep["auth"] else ""
                resp = f" → {ep['response']}" if ep["response"] else ""
                lines.append(f"  - `{ep['method']} {c['prefix']}{ep['path']}`{resp}{auth_mark}")
        lines.append("")
    if "interfaces" in ctx and ctx["interfaces"]:
        lines.append("## TypeScript Interfaces")
        for iface in ctx["interfaces"]:
            field_names = ", ".join(f["name"] for f in iface.get("fields", []))
            lines.append(f"- **{iface['name']}** — {field_names or 'no fields'}")
        lines.append("")
    return "\n".join(lines)


def _attrs(pairs: list[tuple[str, Any]]) -> str:
    """Render XML attributes with escaped, quoted values; ``None`` values are omitted."""
    return "".join(f" {key}={quoteattr(str(value))}" for key, value in pairs if value is not None)


def _typed_fields(fields: list[dict[str, Any]]) -> list[str]:
    return [
        "      <field"
        + _attrs(
            [
                ("name", f["name"]),
                ("type", f["type"]),
                ("optional", "true" if f["optional"] else None),
            ]
        )
        + "/>"
        for f in fields
    ]


def format_context_claude(ctx: dict[str, Any]) -> str:
    """Wrap context in Claude XML blocks; all dynamic text is XML-escaped."""
    parts = ["<context>"]
    if "project_name" in ctx:
        project_attrs = _attrs([("name", ctx["project_name"]), ("path", ctx.get("project_path"))])
        parts.append(f"  <project{project_attrs}>")
        comps = ctx.get("components", {})
        active = [k for k, v in comps.items() if v]
        if active:
            parts.append(f"    <components>{xml_escape(', '.join(active))}</components>")
        parts.append("  </project>")
    if "models" in ctx and ctx["models"]:
        parts.append("  <models>")
        for m in ctx["models"]:
            model_attrs = _attrs(
                [("name", m["name"]), ("app", m["app"]), ("inherits", m["inherits"])]
            )
            parts.append(f"    <model{model_attrs}>")
            for f in m.get("fields", []):
                extra = [(k, v) for k, v in f.items() if k not in ("name", "type")]
                field_attrs = _attrs([("name", f["name"]), ("type", f["type"]), *extra])
                parts.append(f"      <field{field_attrs}/>")
            parts.append("    </model>")
        parts.append("  </models>")
    if "routes" in ctx and ctx["routes"]:
        parts.append("  <routes>")
        for c in ctx["routes"]:
            ctrl_attrs = _attrs(
                [("name", c["controller"]), ("prefix", c["prefix"]), ("tag", c["tag"] or None)]
            )
            parts.append(f"    <controller{ctrl_attrs}>")
            for ep in c.get("endpoints", []):
                ep_attrs = _attrs(
                    [
                        ("method", ep["method"]),
                        ("path", ep["path"]),
                        ("handler", ep["handler"]),
                        ("response", ep["response"] or None),
                        ("auth", "true" if ep["auth"] else None),
                    ]
                )
                parts.append(f"      <endpoint{ep_attrs}/>")
            parts.append("    </controller>")
        parts.append("  </routes>")
    if "interfaces" in ctx and ctx["interfaces"]:
        parts.append("  <types>")
        for iface in ctx["interfaces"]:
            iface_attrs = _attrs([("name", iface["name"]), ("extends", iface["extends"] or None)])
            parts.append(f"    <interface{iface_attrs}>")
            parts.extend(_typed_fields(iface.get("fields", [])))
            parts.append("    </interface>")
        parts.append("  </types>")
    if "zod_schemas" in ctx and ctx["zod_schemas"]:
        parts.append("  <zod_schemas>")
        for schema in ctx["zod_schemas"]:
            parts.append(f"    <schema{_attrs([('name', schema['name'])])}>")
            parts.extend(_typed_fields(schema.get("fields", [])))
            parts.append("    </schema>")
        parts.append("  </zod_schemas>")
    parts.append("</context>")
    return "\n".join(parts)


def apply_format(ctx: dict[str, Any], fmt: str, include_token_count: bool = True) -> str:
    """Render ``ctx`` as ``fmt`` (one of ``FORMATS``)."""
    if fmt == "json":
        if include_token_count:
            text = json.dumps(ctx, indent=2)
            ctx_with_tokens = {**ctx, "_estimated_tokens": estimate_tokens(text)}
            return json.dumps(ctx_with_tokens, indent=2)
        return json.dumps(ctx, indent=2)
    if fmt == "claude":
        text = format_context_claude(ctx)
        if include_token_count:
            text += f"\n<!-- Estimated tokens: ~{estimate_tokens(text):,} -->"
        return text
    text = format_context_markdown(ctx)
    if include_token_count:
        tokens = estimate_tokens(text)
        text += f"\n\n# Estimated tokens: ~{tokens:,}"
    return text


def truncate_to_tokens(ctx: dict[str, Any], max_tokens: int, fmt: str) -> dict[str, Any]:
    """Naively trim lists in ctx until estimated token count fits."""
    text = apply_format(ctx, fmt, include_token_count=False)
    if estimate_tokens(text) <= max_tokens:
        return ctx
    # Trim models / routes / interfaces
    for key in ("models", "routes", "interfaces", "zod_schemas"):
        if key in ctx and isinstance(ctx[key], list):
            while ctx[key] and estimate_tokens(apply_format(ctx, fmt, False)) > max_tokens:
                ctx[key] = ctx[key][:-1]
    return ctx
