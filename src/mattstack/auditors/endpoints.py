"""Endpoint auditor — static route analysis + optional live probing."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import httpx

from mattstack.auditors.base import AuditFinding, AuditType, BaseAuditor, Severity
from mattstack.parsers.django_routes import (
    DjangoMattController,
    Route,
    find_django_matt_controller_files,
    find_route_files,
    is_django_matt_project,
    parse_django_matt_controller_file,
    parse_routes_file,
)
from mattstack.parsers.nextjs_routes import (
    NextjsRoute,
    find_nextjs_app_dirs,
    parse_nextjs_routes,
)


class EndpointAuditor(BaseAuditor):
    audit_type = AuditType.ENDPOINTS

    def run(self) -> list[AuditFinding]:
        project = self.config.project_path
        routes = self._parse_all_routes(project)
        matt_controllers = self._parse_django_matt_controllers(project)
        nextjs_routes = self._parse_nextjs_routes(project)

        if not routes and not matt_controllers and not nextjs_routes:
            self.add_finding(
                Severity.INFO,
                Path("."),
                0,
                "No route definitions found",
                "Routes are expected in api.py, routes.py, controllers.py, "
                "or Next.js app/api/ directory.",
            )
            return self.findings

        if routes:
            self._check_duplicates(routes)
            self._check_stubs(routes)
            self._check_auth(routes)
            self._check_naming(routes)

        if matt_controllers:
            self._check_django_matt_controllers(matt_controllers)

        if nextjs_routes:
            self._check_nextjs_api_routes(nextjs_routes)

        if self.config.live:
            self._live_probe(routes)

        return self.findings

    def _parse_all_routes(self, project: Path) -> list[Route]:
        routes: list[Route] = []
        for f in find_route_files(project):
            routes.extend(parse_routes_file(f))
        return routes

    def _parse_django_matt_controllers(self, project: Path) -> list[DjangoMattController]:
        if not is_django_matt_project(project):
            return []
        controllers: list[DjangoMattController] = []
        for f in find_django_matt_controller_files(project):
            controllers.extend(parse_django_matt_controller_file(f))
        return controllers

    def _parse_nextjs_routes(self, project: Path) -> list[NextjsRoute]:
        routes: list[NextjsRoute] = []
        for app_dir in find_nextjs_app_dirs(project):
            routes.extend(parse_nextjs_routes(app_dir))
        return routes

    def _check_django_matt_controllers(self, controllers: list[DjangoMattController]) -> None:
        """Audit django-matt APIController endpoints for auth and naming."""
        write_methods = {"POST", "PUT", "DELETE", "PATCH"}

        for ctrl in controllers:
            for ep in ctrl.endpoints:
                full_path = ctrl.prefix.rstrip("/") + "/" + ep.path.lstrip("/")

                if ep.method in write_methods and not ep.auth:
                    self.add_finding(
                        Severity.WARNING,
                        self._rel(ctrl.file),
                        ctrl.line,
                        f"No auth on write endpoint: {ep.method} {full_path} ({ep.handler})",
                        "Add auth=JWTAuth() to protect write operations",
                    )

                if not full_path.startswith("/"):
                    self.add_finding(
                        Severity.INFO,
                        self._rel(ctrl.file),
                        ctrl.line,
                        f"Route path missing leading slash: '{full_path}'",
                        f"Use '/{full_path}' for consistency",
                    )

    def _check_nextjs_api_routes(self, routes: list[NextjsRoute]) -> None:
        """Audit Next.js API routes for stubs and missing auth."""
        api_routes = [r for r in routes if r.route_type == "api"]
        write_methods = {"POST", "PUT", "DELETE", "PATCH"}

        for r in api_routes:
            if r.is_stub:
                self.add_finding(
                    Severity.WARNING,
                    self._rel(r.file),
                    1,
                    f"Stub API route: {', '.join(r.methods)} {r.path}",
                    "Implement the route handler",
                )

            has_write = any(m in write_methods for m in r.methods)
            if has_write and not r.has_auth:
                self.add_finding(
                    Severity.WARNING,
                    self._rel(r.file),
                    1,
                    f"No auth on write API route: {', '.join(r.methods)} {r.path}",
                    "Add authentication check (getServerSession, middleware, etc.)",
                )

        # Check for duplicate API paths
        path_counter: Counter[str] = Counter()
        for r in api_routes:
            path_counter[r.path] += 1
        for path, count in path_counter.items():
            if count > 1:
                self.add_finding(
                    Severity.ERROR,
                    Path("."),
                    0,
                    f"Duplicate Next.js API route: {path} defined {count} times",
                    "Remove duplicate route.ts files",
                )

    def _check_duplicates(self, routes: list[Route]) -> None:
        """Find duplicate method+path combinations."""
        counter: Counter[tuple[str, str]] = Counter()
        route_map: dict[tuple[str, str], list[Route]] = {}

        for r in routes:
            key = (r.method, r.path)
            counter[key] += 1
            route_map.setdefault(key, []).append(r)

        for key, count in counter.items():
            if count > 1:
                method, path = key
                dupes = route_map[key]
                files = ", ".join(f"{self._rel(r.file)}:{r.line}" for r in dupes)
                self.add_finding(
                    Severity.ERROR,
                    self._rel(dupes[0].file),
                    dupes[0].line,
                    f"Duplicate route: {method} {path} defined {count} times ({files})",
                    "Remove duplicate or use unique paths",
                )

    def _check_stubs(self, routes: list[Route]) -> None:
        """Find routes with stub implementations."""
        for r in routes:
            if r.is_stub:
                self.add_finding(
                    Severity.WARNING,
                    self._rel(r.file),
                    r.line,
                    f"Stub endpoint: {r.method} {r.path} ({r.function_name})",
                    "Implement the endpoint handler",
                )

    def _check_auth(self, routes: list[Route]) -> None:
        """Find write endpoints without explicit auth."""
        write_methods = {"POST", "PUT", "DELETE", "PATCH"}
        for r in routes:
            if r.method in write_methods and not r.has_auth:
                self.add_finding(
                    Severity.WARNING,
                    self._rel(r.file),
                    r.line,
                    f"No auth on write endpoint: {r.method} {r.path}",
                    "Add auth=... parameter to protect write operations",
                )

    def _check_naming(self, routes: list[Route]) -> None:
        """Check route naming conventions."""
        for r in routes:
            # Flag routes with no leading slash
            if not r.path.startswith("/"):
                self.add_finding(
                    Severity.INFO,
                    self._rel(r.file),
                    r.line,
                    f"Route path missing leading slash: '{r.path}'",
                    f"Use '/{r.path}' for consistency",
                )

            # Flag routes ending with slash inconsistency
            if r.path != "/" and r.path.endswith("/"):
                self.add_finding(
                    Severity.INFO,
                    self._rel(r.file),
                    r.line,
                    f"Trailing slash on route: '{r.path}'",
                    "Consider removing trailing slash for consistency",
                )

    def _live_probe(self, routes: list[Route]) -> None:
        """GET-probe discovered endpoints (safe, read-only)."""
        base_url = self.config.base_url

        with httpx.Client(timeout=5, follow_redirects=True) as client:
            for r in routes:
                if r.method != "GET":
                    continue

                url = f"{base_url}{r.path}"
                # Skip parameterized routes
                if "{" in url or "<" in url:
                    continue

                try:
                    status = client.get(url).status_code
                except (httpx.UnsupportedProtocol, httpx.InvalidURL) as exc:
                    self.add_finding(
                        Severity.WARNING,
                        Path("."),
                        0,
                        f"Invalid base URL {base_url}: {exc}",
                        "Pass an http:// or https:// URL to --base-url",
                    )
                    break
                except httpx.TransportError:
                    # Server not running or not reachable
                    self.add_finding(
                        Severity.INFO,
                        Path("."),
                        0,
                        f"Could not reach {base_url} — is the server running?",
                        "Start the backend with 'make backend-dev' before using --live",
                    )
                    break  # No point probing more
                except httpx.RequestError as exc:
                    self.add_finding(
                        Severity.WARNING,
                        self._rel(r.file),
                        r.line,
                        f"Live probe {r.method} {r.path} failed: {exc}",
                        "Check the route's redirects and response encoding",
                    )
                    continue

                if status >= 500:
                    self.add_finding(
                        Severity.ERROR,
                        self._rel(r.file),
                        r.line,
                        f"Live probe {r.method} {r.path} returned {status}",
                        "Check server logs for the error",
                    )
                elif status == 404:
                    self.add_finding(
                        Severity.WARNING,
                        self._rel(r.file),
                        r.line,
                        f"Live probe {r.method} {r.path} returned 404",
                        "Route may not be registered or server isn't running",
                    )
