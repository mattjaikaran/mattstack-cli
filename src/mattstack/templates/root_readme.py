"""Root README.md template for generated projects."""

from __future__ import annotations

from mattstack.config import FrontendFramework, ProjectConfig
from mattstack.runtime_profiles import task_summary


def generate_readme(config: ProjectConfig) -> str:
    """Generate project README.md."""
    sections = [_header(config), _tech_stack(config), _quickstart(config)]

    if config.is_fullstack:
        sections.append(_project_structure_fullstack(config))
    elif config.has_backend:
        sections.append(_project_structure_backend(config))
    elif config.has_frontend:
        sections.append(_project_structure_frontend(config))

    sections.append(_prerequisites())
    sections.append(_commands(config))

    if config.has_backend:
        sections.append(_api_docs(config))

    if config.is_b2b:
        sections.append(_b2b_features())

    return "\n\n".join(sections) + "\n"


def _prerequisites() -> str:
    """Return the tools the generated Makefile calls."""
    return """\
## Prerequisites

Install these before you run `make setup`:

| Tool | Used by |
|---|---|
| [uv](https://docs.astral.sh/uv/) | Backend dependencies and Django commands |
| [bun](https://bun.sh/) | Frontend dependencies and scripts |
| [Docker](https://docs.docker.com/get-docker/) | `make up` and the database |
| [mattstack](https://github.com/mattjaikaran/mattstack-cli) | `make sync-types`, `make gauntlet` |

```bash
uv tool install git+https://github.com/mattjaikaran/mattstack-cli
```"""


def _header(config: ProjectConfig) -> str:
    variant = " (B2B)" if config.is_b2b else ""
    return f"# {config.display_name}{variant}"


def _tech_stack(config: ProjectConfig) -> str:
    stack: list[str] = []
    if config.has_backend:
        if config.is_nestjs_backend:
            stack.append("- **Backend**: NestJS v11 + Fastify (TypeScript)")
            stack.append("- **ORM**: Drizzle ORM")
        else:
            stack.append("- **Backend**: Django + Django Ninja (Python)")
        stack.append("- **Database**: PostgreSQL 17")
        if config.use_redis:
            stack.append("- **Cache/Queue**: Redis 7")
        if config.is_nestjs_backend:
            stack.append("- **Background Jobs**: Bull (Redis-based)")
        else:
            stack.append(f"- **Background Tasks**: {task_summary(config)}")
        if config.use_realtime:
            stack.append("- **Realtime**: Centrifugo (`make up-realtime`)")
    if config.has_frontend:
        stack.append(f"- **Frontend**: {_frontend_description(config)}")
    if config.include_ios:
        stack.append("- **iOS**: SwiftUI (iOS 17+)")

    stack_list = "\n".join(stack)
    return f"## Tech Stack\n\n{stack_list}"


# Router per template, from each source repo's package.json and route files.
_FRONTEND_DESCRIPTIONS = {
    FrontendFramework.REACT_VITE: (
        "React + Vite + TypeScript (TanStack Router, file routes in src/routes)"
    ),
    FrontendFramework.REACT_VITE_STARTER: (
        "React + Vite + TypeScript (React Router, JSX routes in src/App.tsx)"
    ),
    FrontendFramework.REACT_RSBUILD: (
        "React + Rsbuild + TypeScript (TanStack Router, file routes in src/routes)"
    ),
    FrontendFramework.REACT_RSBUILD_KIBO: (
        "React + Rsbuild + Kibo UI + TypeScript "
        "(TanStack Router file routes in src/routes, TanStack Table)"
    ),
    FrontendFramework.NEXTJS: "Next.js (App Router, TypeScript, Tailwind)",
}


def _frontend_description(config: ProjectConfig) -> str:
    return _FRONTEND_DESCRIPTIONS[config.frontend_framework]


def _frontend_label(config: ProjectConfig) -> str:
    if config.is_nextjs:
        return "Next.js App"
    if config.frontend_framework == FrontendFramework.REACT_VITE_STARTER:
        return "React SPA (React Router)"
    return "React SPA (TanStack Router)"


def _quickstart(config: ProjectConfig) -> str:
    api_port = config.backend_api_port
    lines = [
        "## Quick Start",
        "",
        "```bash",
        "# Install dependencies",
        "make setup",
    ]

    if config.has_backend:
        lines.extend(
            [
                "",
                "# Start services (Docker)",
                "make up",
                "",
                "# Run database migrations",
                "make backend-migrate",
            ]
        )
        if config.is_django_backend:
            lines.extend(
                [
                    "",
                    "# Create admin user",
                    "make backend-superuser",
                ]
            )

    lines.append("")
    lines.append("# Start dev servers")

    if config.has_backend:
        lines.append(f"make backend-dev   # http://localhost:{api_port}")

    if config.has_frontend:
        lines.append("make frontend-dev  # http://localhost:3000")

    lines.append("```")
    return "\n".join(lines)


def _project_structure_fullstack(config: ProjectConfig) -> str:
    ios_line = "\n├── ios/                  # iOS client (SwiftUI)" if config.include_ios else ""
    fe_label = _frontend_label(config)
    backend_label = "NestJS API (TypeScript)" if config.is_nestjs_backend else "Django API (Python)"
    return f"""\
## Project Structure

```
{config.name}/
├── backend/              # {backend_label}
├── frontend/             # {fe_label}{ios_line}
├── docker-compose.yml    # Dev services
├── docker-compose.prod.yml
├── Makefile              # All commands
├── .env.example
└── CLAUDE.md
```"""


def _project_structure_backend(config: ProjectConfig) -> str:
    backend_label = "NestJS API (TypeScript)" if config.is_nestjs_backend else "Django API (Python)"
    return f"""\
## Project Structure

```
{config.name}/
├── backend/              # {backend_label}
├── docker-compose.yml    # Dev services
├── Makefile
├── .env.example
└── CLAUDE.md
```"""


def _project_structure_frontend(config: ProjectConfig) -> str:
    label = _frontend_label(config)
    return f"""\
## Project Structure

```
{config.name}/
├── frontend/             # {label}
├── Makefile
└── .env.example
```"""


def _commands(config: ProjectConfig) -> str:
    rows = [
        ("| Command | Description |", True),
        ("|---------|-------------|", True),
        ("| `make setup` | Install all dependencies |", True),
        ("| `make up` | Start Docker services |", config.has_backend),
        ("| `make down` | Stop Docker services |", config.has_backend),
        ("| `make test` | Run all tests |", True),
        ("| `make lint` | Lint all code |", True),
        ("| `make format` | Format all code |", True),
    ]

    table = "\n".join(row for row, include in rows if include)

    return f"""\
## Commands

Run `make help` to see all available commands.

{table}"""


def _api_docs(config: ProjectConfig) -> str:
    api_port = config.backend_api_port
    if config.is_nestjs_backend:
        return f"""\
## API Documentation

- Swagger UI: http://localhost:{api_port}/api/docs
- OpenAPI JSON: http://localhost:{api_port}/api-json"""
    return f"""\
## API Documentation

- Swagger UI: http://localhost:{api_port}/api/docs
- OpenAPI JSON: http://localhost:{api_port}/api/openapi.json"""


def _b2b_features() -> str:
    return """\
## B2B Features

After running `make setup` and `make backend-migrate`, generate B2B features:

```bash
cd backend
uv run python manage.py generate_feature organizations
uv run python manage.py generate_feature teams
uv run python manage.py generate_feature rbac
uv run python manage.py makemigrations
uv run python manage.py migrate
```"""
