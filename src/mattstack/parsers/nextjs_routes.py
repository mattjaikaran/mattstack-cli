"""Parse Next.js App Router routes from filesystem structure and route handlers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from mattstack.parsers.frontend_layout import package_dependencies


@dataclass
class NextjsRoute:
    route_type: str  # "page" or "api"
    path: str  # e.g. "/dashboard", "/api/users"
    file: Path
    methods: list[str]  # ["GET"] for pages, ["GET", "POST", ...] for API routes
    has_auth: bool = False
    is_stub: bool = False
    has_loading: bool = False
    has_error: bool = False
    has_layout: bool = False


# HTTP method exports in route.ts files: export async function GET(...)
METHOD_EXPORT_RE = re.compile(
    r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\(",
    re.MULTILINE,
)

# Arrow function exports: export const GET = async (...)
METHOD_ARROW_RE = re.compile(
    r"export\s+const\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*=",
    re.MULTILINE,
)

# Auth patterns in Next.js: middleware auth, getServerSession, auth(), cookies()
AUTH_PATTERNS = re.compile(
    r"(?:getServerSession|auth\(\)|cookies\(\)|getToken|withAuth|middleware|"
    r"NextAuth|authOptions|session\s*=|currentUser)",
    re.IGNORECASE,
)

# Stub patterns for route handlers
STUB_RE = re.compile(
    r"(?:return\s+(?:new\s+)?(?:Response|NextResponse)\.json\(\s*\{\s*\}\s*\)"
    r"|throw\s+new\s+Error\(['\"]Not implemented"
    r"|//\s*TODO"
    r"|return\s+(?:new\s+)?(?:Response|NextResponse)\.json\(\s*\{\s*"
    r"(?:message|msg)\s*:\s*['\"](?:todo|not implemented|placeholder))",
    re.IGNORECASE,
)


def _dir_to_route_path(app_dir: Path, file_path: Path) -> str:
    """Convert a file path relative to app/ into a URL route path.

    Examples:
        app/page.tsx -> /
        app/dashboard/page.tsx -> /dashboard
        app/api/users/route.ts -> /api/users
        app/users/[id]/page.tsx -> /users/[id]
        app/(auth)/login/page.tsx -> /login  (groups are stripped)
    """
    rel = file_path.parent.relative_to(app_dir)
    parts = []
    for part in rel.parts:
        if part.startswith("(") and part.endswith(")"):
            continue
        parts.append(part)

    route = "/" + "/".join(parts) if parts else "/"
    return route


def parse_nextjs_routes(app_dir: Path) -> list[NextjsRoute]:
    """Parse all routes from a Next.js App Router directory."""
    routes: list[NextjsRoute] = []

    if not app_dir.exists():
        return routes

    # Find page files (page.tsx, page.ts, page.jsx, page.js)
    for page_file in app_dir.rglob("page.*"):
        if page_file.suffix not in (".tsx", ".ts", ".jsx", ".js"):
            continue
        if "node_modules" in page_file.parts:
            continue

        route_path = _dir_to_route_path(app_dir, page_file)
        page_dir = page_file.parent

        routes.append(
            NextjsRoute(
                route_type="page",
                path=route_path,
                file=page_file,
                methods=["GET"],
                has_loading=(page_dir / "loading.tsx").exists()
                or (page_dir / "loading.ts").exists(),
                has_error=(page_dir / "error.tsx").exists() or (page_dir / "error.ts").exists(),
                has_layout=(page_dir / "layout.tsx").exists() or (page_dir / "layout.ts").exists(),
            )
        )

    # Find API route files (route.ts, route.tsx, route.js)
    for route_file in app_dir.rglob("route.*"):
        if route_file.suffix not in (".ts", ".tsx", ".js", ".jsx"):
            continue
        if "node_modules" in route_file.parts:
            continue

        route_path = _dir_to_route_path(app_dir, route_file)
        text = route_file.read_text(encoding="utf-8", errors="replace")

        methods: list[str] = []
        for pattern in (METHOD_EXPORT_RE, METHOD_ARROW_RE):
            for match in pattern.finditer(text):
                method = match.group(1).upper()
                if method not in methods:
                    methods.append(method)

        if not methods:
            methods = ["GET"]

        has_auth = bool(AUTH_PATTERNS.search(text))
        is_stub = bool(STUB_RE.search(text))

        routes.append(
            NextjsRoute(
                route_type="api",
                path=route_path,
                file=route_file,
                methods=methods,
                has_auth=has_auth,
                is_stub=is_stub,
            )
        )

    return routes


def find_nextjs_app_dirs(project_path: Path) -> list[Path]:
    """Find the App Router directory of each package that depends on ``next``.

    Vite and Rsbuild SPAs often keep components in ``src/app``; without the
    ``next`` dependency those files are not Next.js pages or route handlers.
    Next.js ignores ``src/app`` when ``app`` exists, so return only the first.
    """
    dirs: list[Path] = []
    for package_root in (project_path / "frontend", project_path):
        if "next" not in package_dependencies(package_root):
            continue
        app_dir = next(
            (d for d in (package_root / "app", package_root / "src" / "app") if d.is_dir()), None
        )
        if app_dir is not None:
            dirs.append(app_dir)
    return dirs
