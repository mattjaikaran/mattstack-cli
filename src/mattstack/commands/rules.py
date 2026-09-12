"""Rules command: generate/update AI agent configuration files."""
# ruff: noqa: E501  — template strings contain long lines by design

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated

import typer

from mattstack.detected import DetectedProject
from mattstack.utils.console import console, print_error, print_info, print_success
from mattstack.utils.package_manager import detect_package_manager


def detect_project(path: Path) -> DetectedProject:
    """Detect project configuration from filesystem."""
    path = path.resolve()
    name = path.name or "project"

    has_backend = (path / "backend" / "pyproject.toml").exists()
    has_frontend = (path / "frontend" / "package.json").exists()
    has_docker = (path / "docker-compose.yml").exists()
    has_ios = (path / "ios").is_dir() and any((path / "ios").glob("*.xcodeproj"))

    # Backend details
    backend_framework = "django-ninja"
    use_celery = False
    if has_backend:
        pyproject = path / "backend" / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8", errors="replace").lower()
        if "django" in content:
            backend_framework = "django-ninja"
        if "celery" in content:
            use_celery = True

    # Frontend details
    is_nextjs = False
    frontend_framework = "react-vite"
    if has_frontend:
        pkg_path = path / "frontend" / "package.json"
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        else:
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "next" in deps:
                is_nextjs = True
                frontend_framework = "nextjs"
            elif "vite" in deps:
                frontend_framework = "react-vite"

    # Docker Redis
    use_redis = False
    docker_services: list[str] = []
    if has_docker:
        dc_path = path / "docker-compose.yml"
        content = dc_path.read_text(encoding="utf-8", errors="replace").lower()
        if "redis" in content:
            use_redis = True
        # Extract service names
        for m in re.finditer(r"^\s{2}(\w+):\s*$", content, re.MULTILINE):
            docker_services.append(m.group(1))

    # Python package manager (uv by default, check for uv.lock)
    python_pm = "uv"
    if has_backend:
        backend_dir = path / "backend"
        if (backend_dir / "uv.lock").exists():
            python_pm = "uv"
        elif (backend_dir / "poetry.lock").exists():
            python_pm = "poetry"
        elif (backend_dir / "Pipfile.lock").exists():
            python_pm = "pipenv"

    # JS package manager from lockfiles
    js_pm_obj = detect_package_manager(path)
    js_pm = js_pm_obj.value

    # Env files
    env_files: list[str] = []
    for f in (".env.example", ".env", "frontend/.env.local"):
        if (path / f).exists():
            env_files.append(f)

    # Makefile targets
    makefile_targets: list[str] = []
    makefile = path / "Makefile"
    if makefile.exists():
        for line in makefile.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("\t") and not line.startswith("#") and ":" in line:
                target = line.split(":")[0].strip()
                if target and not target.startswith("."):
                    makefile_targets.append(target)

    return DetectedProject(
        name=name,
        has_backend=has_backend,
        has_frontend=has_frontend,
        has_docker=has_docker,
        has_ios=has_ios,
        is_nextjs=is_nextjs,
        is_b2b=False,
        use_celery=use_celery,
        use_redis=use_redis,
        python_pm=python_pm,
        js_pm=js_pm,
        backend_framework=backend_framework,
        frontend_framework=frontend_framework,
        docker_services=docker_services,
        env_files=env_files,
        makefile_targets=makefile_targets,
    )


def generate_claude_md_from_detected(project: DetectedProject) -> str:
    """Generate CLAUDE.md from detected project state."""
    sections = [
        _claude_header(project),
        _claude_structure(project),
        _claude_tech(project),
        _claude_rules(project),
        _claude_commands(project),
        _claude_ports(project),
        _claude_env_vars(project),
    ]
    if project.has_backend:
        sections.append(_claude_backend(project))
    if project.has_frontend:
        sections.append(_claude_frontend(project))
    if project.has_ios:
        sections.append(_claude_ios())
    if project.has_backend:
        sections.append(_claude_docker_services(project))
    sections.append(_claude_mattstack())
    return "\n\n".join(sections) + "\n"


def _claude_header(project: DetectedProject) -> str:
    variant = " (B2B)" if project.is_b2b else ""
    return f"# {project.display_name}{variant}"


def _claude_structure(project: DetectedProject) -> str:
    parts: list[str] = []
    if project.has_backend:
        parts.append("- `backend/` — Django API (django-ninja, Python 3.12+)")
    if project.has_frontend:
        if project.is_nextjs:
            parts.append("- `frontend/` — Next.js (App Router, TypeScript, Tailwind)")
        else:
            parts.append("- `frontend/` — React + Vite + TypeScript")
    if project.has_docker:
        services = ["PostgreSQL 17"]
        if project.use_redis:
            services.append("Redis 7")
        parts.append(f"- `docker-compose.yml` — {', '.join(services)}")
    if project.has_ios:
        parts.append("- `ios/` — SwiftUI iOS client (iOS 17+)")
    return "## Structure\n\n" + "\n".join(parts)


def _claude_tech(project: DetectedProject) -> str:
    parts: list[str] = []
    if project.has_backend:
        parts.append("- Backend: Python 3.12+, Django, django-ninja, PostgreSQL 17")
        if project.use_celery:
            parts.append("- Background: Celery + Redis")
    if project.has_frontend:
        if project.is_nextjs:
            parts.append("- Frontend: Next.js (App Router), TypeScript (strict)")
        else:
            parts.append("- Frontend: React 18, Vite, TypeScript (strict)")
    if project.has_ios:
        parts.append("- iOS: SwiftUI, MVVM, async/await, iOS 17+")
    return "## Tech Stack\n\n" + "\n".join(parts)


def _claude_rules(project: DetectedProject) -> str:
    lines = [
        "## Rules",
        "",
        "**CRITICAL — AI agents MUST follow these rules:**",
        "",
        f"- **Python packages**: ALWAYS use `{project.python_pm}`. NEVER use `pip`, `pip install`, `poetry`, or `conda`.",
        f"- **JavaScript packages**: ALWAYS use `{project.js_pm}`. NEVER use `npm`, `yarn`, or `pnpm` (unless detected).",
    ]
    if project.has_backend:
        lines.append(
            "- **Docker**: Infrastructure runs in Docker Compose. Run `docker compose up -d` before "
            "starting dev servers. NEVER install PostgreSQL or Redis locally."
        )
        lines.append(
            "- **API framework**: Backend uses django-ninja (Pydantic models, type-safe). "
            "NEVER use Django REST Framework serializers."
        )
        lines.append(
            "- **Migrations**: ALWAYS run `cd backend && uv run python manage.py makemigrations "
            "&& uv run python manage.py migrate` after model changes."
        )
    lines.append(
        "- **Type safety**: ALWAYS use type hints on every Python function. ALWAYS use strict TypeScript."
    )
    if project.is_fullstack:
        lines.append(
            "- **Testing**: Run `uv run pytest -v` in `backend/`. Run `bun run test` in `frontend/`."
        )
        lines.append(
            "- **Linting**: Run `uv run ruff check .` in `backend/`. Run `bun run lint` in `frontend/`."
        )
        lines.append(
            "- **Formatting**: Run `uv run ruff format .` in `backend/`. Run `bun run format` in `frontend/`."
        )
    elif project.has_backend:
        lines.append("- **Testing**: Run `uv run pytest -v` in `backend/`.")
        lines.append("- **Linting**: Run `uv run ruff check .` in `backend/`.")
        lines.append("- **Formatting**: Run `uv run ruff format .` in `backend/`.")
    else:
        lines.append("- **Testing**: Run `bun run test` in `frontend/`.")
        lines.append("- **Linting**: Run `bun run lint` in `frontend/`.")
        lines.append("- **Formatting**: Run `bun run format` in `frontend/`.")
    if project.env_files:
        lines.append(f"- **Env files**: {', '.join(project.env_files)}")
    lines.append(
        "- **mattstack**: Use `mattstack dev` to start all services, `mattstack test` to run all tests, "
        "`mattstack lint` to lint all code, `mattstack audit` for static analysis."
    )
    return "\n".join(lines)


def _claude_commands(project: DetectedProject) -> str:
    lines = [
        "## Commands",
        "",
        "```bash",
        "make setup              # Install all dependencies",
    ]
    if project.has_backend:
        lines.append("make up                 # Start Docker services (PostgreSQL, Redis)")
        lines.append("make down               # Stop Docker services")
    dev_desc = (
        "Start all dev servers (docker + backend + frontend)"
        if project.is_fullstack
        else "Start dev servers (docker + backend)"
        if project.has_backend
        else "Start frontend dev server"
    )
    test_desc = "Run all tests (backend + frontend)" if project.is_fullstack else "Run tests"
    lines.extend(
        [
            f"mattstack dev          # {dev_desc}",
            f"mattstack test         # {test_desc}",
            "mattstack lint         # Lint all code",
            "mattstack lint --fix   # Auto-fix lint issues",
            "mattstack env check    # Verify .env files are in sync",
            "mattstack audit        # Run static analysis",
            "```",
        ]
    )
    return "\n".join(lines)


def _claude_ports(project: DetectedProject) -> str:
    rows: list[tuple[str, str, str]] = []
    if project.has_backend:
        rows.extend(
            [
                ("Django API", "8000", "http://localhost:8000"),
                ("PostgreSQL", "5432", "—"),
            ]
        )
        if project.use_redis:
            rows.append(("Redis", "6379", "—"))
        rows.append(("API Docs", "8000", "http://localhost:8000/api/docs"))
    if project.has_frontend:
        rows.append(("Frontend", "3000", "http://localhost:3000"))
    if not rows:
        return ""
    table = "| Service | Port | URL |\n|---------|------|-----|\n"
    table += "\n".join(f"| {svc} | {port} | {url} |" for svc, port, url in rows)
    return "## Ports\n\n" + table


def _claude_env_vars(project: DetectedProject) -> str:
    parts = ["## Environment Variables", ""]
    if project.has_backend:
        parts.append("- Root `.env`: `DATABASE_URL`, `DJANGO_SECRET_KEY`, `REDIS_URL` (if Redis)")
    if project.has_frontend:
        api_var = "NEXT_PUBLIC_API_BASE_URL" if project.is_nextjs else "VITE_API_BASE_URL"
        parts.append(f"- Frontend: `{api_var}` for API base URL")
    if not project.has_backend and not project.has_frontend:
        return ""
    return "\n".join(parts)


def _claude_backend(project: DetectedProject) -> str:
    lines = [
        "## Backend",
        "",
        "- Language: Python 3.12+",
        "- Framework: Django + django-ninja",
        f"- Package manager: {project.python_pm} (NEVER pip)",
        "- Testing: pytest",
        "- Linting: ruff",
        "- Database: PostgreSQL 17 (via Docker)",
        "- API docs: http://localhost:8000/api/docs (Swagger UI)",
    ]
    if project.use_celery:
        lines.append("- Background jobs: Celery (run with `docker compose --profile celery up`)")
    if project.is_b2b:
        lines.append("- B2B: Organizations, teams, RBAC (role-based access control)")
    return "\n".join(lines)


def _claude_frontend(project: DetectedProject) -> str:
    if project.is_nextjs:
        return """## Frontend

- Language: TypeScript (strict mode)
- Framework: Next.js (App Router)
- Routing: App Router (file-based)
- Package manager: bun (NEVER npm/yarn)
- Styling: Tailwind CSS
- API base: `NEXT_PUBLIC_API_BASE_URL` env var
- API routes: `app/api/` directory"""
    return """## Frontend

- Language: TypeScript (strict mode)
- Framework: React 18 + Vite
- Routing: TanStack Router
- Package manager: bun (NEVER npm/yarn)
- Styling: Tailwind CSS
- API base: `VITE_API_BASE_URL` env var
- State management: TanStack Query (server state)"""


def _claude_ios() -> str:
    return """## iOS

- SwiftUI with MVVM pattern
- Async/await networking
- iOS 17+ minimum deployment target"""


def _claude_docker_services(project: DetectedProject) -> str:
    parts = ["## Docker Services", "", "- `db`: PostgreSQL 17"]
    if project.use_redis:
        parts.append("- `redis`: Redis 7")
    parts.append("- `api-dev`: Django dev server (when using Docker)")
    if project.use_celery:
        parts.append("- `celery-worker`, `celery-beat`: Celery (profile: celery)")
    return "\n".join(parts)


def _claude_mattstack() -> str:
    return """## mattstack Integration

This project was scaffolded with `mattstack`. The CLI provides unified commands:
- `mattstack dev` — Start all services (Docker + backend + frontend)
- `mattstack test` — Run all tests
- `mattstack lint` — Lint all code
- `mattstack env check` — Compare .env files
- `mattstack audit` — Static analysis (quality, types, endpoints, tests, dependencies)"""


def generate_cursorrules_from_detected(project: DetectedProject) -> str:
    """Generate .cursorrules from detected project state."""
    lines = [
        "# Project Rules for Cursor",
        "",
        "## Package Managers",
        f"- Python: use `{project.python_pm}` (NEVER pip/poetry)",
        f"- JavaScript: use `{project.js_pm}` (NEVER npm/yarn)",
        "",
        "## Development",
    ]
    if project.has_backend:
        lines.append("- Docker Compose for infrastructure: `docker compose up -d`")
    lines.extend(
        [
            "- Use `mattstack dev` to start all services",
            "- Use `mattstack test` to run tests",
            "- Use `mattstack lint` to lint code",
            "- Use `mattstack audit` for static analysis",
            "",
        ]
    )
    if project.has_backend:
        lines.extend(
            [
                "## Backend",
                "- django-ninja for API (Pydantic models, type-safe)",
                "- NEVER use Django REST Framework serializers",
                "- Run migrations after model changes: `cd backend && uv run python manage.py makemigrations && uv run python manage.py migrate`",
                "",
            ]
        )
    if project.has_frontend:
        lines.extend(
            [
                "## Frontend",
                "- TypeScript strict mode",
                "- Use `bun run dev` for development",
                "",
            ]
        )
    lines.extend(
        [
            "## Code Style",
            "- Type hints on every Python function",
            "- Strict TypeScript",
            "",
        ]
    )
    return "\n".join(lines)


def run_rules(
    path: Path,
    gsd: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Generate/update AI agent configuration files."""
    path = path.resolve()
    if not path.is_dir():
        print_error(f"Directory not found: {path}")
        raise typer.Exit(code=1)

    project = detect_project(path)

    files_to_write: list[tuple[Path, str, str]] = []

    files_to_write.append(
        (
            path / "CLAUDE.md",
            generate_claude_md_from_detected(project),
            "AI agent context (Claude Code, Cursor)",
        )
    )
    files_to_write.append(
        (
            path / ".cursorrules",
            generate_cursorrules_from_detected(project),
            "Cursor IDE agent rules",
        )
    )

    if gsd:
        from mattstack.templates.gsd_project import (
            generate_gsd_config_json_static,
            generate_gsd_project_md_from_detected,
            generate_gsd_state_md_from_detected,
        )

        planning_dir = path / ".planning"
        files_to_write.append(
            (
                planning_dir / "PROJECT.md",
                generate_gsd_project_md_from_detected(project),
                "GSD project definition",
            )
        )
        files_to_write.append(
            (
                planning_dir / "STATE.md",
                generate_gsd_state_md_from_detected(project),
                "GSD project state",
            )
        )
        files_to_write.append(
            (
                planning_dir / "config.json",
                generate_gsd_config_json_static(),
                "GSD configuration",
            )
        )

    if dry_run:
        console.print()
        console.print("[bold cyan]mattstack rules --dry-run[/bold cyan]")
        console.print()
        for file_path, _, desc in files_to_write:
            rel = file_path.relative_to(path)
            status = "overwrite" if file_path.exists() else "create"
            console.print(f"  [{status}] {rel} — {desc}")
        return

    console.print()
    console.print("[bold cyan]mattstack rules[/bold cyan]")
    console.print()

    for file_path, content, _desc in files_to_write:
        rel = file_path.relative_to(path)
        if file_path.exists() and not force:
            print_info(f"Skipping {rel} (exists, use --force to overwrite)")
            continue
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        print_success(f"Generated {rel}")

    if gsd:
        print_info("GSD files created in .planning/")
        print_info("Run /gsd:new-project in Claude Code to start planning")


HARNESS_ADAPTERS: dict[str, str] = {
    "claude": ".claude/CLAUDE.md",
    "cursor": ".cursor/.cursorrules",
    "windsurf": ".windsurf/rules.md",
    "kiro": ".kiro/rules.md",
    "continue": ".continue/README.md",
    "agents": ".agents/AGENTS.md",
}

CANONICAL_DIRS: tuple[str, ...] = (".omp", ".context")

_GENERATED_HEADER = (
    "<!-- Generated by `mattstack rules sync` from canonical .omp/ + .context/. "
    "Do not edit; regenerate instead. -->"
)


def collect_canonical(path: Path) -> str:
    """Concatenate all ``.md`` files in ``.omp/`` and ``.context/`` in order."""
    chunks: list[str] = []
    for rel in CANONICAL_DIRS:
        directory = path / rel
        if not directory.is_dir():
            continue
        for file in sorted(directory.glob("*.md")):
            chunks.append(f"<!-- {rel}/{file.name} -->\n\n{file.read_text(encoding='utf-8')}")
    return "\n\n".join(chunks)


def render_adapter(canonical: str) -> str:
    """Wrap canonical content with the generated-file header."""
    return f"{_GENERATED_HEADER}\n\n{canonical}\n"


def sync_harness_rules(path: Path, *, dry_run: bool = False, force: bool = False) -> list[Path]:
    """Regenerate per-harness adapters from canonical ``.omp/`` + ``.context/``.

    Returns the list of adapter files written.
    """
    path = path.resolve()
    if not path.is_dir():
        print_error(f"Directory not found: {path}")
        raise typer.Exit(code=1)

    canonical = collect_canonical(path)
    if not canonical.strip():
        print_error(f"No canonical rule files in {path}/.omp/ or {path}/.context/")
        raise typer.Exit(code=1)

    content = render_adapter(canonical)
    written: list[Path] = []

    console.print()
    console.print("[bold cyan]mattstack rules sync[/bold cyan]")
    console.print()

    for harness, rel in HARNESS_ADAPTERS.items():
        target = path / rel
        if dry_run:
            status = "overwrite" if target.exists() else "create"
            console.print(f"  [{status}] {rel} ({harness})")
            continue
        if target.exists() and not force:
            print_info(f"Skipping {rel} (exists, use --force to overwrite)")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(target)
        print_success(f"Synced {rel}")

    return written


rules_app = typer.Typer(
    name="rules",
    help="Generate AI agent config files and sync per-harness adapters.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    invoke_without_command=True,
)


@rules_app.callback()
def _rules_callback(
    ctx: typer.Context,
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
    gsd: Annotated[
        bool, typer.Option("--gsd", help="Also generate GSD planning files (.planning/)")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview what would be generated")
    ] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing files")] = False,
) -> None:
    """Generate AI agent config files when invoked without a subcommand."""
    if ctx.invoked_subcommand is None:
        run_rules(path=path or Path.cwd(), gsd=gsd, dry_run=dry_run, force=force)


@rules_app.command("sync")
def sync(
    path: Annotated[Path | None, typer.Option("--path", "-p", help="Project path")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview what would be written")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing adapter files")
    ] = False,
) -> None:
    """Regenerate per-harness adapters from canonical .omp/ + .context/ files."""
    sync_harness_rules(path=path or Path.cwd(), dry_run=dry_run, force=force)
