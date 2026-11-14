"""Root AGENTS.md template for generated projects and `mattstack rules`.

The root file holds only global invariants: package managers, root commands,
gates, cross-stack rules, git rules, and the list of nested AGENTS.md files.
Each component owns its stack rules, ports, versions, and env vars. The
output stays under 60 lines.
"""

from __future__ import annotations

from mattstack.config import ProjectConfig
from mattstack.runtime_profiles import runtime_guidance
from mattstack.templates.component_guidance import component_gates, nested_guidance
from mattstack.templates.frontend_runtime import api_version_note
from mattstack.templates.stack_facts import Toolchain, backend_facts


def generate_agents_md(config: ProjectConfig, tools: Toolchain | None = None) -> str:
    """Generate the root AGENTS.md.

    ``tools`` names the package managers the project actually uses; `init`
    omits it and gets the scaffold defaults (uv and bun).
    """
    tools = tools or Toolchain()
    sections = [
        _header(config),
        nested_guidance(config),
        _package_managers(config, tools),
        _commands(config),
        _gates(config, tools),
        _cross_stack(config, tools),
        _git(),
    ]
    return "\n\n".join(section for section in sections if section) + "\n"


def _header(config: ProjectConfig) -> str:
    variant = " (B2B)" if config.is_b2b else ""
    return (
        f"# {config.display_name}{variant}\n\n"
        "Root rules for this project. They apply to every directory. Nested "
        "AGENTS.md files add rules for their own directory."
    )


def _package_managers(config: ProjectConfig, tools: Toolchain) -> str:
    lines = ["## Package managers", ""]
    if config.has_backend and backend_facts(config.backend_framework, tools).is_python:
        lines.append(
            f"- Python packages: use `{tools.python_pm}`. Never use {tools.python_alternatives()}."
        )
    lines.append(
        f"- JavaScript packages: use `{tools.js_pm}`. Never use {tools.js_alternatives()}."
    )
    return "\n".join(lines)


def _commands(config: ProjectConfig) -> str:
    lines = ["## Commands", "", "```bash", "just setup          # Install all dependencies"]
    if config.has_backend:
        lines.append("just up             # Start Docker services")
        lines.append("just down           # Stop Docker services")
        lines.append("just backend-dev    # Start the API dev server")
    if config.has_frontend:
        lines.append("just frontend-dev   # Start the frontend dev server")
    lines.append("```")
    lines.append("")
    if config.has_backend and (config.backend_dir / "AGENTS.md").is_file():
        lines.append(
            "`backend/AGENTS.md` names recipes as `just <recipe>`. From the root, run "
            "`just backend-<recipe>` when `just --list` shows it."
        )
    return "\n".join(lines)


def _gates(config: ProjectConfig, tools: Toolchain) -> str:
    lines = ["## Gates", "", "- Root: run `just gauntlet` before you open a pull request."]
    lines.extend(component_gates(config, tools))
    return "\n".join(lines)


def _cross_stack(config: ProjectConfig, tools: Toolchain) -> str:
    lines = ["## Cross-stack rules", ""]
    if config.has_backend:
        lines.append(
            "- Run `docker compose up -d` before the dev servers. "
            "Do not install PostgreSQL or Redis on the host."
        )
        lines.append(f"- {api_version_note(config)}")
        # Root recipes (just up-<profile>, just up-realtime) exist only in the
        # monorepo, so no component AGENTS.md can describe them.
        lines.extend(runtime_guidance(config))
    if config.is_fullstack and config.is_django_backend:
        lines.append(
            "- The backend schemas are the contract. Do not edit the generated frontend "
            "client by hand."
        )
        lines.append(
            "- After any backend schema change, run `mattstack sync openapi` and commit the "
            "generated files. `mattstack sync check` must pass."
        )
    lines.append(f"- {_env_files_description(config)}")
    return "\n".join(lines)


def _env_files_description(config: ProjectConfig) -> str:
    if config.has_backend and config.has_frontend:
        return (
            "Root `.env` holds Docker and backend values; "
            "`frontend/.env.local` holds frontend values."
        )
    if config.has_backend:
        return "Root `.env` holds backend and Docker values."
    return "`frontend/.env.local` holds frontend values."


def _git() -> str:
    return "\n".join(
        [
            "## Git",
            "",
            "- Use Conventional Commits: `type(scope): imperative summary`. Keep the "
            "subject at most 50 characters and wrap the body at 72.",
            "- Name branches `<type>/<short-topic>` in lowercase kebab-case, for example "
            "`feat/product-search`.",
            "- Never commit secrets or `.env` files.",
        ]
    )
