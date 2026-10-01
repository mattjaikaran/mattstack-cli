"""Opt-in route behavior shared by `generate page` and `generate crud`."""

from __future__ import annotations

from dataclasses import dataclass

from mattstack.commands.codegen.backend_layout import GenerateError
from mattstack.parsers.frontend_layout import FrontendLayout

GUARD_NOTICE = (
    "The route guard only redirects signed-out users in the browser. "
    "It is not authorization: the API must enforce access to the data."
)


@dataclass(frozen=True)
class RouteOptions:
    """Extra route wiring; every flag defaults to off."""

    guard: bool = False  # TanStack: beforeLoad redirect using the app's auth store
    pending: bool = False  # TanStack: loader-backed pendingComponent (CRUD only)
    error: bool = False  # TanStack errorComponent; React Router data-router ErrorBoundary
    lazy: bool = False  # React Router data router: register with `lazy: () => import()`


DEFAULT_ROUTE_OPTIONS = RouteOptions()


def is_data_router(layout: FrontendLayout) -> bool:
    """True when routes go through createBrowserRouter/createHashRouter/createMemoryRouter."""
    source = layout.route_source
    return source is not None and source.call is not None and source.call != "useRoutes"


def check_route_options(
    layout: FrontendLayout, options: RouteOptions, *, has_loader: bool = False
) -> None:
    """Refuse flags the detected router cannot honor; nothing is planned yet.

    *has_loader* is True when the generated route loads data (CRUD list pages),
    which is what makes a pending component render.
    """
    router = layout.router
    if options.guard and router != "tanstack":
        hint = " Use --route-group protected instead." if router == "react-router" else ""
        raise GenerateError(f"--guard applies to TanStack Router, not {router}.{hint}")
    if options.pending:
        if router != "tanstack":
            raise GenerateError(
                f"--pending applies to TanStack Router loaders, not {router}. "
                "React Router has no per-route pending component; use useNavigation()."
            )
        if not has_loader:
            raise GenerateError(
                "--pending needs a route loader, and a generated page has none: the pending "
                "component would never render. Use `mattstack generate crud --pending`, or "
                "add a loader to the page by hand."
            )
    where = f"{router} with JSX <Routes>" if router == "react-router" else router
    if layout.route_source is not None and layout.route_source.call == "useRoutes":
        where = "React Router useRoutes() inside a declarative router"
    data_router = is_data_router(layout)
    if options.error and router != "tanstack" and not data_router:
        raise GenerateError(
            "--error needs TanStack Router or a React Router data router "
            f"(createBrowserRouter); this frontend uses {where}, which ignores errorElement."
        )
    if options.lazy and not data_router:
        raise GenerateError(
            "--lazy needs a React Router data router (createBrowserRouter); "
            f"this frontend uses {where}, which ignores route `lazy`."
        )
