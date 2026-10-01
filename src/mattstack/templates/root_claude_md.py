"""Root CLAUDE.md template for generated projects and `mattstack rules`."""
# ruff: noqa: E501  — template strings contain long lines by design

from __future__ import annotations

from mattstack.config import FrontendFramework, ProjectConfig
from mattstack.templates.frontend_runtime import api_base_env_var
from mattstack.templates.stack_facts import BackendFacts, Toolchain, backend_facts

_RSBUILD = FrontendFramework.REACT_RSBUILD
_KIBO = FrontendFramework.REACT_RSBUILD_KIBO


def generate_claude_md(config: ProjectConfig, tools: Toolchain | None = None) -> str:
    """Generate CLAUDE.md for AI assistant context.

    ``tools`` names the package managers the project actually uses. `init`
    omits it and gets the scaffold defaults (uv and bun).
    """
    tools = tools or Toolchain()
    backend = backend_facts(config.backend_framework, tools)
    sections = [
        _header(config),
        _structure(config, backend),
        _tech(config, backend),
        _rules(config, backend, tools),
        _commands(config),
        _ports(config, backend),
        _env_vars(config, backend),
    ]

    if config.has_backend:
        sections.append(_backend(config, backend))

    if config.has_frontend:
        sections.append(_frontend(config, tools))

    if config.include_ios:
        sections.append(_ios(config))

    if config.has_backend:
        sections.append(_docker_services(config, backend))

    sections.append(_mattstack_integration(config))

    return "\n\n".join(sections) + "\n"


def _header(config: ProjectConfig) -> str:
    variant = " (B2B)" if config.is_b2b else ""
    return f"# {config.display_name}{variant}"


def _structure(config: ProjectConfig, backend: BackendFacts) -> str:
    parts: list[str] = []
    if config.has_backend:
        parts.append(f"- `backend/` — {backend.structure}")
    if config.has_frontend:
        if config.is_nextjs:
            parts.append("- `frontend/` — Next.js (App Router, TypeScript, Tailwind)")
        elif config.frontend_framework == _KIBO:
            parts.append(
                "- `frontend/` — React + Rsbuild + Kibo UI + TypeScript (TanStack Router/Table)"
            )
        elif config.frontend_framework == _RSBUILD:
            parts.append("- `frontend/` — React + Rsbuild + TypeScript (TanStack Router)")
        else:
            fw = config.frontend_framework
            router = "TanStack Router" if fw == FrontendFramework.REACT_VITE else "React Router"
            parts.append(f"- `frontend/` — React + Vite + TypeScript ({router})")
    if config.has_backend:
        services = ["PostgreSQL 17"]
        if config.use_redis:
            services.append("Redis 7")
        parts.append(f"- `docker-compose.yml` — {', '.join(services)}")
    if config.include_ios:
        parts.append("- `ios/` — SwiftUI iOS client (iOS 17+)")
    return "## Structure\n\n" + "\n".join(parts)


def _background(config: ProjectConfig, backend: BackendFacts) -> str | None:
    """Return the background job runner, or None when the project has none."""
    if config.is_nestjs_backend:
        return backend.background
    return backend.background if config.use_celery else None


def _tech(config: ProjectConfig, backend: BackendFacts) -> str:
    parts: list[str] = []
    if config.has_backend:
        parts.append(f"- Backend: {backend.tech}")
        background = _background(config, backend)
        if background:
            parts.append(f"- Background jobs: {background}")
    if config.has_frontend:
        if config.is_nextjs:
            parts.append("- Frontend: Next.js (App Router), TypeScript (strict)")
        elif config.frontend_framework in (_RSBUILD, _KIBO):
            parts.append("- Frontend: React 19, Rsbuild (Rspack), TypeScript (strict)")
        else:
            parts.append("- Frontend: React 18, Vite, TypeScript (strict)")
    if config.include_ios:
        parts.append("- iOS: SwiftUI, MVVM, async/await, iOS 17+")
    return "## Tech Stack\n\n" + "\n".join(parts)


def _rules(config: ProjectConfig, backend: BackendFacts, tools: Toolchain) -> str:
    lines: list[str] = [
        "## Rules",
        "",
        "**CRITICAL — AI agents MUST follow these rules:**",
        "",
    ]

    uses_python = config.has_backend and backend.is_python
    if uses_python:
        lines.append(
            f"- **Python packages**: ALWAYS use `{tools.python_pm}`. "
            f"NEVER use {tools.python_alternatives()}."
        )
    lines.append(
        f"- **JavaScript packages**: ALWAYS use `{tools.js_pm}`. "
        f"NEVER use {tools.js_alternatives()}."
    )

    if config.has_backend:
        lines.append(
            "- **Docker**: Run `docker compose up -d` before dev servers. "
            "NEVER install PostgreSQL or Redis locally."
        )
        lines.append(f"- **API framework**: {backend.api_rule}")
        lines.append(
            f"- **Migrations**: ALWAYS run `{backend.migrate}` after {backend.migrate_trigger}."
        )

    type_rule = "type hints (Python) / strict TypeScript" if uses_python else "strict TypeScript"
    lines.append(f"- **Type safety**: ALWAYS use {type_rule}.")

    frontend_test = f"`{tools.js_run('test')}` in frontend"
    if config.is_fullstack:
        lines.append(f"- **Testing**: `{backend.test}` in backend, {frontend_test}.")
        lines.append(
            f"- **Linting**: `{backend.lint}` in backend, `{tools.js_run('lint')}` in frontend."
        )
        lines.append(
            f"- **Formatting**: `{backend.format}` in backend, `{tools.js_run('format')}` in frontend."
        )
    elif config.has_backend:
        lines.append(f"- **Testing**: Run `{backend.test}` in `backend/`.")
        lines.append(f"- **Linting**: Run `{backend.lint}` in `backend/`.")
        lines.append(f"- **Formatting**: Run `{backend.format}` in `backend/`.")
    else:
        lines.append(f"- **Testing**: Run `{tools.js_run('test')}` in `frontend/`.")
        lines.append(f"- **Linting**: Run `{tools.js_run('lint')}` in `frontend/`.")
        lines.append(f"- **Formatting**: Run `{tools.js_run('format')}` in `frontend/`.")

    env_desc = _env_files_description(config)
    if env_desc:
        lines.append(f"- **Env files**: {env_desc}")

    lines.append(
        "- **mattstack**: `mattstack dev` (start all), `mattstack test`, "
        "`mattstack lint`, `mattstack audit`."
    )

    return "\n".join(lines)


def _env_files_description(config: ProjectConfig) -> str:
    if config.has_backend and config.has_frontend:
        return "Root `.env` for Docker services. `frontend/.env.local` for frontend-specific vars."
    if config.has_backend:
        return "Root `.env` for backend and Docker services."
    if config.has_frontend:
        return "`frontend/.env.local` for frontend-specific vars."
    return ""


def _commands(config: ProjectConfig) -> str:
    api_port = config.backend_api_port
    lines = [
        "## Commands",
        "",
        "```bash",
        "make setup              # Install all dependencies",
    ]
    if config.has_backend:
        lines.append("make up                 # Start Docker services (PostgreSQL, Redis)")
        lines.append("make down               # Stop Docker services")
    if config.has_backend:
        lines.append(f"make backend-dev        # API dev server (port {api_port})")
    if config.has_frontend:
        if config.is_nextjs:
            label = "Next.js"
        elif config.frontend_framework in (_RSBUILD, _KIBO):
            label = "Rsbuild"
        else:
            label = "Vite"
        lines.append(f"make frontend-dev       # {label} dev server (port 3000)")
    if config.is_fullstack:
        dev_desc = "Start all dev servers (docker + backend + frontend)"
    elif config.has_backend:
        dev_desc = "Start dev servers (docker + backend)"
    else:
        dev_desc = "Start frontend dev server"
    test_desc = "Run all tests (backend + frontend)" if config.is_fullstack else "Run tests"
    lines.append(f"mattstack dev          # {dev_desc}")
    lines.append(f"mattstack test         # {test_desc}")
    lines.append("mattstack lint         # Lint all code")
    lines.append("mattstack lint --fix   # Auto-fix lint issues")
    lines.append("mattstack env check    # Verify .env files are in sync")
    lines.append("mattstack audit        # Run static analysis")
    lines.append("```")
    return "\n".join(lines)


def _ports(config: ProjectConfig, backend: BackendFacts) -> str:
    api_port = config.backend_api_port
    rows: list[tuple[str, str, str]] = []
    if config.has_backend:
        rows.append((backend.service, str(api_port), f"http://localhost:{api_port}"))
        rows.append(("PostgreSQL", "5432", "—"))
        if config.use_redis:
            rows.append(("Redis", "6379", "—"))
        if backend.docs_path:
            docs_url = f"http://localhost:{api_port}{backend.docs_path}"
            rows.append(("API Docs", str(api_port), docs_url))
    if config.has_frontend:
        rows.append(("Frontend", "3000", "http://localhost:3000"))
    if not rows:
        return ""
    table = "| Service | Port | URL |\n|---------|------|-----|\n"
    table += "\n".join(f"| {svc} | {port} | {url} |" for svc, port, url in rows)
    return "## Ports\n\n" + table


def _env_vars(config: ProjectConfig, backend: BackendFacts) -> str:
    parts: list[str] = ["## Environment Variables", ""]
    if config.has_backend:
        parts.append(f"- Root `.env`: {backend.env_vars}")
    if config.has_frontend:
        parts.append(f"- Frontend: `{api_base_env_var(config)}` for API base URL")
    if not config.has_backend and not config.has_frontend:
        return ""
    return "\n".join(parts)


def _backend(config: ProjectConfig, backend: BackendFacts) -> str:
    lines = [
        "## Backend",
        "",
        f"- Language: {backend.language}",
        f"- Framework: {backend.framework}",
        f"- Package manager: {backend.package_manager}",
        *(f"- {detail}" for detail in backend.details),
        "- Database: PostgreSQL 17 (via Docker)",
        f"- Dev server: `{backend.dev}`",
    ]
    if backend.docs_path:
        docs_url = f"http://localhost:{config.backend_api_port}{backend.docs_path}"
        lines.append(f"- API docs: {docs_url} (Swagger UI)")
    if config.use_celery and not config.is_nestjs_backend:
        lines.append("- Background jobs: Celery (run with `docker compose --profile celery up`)")
    if config.is_b2b:
        lines.append("- B2B: Organizations, teams, RBAC (role-based access control)")
    return "\n".join(lines)


def _frontend(config: ProjectConfig, tools: Toolchain) -> str:
    pm = tools.js_pm
    api_var = api_base_env_var(config)
    if config.is_nextjs:
        return f"""## Frontend

- Language: TypeScript (strict mode)
- Framework: Next.js (App Router)
- Routing: App Router (file-based)
- Package manager: {pm}
- Styling: Tailwind CSS
- API base: `{api_var}` env var
- API routes: `app/api/` directory
- Dev server: `cd frontend && {tools.js_run("dev")}` (Next.js dev server on port 3000)"""
    if config.frontend_framework in (_RSBUILD, _KIBO):
        return f"""## Frontend

- Language: TypeScript (strict mode)
- Framework: React 19 + Rsbuild (Rspack, Rust-powered)
- Routing: TanStack Router (file-based)
- Package manager: {pm}
- Styling: Tailwind CSS
- API base: `{api_var}` env var
- State management: TanStack Query (server), Zustand (client)
- Build config: `rsbuild.config.ts` (NOT vite.config.ts)"""
    router = (
        "TanStack Router"
        if config.frontend_framework == FrontendFramework.REACT_VITE
        else "React Router"
    )
    return f"""## Frontend

- Language: TypeScript (strict mode)
- Framework: React 18 + Vite
- Routing: {router}
- Package manager: {pm}
- Styling: Tailwind CSS
- API base: `{api_var}` env var
- State management: TanStack Query (server state)"""


def _ios(config: ProjectConfig) -> str:
    return """## iOS

- SwiftUI with MVVM pattern
- Async/await networking
- iOS 17+ minimum deployment target"""


def _docker_services(config: ProjectConfig, backend: BackendFacts) -> str:
    parts = ["## Docker Services", "", "- `db`: PostgreSQL 17"]
    if config.use_redis:
        parts.append("- `redis`: Redis 7")
    if config.is_nestjs_backend:
        parts.append("- `api-dev`: NestJS dev server (auto-migrates on start)")
    else:
        parts.append(f"- `api-dev`: {backend.service} dev server (when using Docker)")
        if config.use_celery:
            parts.append("- `celery-worker`, `celery-beat`: Celery (profile: celery)")
    return "\n".join(parts)


def _mattstack_integration(config: ProjectConfig) -> str:
    lines = [
        "## mattstack Integration",
        "",
        "This project was scaffolded with `mattstack`. The CLI provides unified commands:",
        "- `mattstack dev` — Start all services (Docker + backend + frontend)",
        "- `mattstack test` — Run all tests",
        "- `mattstack lint` — Lint all code",
        "- `mattstack fmt` — Format all code",
        "- `mattstack env check` — Compare .env files",
        "- `mattstack audit` — Static analysis (quality, types, endpoints, tests, dependencies)",
        "- `mattstack health` — Check service health (Docker, DB, Redis, servers)",
        "- `mattstack deps check` — Show outdated packages",
    ]
    if config.has_backend:
        lines.extend(
            [
                "- `mattstack db migrate` — Run database migrations",
                "- `mattstack db seed` — Seed database with sample data",
            ]
        )
        if config.is_django_backend:
            lines.append(
                '- `mattstack generate model <Name> --fields "..."` — Scaffold Django model + schema + router'
            )
    if config.has_backend and config.has_frontend and config.is_django_backend:
        lines.extend(
            [
                "- `mattstack sync types` — Generate TypeScript interfaces from Pydantic models",
                "- `mattstack sync zod` — Generate Zod schemas from Pydantic models",
                "- `mattstack sync api-client` — Generate TanStack Query hooks from Django routes",
            ]
        )
    if config.has_frontend:
        lines.extend(
            [
                "- `mattstack generate component <Name>` — Scaffold React component",
                "- `mattstack generate page <name>` — Scaffold route page",
            ]
        )
    lines.extend(
        [
            "- `mattstack hooks install` — Install pre-commit git hooks",
            "- `mattstack workflow` — Generate CI/CD workflows (GitHub Actions)",
        ]
    )
    return "\n".join(lines)
