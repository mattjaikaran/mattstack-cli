"""Collect API routes with their mounted paths and declared contracts.

`parse_routes_file` reads decorators one file at a time and has no notion of
where a router or controller is mounted. Generated API clients need the full
path, so this module joins controller prefixes (ninja-extra
`@api_controller`, django-matt `prefix =`) and `add_router` mount prefixes,
and records the declared response and request body types.
"""

from __future__ import annotations

import re
from pathlib import Path

from mattstack.parsers.django_routes import Route, find_route_files
from mattstack.parsers.utils import find_files

_HTTP_METHODS = "get|post|put|delete|patch"

# @http_get( / @router.get( / @api.get( / @get(  — call opened, args parsed below
DECORATOR_RE = re.compile(
    rf"^[ \t]*@(?:(?P<owner>\w+)\.)?(?P<http>http_)?(?P<method>{_HTTP_METHODS})\s*\(",
    re.MULTILINE,
)
API_CONTROLLER_RE = re.compile(r"^@api_controller\s*\(", re.MULTILINE)
MATT_CONTROLLER_RE = re.compile(
    r"^class\s+(\w+)\s*\((?:[\w.]*\.)?(?:APIController|MattAPIController|MattController)\)",
    re.MULTILINE,
)
TOP_LEVEL_CLASS_RE = re.compile(r"^class\s+\w+", re.MULTILINE)
MATT_PREFIX_RE = re.compile(r"""^\s+prefix\s*=\s*['"]([^'"]*)['"]""", re.MULTILINE)
DEF_RE = re.compile(r"^[ \t]*(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE)
STRING_RE = re.compile(r"""^\s*(?:[rbuf]*)(['"])(.*?)\1""")
ADD_ROUTER_RE = re.compile(r"""\.add_router\s*\(\s*['"]([^'"]*)['"]\s*,\s*([\w.'"]+)""")
IMPORT_RE = re.compile(r"^from\s+([\w.]+)\s+import\s+(\([^)]*\)|.+)$", re.MULTILINE)
PATH_PARAM_RE = re.compile(r"<(?:\w+:)?(\w+)>|\{(?:\w+:)?(\w+)\}")
STUB_BODY_RE = re.compile(r"^\s*(?:pass|\.\.\.|raise NotImplementedError\b.*)\s*$")
REQUEST_PARAMS = frozenset({"self", "request", "cls"})
SCALAR_TYPES = frozenset({"str", "int", "float", "bool", "UUID", "date", "datetime", "Decimal"})
BODY_PARAM_NAMES = ("payload", "body", "data")


def _matching_paren(text: str, open_index: int) -> int:
    """Return the index of the bracket closing the one at *open_index*."""
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                return index
    return len(text) - 1


def split_args(args: str) -> list[str]:
    """Split call or signature arguments at bracket depth zero."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in args:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def _call_args(text: str, open_index: int) -> tuple[list[str], int]:
    close = _matching_paren(text, open_index)
    return split_args(text[open_index + 1 : close]), close


def _keyword(args: list[str], name: str) -> str | None:
    for arg in args:
        key, sep, value = arg.partition("=")
        if sep and key.strip() == name:
            return value.strip()
    return None


def _string_arg(args: list[str]) -> str | None:
    if not args or "=" in args[0].split("(")[0].split("[")[0]:
        return None
    match = STRING_RE.match(args[0])
    return match.group(2) if match else None


def join_path(prefix: str, path: str) -> str:
    """Join a mount prefix and an endpoint path the way Ninja and django-matt do."""
    path = PATH_PARAM_RE.sub(lambda m: "{" + (m.group(1) or m.group(2)) + "}", path)
    prefix = PATH_PARAM_RE.sub(lambda m: "{" + (m.group(1) or m.group(2)) + "}", prefix).strip()
    if not prefix or prefix == "/":
        joined = path or "/"
    elif not path:
        joined = prefix
    else:
        joined = prefix.rstrip("/") + "/" + path.lstrip("/")
        if path == "/":
            joined = prefix.rstrip("/") + "/"
    joined = re.sub(r"/{2,}", "/", joined)
    return joined if joined.startswith("/") else "/" + joined


def _function_after(text: str, start: int) -> tuple[str, list[str], str | None, bool, int] | None:
    """Return (name, params, return annotation, is_stub, def offset) for the next def."""
    match = DEF_RE.search(text, start)
    if not match:
        return None
    params, close = _call_args(text, match.end() - 1)
    header, _, after = text[close + 1 :].partition("\n")
    header = header.split("#", 1)[0].strip()
    returns = header[2:].rstrip(":").strip() if header.startswith("->") else None
    body = re.sub(r'(?s)^\s*(?:"""|\'\'\').*?(?:"""|\'\'\')', "", after, count=1)
    first = next(
        (
            line.strip()
            for line in body.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ),
        "",
    )
    is_stub = bool(STUB_BODY_RE.match(first))
    return match.group(1), params, returns, is_stub, match.start()


def _body_type(params: list[str], path: str) -> str | None:
    path_params = set(re.findall(r"\{(\w+)\}", path))
    candidates: list[tuple[str, str]] = []
    for param in params:
        name, _, annotation = param.partition(":")
        name = name.strip().lstrip("*")
        annotation = annotation.split("=", 1)[0].strip()
        if not annotation or name in REQUEST_PARAMS or name in path_params:
            continue
        base = annotation.split("[", 1)[0].rsplit(".", 1)[-1]
        if base in SCALAR_TYPES or base in ("Query", "Path", "Header", "Cookie", "list", "dict"):
            continue
        if base == "Body":
            inner = annotation[annotation.find("[") + 1 : annotation.rfind("]")]
            annotation = split_args(inner)[0] if inner else annotation
        candidates.append((name, annotation))
    for preferred in BODY_PARAM_NAMES:
        for name, annotation in candidates:
            if name == preferred:
                return annotation
    return candidates[0][1] if candidates else None


def _decorator_block(text: str, match_start: int, def_start: int) -> str:
    """Return every decorator line stacked on the function at *def_start*."""
    block_start = match_start
    while block_start > 0:
        prev_end = text.rfind("\n", 0, block_start - 1)
        line = text[prev_end + 1 : block_start - 1]
        if not line.strip().startswith("@"):
            break
        block_start = prev_end + 1
    return text[block_start:def_start]


def route_owners(text: str) -> frozenset[str]:
    """Names ninja-extra's `route` object is bound to (`@route.get(...)`)."""
    owners = {"route"}
    for names in re.findall(r"^from\s+ninja_extra\s+import\s+(\([^)]*\)|.+)$", text, re.MULTILINE):
        for item in names.strip("()\n ").split(","):
            original, _, alias = item.split("#", 1)[0].strip().partition(" as ")
            if original.strip() == "route" and alias.strip():
                owners.add(alias.strip())
    return frozenset(owners)


def _routes_in(
    text: str,
    path: Path,
    span: tuple[int, int],
    prefix: str,
    controller: bool,
    controller_auth: bool = False,
    owners: frozenset[str] = frozenset(),
) -> list[Route]:
    """Parse route decorators inside *span* under *prefix*.

    Inside a controller, bare decorators (`@http_get`, `@get`) and those on an
    allowed owner (`@route.get` in ninja-extra) are routes; `@router.get` is not.
    Outside one, owner decorators (`@router.get`, `@api.get`) and `@http_*` are.
    """
    routes: list[Route] = []
    for match in DECORATOR_RE.finditer(text, *span):
        owner, is_http = match.group("owner"), bool(match.group("http"))
        if controller and owner and owner not in owners:
            continue
        if not controller and not owner and not is_http:
            continue
        args, close = _call_args(text, match.end() - 1)
        route_path = _string_arg(args)
        if route_path is None:
            continue
        details = _function_after(text, close)
        if details is None:
            continue
        name, params, returns, is_stub, def_start = details
        full_path = join_path(prefix, route_path)
        response = _keyword(args, "response") or _keyword(args, "response_model") or returns
        auth = _keyword(args, "auth")
        has_auth = controller_auth if auth is None else auth not in ("None", "False")
        decorators = _decorator_block(text, match.start(), def_start)
        has_auth = has_auth or "@jwt_required" in decorators
        paginator = re.search(r"@paginate\s*\(\s*([\w.]+)", decorators)
        routes.append(
            Route(
                method=match.group("method").upper(),
                path=full_path,
                function_name=name,
                file=path,
                line=text[: match.start()].count("\n") + 1,
                has_auth=has_auth,
                is_stub=is_stub,
                response=response,
                body_type=_body_type(params, full_path),
                pagination=paginator.group(1).rsplit(".", 1)[-1] if paginator else None,
            )
        )
    return routes


def _class_end(text: str, start: int) -> int:
    nxt = TOP_LEVEL_CLASS_RE.search(text, start)
    return nxt.start() if nxt else len(text)


def parse_api_file(path: Path, mount_prefix: str = "") -> list[Route]:
    """Parse every route in *path*, joining controller and mount prefixes."""
    text = path.read_text(encoding="utf-8", errors="replace")
    routes: list[Route] = []
    covered: list[tuple[int, int]] = []

    for match in API_CONTROLLER_RE.finditer(text):
        args, close = _call_args(text, match.end() - 1)
        prefix = _string_arg(args) or ""
        auth = _keyword(args, "auth")
        class_match = TOP_LEVEL_CLASS_RE.search(text, close)
        if not class_match:
            continue
        end = _class_end(text, class_match.end())
        covered.append((match.start(), end))
        routes.extend(
            _routes_in(
                text,
                path,
                (class_match.end(), end),
                join_path(mount_prefix, prefix),
                True,
                controller_auth=bool(auth and auth not in ("None", "False")),
                owners=route_owners(text),
            )
        )

    for match in MATT_CONTROLLER_RE.finditer(text):
        end = _class_end(text, match.end())
        covered.append((match.start(), end))
        prefix_match = MATT_PREFIX_RE.search(text, match.end(), end)
        prefix = prefix_match.group(1) if prefix_match else ""
        routes.extend(
            _routes_in(text, path, (match.end(), end), join_path(mount_prefix, prefix), True)
        )

    cursor = 0
    for start, end in sorted(covered) + [(len(text), len(text))]:
        routes.extend(_routes_in(text, path, (cursor, start), mount_prefix, False))
        cursor = max(cursor, end)
    return routes


def _module_file(backend_dir: Path, module: str, importer: Path) -> Path | None:
    if module.startswith("."):
        level = len(module) - len(module.lstrip("."))
        base_dir = importer.parent
        for _ in range(level - 1):
            base_dir = base_dir.parent
        parts = [p for p in module.lstrip(".").split(".") if p]
        base = base_dir.joinpath(*parts) if parts else base_dir
    else:
        base = backend_dir.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def router_mounts(backend_dir: Path) -> dict[Path, str]:
    """Map router module files to the prefix passed to `add_router`."""
    mounts: dict[Path, str] = {}
    for f in find_files(backend_dir, ["**/*.py"]):
        text = f.read_text(encoding="utf-8", errors="replace")
        if ".add_router" not in text:
            continue
        imported: dict[str, str] = {}
        for module, names in IMPORT_RE.findall(text):
            for item in names.strip("()\n ").split(","):
                original, _, alias = item.split("#", 1)[0].strip().partition(" as ")
                if original:
                    sep = "" if module.endswith(".") else "."
                    imported[(alias or original).strip()] = f"{module}{sep}{original.strip()}"
        for prefix, raw_target in ADD_ROUTER_RE.findall(text):
            target = raw_target.strip("'\"")
            head, _, tail = target.partition(".")
            dotted = imported.get(head, head) + (f".{tail}" if tail else "")
            module = dotted.rsplit(".", 1)[0] if "." in dotted.lstrip(".") else dotted
            module_file = _module_file(backend_dir, module, f) or _module_file(
                backend_dir, dotted, f
            )
            if module_file is not None:
                mounts[module_file.resolve()] = prefix
    return mounts


def collect_api_routes(backend_dir: Path) -> list[Route]:
    """Collect every route under *backend_dir* with its full mounted path."""
    files = {
        *find_route_files(backend_dir),
        *find_files(backend_dir, ["**/controllers/*.py", "**/controllers.py", "**/api/*.py"]),
    }
    mounts = router_mounts(backend_dir)
    routes: list[Route] = []
    seen: set[tuple[str, str]] = set()
    for f in sorted(files):
        for route in parse_api_file(f, mounts.get(f.resolve(), "")):
            key = (route.method, route.path)
            if key in seen:
                continue
            seen.add(key)
            routes.append(route)
    return routes
