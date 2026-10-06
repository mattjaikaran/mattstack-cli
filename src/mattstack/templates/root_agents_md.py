"""Root AGENTS.md template for generated projects and `mattstack rules`.

Each component (``backend/``, ``frontend/``) owns its own ``AGENTS.md`` and
rules. The root file only points at them and holds what spans the stack:
root commands, ports, services, and cross-stack rules. Versions come from the
project's own lockfiles and manifests; a version that cannot be read is
omitted, never guessed.
"""

from __future__ import annotations

from mattstack.config import FrontendFramework, MediaStorage, ProjectConfig
from mattstack.runtime_profiles import runtime_guidance, runtime_service_lines, task_summary
from mattstack.templates.component_guidance import component_guidance
from mattstack.templates.frontend_runtime import api_base_env_var
from mattstack.templates.stack_facts import BackendFacts, Toolchain, backend_facts

_RSBUILD = FrontendFramework.REACT_RSBUILD
_KIBO = FrontendFramework.REACT_RSBUILD_KIBO

# Key from `read_versions` -> display label, in display order.
_VERSION_LABELS: tuple[tuple[str, str], ...] = (
    ("python", "Python"),
    ("django", "Django"),
    ("ruff", "Ruff"),
    ("mypy", "mypy"),
    ("node", "Node.js"),
    ("bun", "Bun"),
    ("typescript", "TypeScript"),
    ("react", "React"),
    ("tailwindcss", "Tailwind CSS"),
    ("zod", "Zod"),
    ("postgres", "PostgreSQL"),
    ("redis", "Redis"),
    ("valkey", "Valkey"),
)

TESTING_POLICY = (
    "Write tests only for bug fixes, changed contracts, and permission or boundary "
    "rules. Do not generate bulk tests."
)


def generate_agents_md(
    config: ProjectConfig,
    tools: Toolchain | None = None,
    versions: dict[str, str] | None = None,
) -> str:
    """Generate the root AGENTS.md.

    ``tools`` names the package managers the project actually uses; `init`
    omits it and gets the scaffold defaults (uv and bun). ``versions`` maps
    ``read_versions`` keys to versions read from the project.
    """
    tools = tools or Toolchain()
    backend = backend_facts(config.backend_framework, tools)
    sections = [
        _header(config),
        _structure(config, backend),
        _versions(versions or {}),
        component_guidance(config, tools),
        _cross_stack(config, backend, tools),
        f"## Testing policy\n\n{TESTING_POLICY}",
        _commands(config),
        _ports(config, backend),
        _env_vars(config, backend),
        _services(config, backend) if config.has_backend else None,
        _mattstack_commands(config),
    ]
    return "\n\n".join(section for section in sections if section) + "\n"


def _header(config: ProjectConfig) -> str:
    variant = " (B2B)" if config.is_b2b else ""
    return (
        f"# {config.display_name}{variant}\n\n"
        "Root guidance for this monorepo. Each component keeps its own rules; read them "
        "before you change that component. This file holds only cross-stack rules."
    )


def _frontend_label(config: ProjectConfig) -> str:
    if config.is_nextjs:
        return "Next.js (App Router, TypeScript)"
    if config.frontend_framework == _KIBO:
        return "React + Rsbuild + Kibo UI + TypeScript (TanStack Router/Table)"
    if config.frontend_framework == _RSBUILD:
        return "React + Rsbuild + TypeScript (TanStack Router)"
    router = (
        "TanStack Router"
        if config.frontend_framework == FrontendFramework.REACT_VITE
        else "React Router"
    )
    return f"React + Vite + TypeScript ({router})"


def _structure(config: ProjectConfig, backend: BackendFacts) -> str:
    parts: list[str] = []
    if config.has_backend:
        parts.append(f"- `backend/` — {backend.framework} ({backend.language})")
        background = backend.background if config.is_nestjs_backend else task_summary(config)
        if background:
            parts.append(f"- Background jobs: {background}")
    if config.has_frontend:
        parts.append(f"- `frontend/` — {_frontend_label(config)}")
    if config.has_backend:
        services = ["PostgreSQL", "Redis"] if config.use_redis else ["PostgreSQL"]
        parts.append(f"- `docker-compose.yml` — {', '.join(services)}")
    if config.include_ios:
        parts.append("- `ios/` — SwiftUI iOS client")
    return "## Structure\n\n" + "\n".join(parts)


def _versions(versions: dict[str, str]) -> str | None:
    rows = [f"- {label}: {versions[key]}" for key, label in _VERSION_LABELS if versions.get(key)]
    if not rows:
        return None
    return "## Versions\n\nRead from the lockfiles, manifests, and Compose images.\n\n" + "\n".join(
        rows
    )


def _cross_stack(config: ProjectConfig, backend: BackendFacts, tools: Toolchain) -> str:
    lines = ["## Cross-stack rules", ""]
    if config.has_backend and backend.is_python:
        lines.append(
            f"- Python packages: use `{tools.python_pm}`. Never use {tools.python_alternatives()}."
        )
    lines.append(
        f"- JavaScript packages: use `{tools.js_pm}`. Never use {tools.js_alternatives()}."
    )
    if config.has_backend:
        lines.append(
            "- Run `docker compose up -d` before the dev servers. "
            "Do not install PostgreSQL or Redis on the host."
        )
        lines.append(f"- Run `{backend.migrate}` after {backend.migrate_trigger}.")
    if config.is_fullstack and config.is_django_backend:
        lines.append(
            "- Types flow from backend to frontend. The backend schemas are the contract; "
            "do not edit the generated frontend client by hand."
        )
        lines.append(
            "- After any backend schema change, run `mattstack sync openapi` and commit the "
            "generated files. `mattstack sync check` must pass."
        )
    env_desc = _env_files_description(config)
    if env_desc:
        lines.append(f"- {env_desc} Never commit `.env` files.")
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


def _commands(config: ProjectConfig) -> str:
    api_port = config.backend_api_port
    lines = ["## Commands", "", "```bash", "make setup              # Install all dependencies"]
    if config.has_backend:
        lines.append("make up                 # Start Docker services (PostgreSQL, Redis)")
        lines.append("make down               # Stop Docker services")
        lines.append(f"make backend-dev        # API dev server (port {api_port})")
    if config.has_frontend:
        if config.is_nextjs:
            label = "Next.js"
        elif config.frontend_framework in (_RSBUILD, _KIBO):
            label = "Rsbuild"
        else:
            label = "Vite"
        lines.append(f"make frontend-dev       # {label} dev server (port 3000)")
    lines.append("mattstack dev          # Start all dev servers")
    lines.append("mattstack test         # Run all tests")
    lines.append("mattstack lint         # Lint all code")
    lines.append("mattstack env check    # Verify .env files are in sync")
    lines.append("```")
    return "\n".join(lines)


def _ports(config: ProjectConfig, backend: BackendFacts) -> str | None:
    api_port = config.backend_api_port
    rows: list[tuple[str, str, str]] = []
    if config.has_backend:
        rows.append((backend.service, str(api_port), f"http://localhost:{api_port}"))
        rows.append(("PostgreSQL", "5432", "—"))
        if config.use_redis:
            rows.append(("Redis", "6379", "—"))
        if backend.docs_path:
            rows.append(
                ("API Docs", str(api_port), f"http://localhost:{api_port}{backend.docs_path}")
            )
    if config.has_frontend:
        rows.append(("Frontend", "3000", "http://localhost:3000"))
    if not rows:
        return None
    table = "| Service | Port | URL |\n|---------|------|-----|\n"
    table += "\n".join(f"| {svc} | {port} | {url} |" for svc, port, url in rows)
    return "## Ports\n\n" + table


def _env_vars(config: ProjectConfig, backend: BackendFacts) -> str | None:
    parts: list[str] = []
    if config.has_backend:
        parts.append(f"- Root `.env`: {backend.env_vars}")
        if config.media_storage == MediaStorage.S3:
            parts.append(
                "- `.env.production` (S3 media, opt-in): `AWS_STORAGE_BUCKET_NAME`, "
                "`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_REGION_NAME` "
                "(default `us-east-1`). Static files stay local."
            )
    if config.has_frontend:
        parts.append(f"- Frontend: `{api_base_env_var(config)}` for the API base URL")
    if not parts:
        return None
    return "## Environment variables\n\n" + "\n".join(parts)


def _services(config: ProjectConfig, backend: BackendFacts) -> str:
    parts = ["## Docker services", "", "- `db`: PostgreSQL"]
    if config.use_redis:
        parts.append("- `redis`: Redis")
    if config.is_nestjs_backend:
        parts.append("- `api-dev`: NestJS dev server (auto-migrates on start)")
    else:
        parts.append(f"- `api-dev`: {backend.service} dev server (when using Docker)")
        parts.extend(runtime_service_lines(config))
        parts.extend(runtime_guidance(config))
    return "\n".join(parts)


def _mattstack_commands(config: ProjectConfig) -> str:
    lines = [
        "## mattstack",
        "",
        "- `mattstack doctor` — Check tools, hooks, and MCP servers",
        "- `mattstack audit` — Static analysis",
        "- `mattstack health` — Check running services",
        "- `mattstack upgrade` — Preview boilerplate changes since the recorded commit",
        "- `mattstack hooks install` — Install the git hooks, including the pre-push gate",
    ]
    if config.has_backend:
        lines.append("- `mattstack db migrate` / `mattstack db seed` — Database operations")
        if config.is_django_backend:
            lines.append(
                '- `mattstack generate model <Name> --fields "..."` — Scaffold a model, '
                "schema, and controller"
            )
    if config.has_frontend:
        lines.append("- `mattstack generate component <Name>` — Scaffold a React component")
    return "\n".join(lines)
