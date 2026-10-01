"""Tests for endpoint auditor."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from mattstack.auditors.base import AuditConfig, AuditFinding, Severity
from mattstack.auditors.endpoints import EndpointAuditor


def _make_config(path: Path, **kwargs) -> AuditConfig:
    return AuditConfig(project_path=path, **kwargs)


def test_finds_no_routes(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    auditor = EndpointAuditor(_make_config(tmp_path))
    findings = auditor.run()
    assert any("No route definitions" in f.message for f in findings)


def test_finds_duplicate_routes(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "from ninja import Router\n"
        "router = Router()\n\n"
        '@router.get("/users")\n'
        "def list_users(request): return []\n\n"
        '@router.get("/users")\n'
        "def list_users_v2(request): return []\n"
    )
    auditor = EndpointAuditor(_make_config(tmp_path))
    findings = auditor.run()
    dup_findings = [f for f in findings if "Duplicate" in f.message]
    assert len(dup_findings) >= 1


def test_finds_stub_endpoints(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "from ninja import Router\n"
        "router = Router()\n\n"
        '@router.get("/stub")\n'
        "def stub_endpoint(request):\n"
        "    pass\n"
    )
    auditor = EndpointAuditor(_make_config(tmp_path))
    findings = auditor.run()
    stub_findings = [f for f in findings if "Stub" in f.message]
    assert len(stub_findings) >= 1


def test_finds_missing_auth(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "from ninja import Router\n"
        "router = Router()\n\n"
        '@router.post("/users")\n'
        "def create_user(request): return {}\n"
    )
    auditor = EndpointAuditor(_make_config(tmp_path))
    findings = auditor.run()
    auth_findings = [f for f in findings if "No auth" in f.message]
    assert len(auth_findings) >= 1


def test_auth_endpoint_no_warning(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "from ninja import Router\n"
        "router = Router()\n\n"
        '@router.post("/users", auth=Bearer)\n'
        "def create_user(request): return {}\n"
    )
    auditor = EndpointAuditor(_make_config(tmp_path))
    findings = auditor.run()
    auth_findings = [f for f in findings if "No auth" in f.message]
    assert len(auth_findings) == 0


def test_trailing_slash_warning(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "from ninja import Router\n"
        "router = Router()\n\n"
        '@router.get("/users/")\n'
        "def list_users(request): return []\n"
    )
    auditor = EndpointAuditor(_make_config(tmp_path))
    findings = auditor.run()
    slash_findings = [f for f in findings if "Trailing slash" in f.message]
    assert len(slash_findings) >= 1


# ---------------------------------------------------------------------------
# _live_probe tests
# ---------------------------------------------------------------------------

_GET_ROUTE_FILE = (
    "from ninja import Router\n"
    "router = Router()\n\n"
    '@router.get("/health")\n'
    'def health_check(request): return {"ok": True}\n'
)

_POST_ROUTE_FILE = (
    "from ninja import Router\n"
    "router = Router()\n\n"
    '@router.post("/users")\n'
    "def create_user(request): return {}\n"
)

_PARAM_ROUTE_FILE = (
    "from ninja import Router\n"
    "router = Router()\n\n"
    '@router.get("/users/{id}")\n'
    "def get_user(request, id: int): return {}\n"
)


@dataclass
class _ProbeServer:
    url: str
    status: int = 200
    hits: list[str] = field(default_factory=list)


@pytest.fixture
def probe_server() -> Iterator[_ProbeServer]:
    """Real local HTTP server that answers every GET with a configurable status."""
    state = _ProbeServer(url="")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            state.hits.append(self.path)
            self.send_response(state.status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield state
    server.shutdown()
    server.server_close()


def _probe(tmp_path: Path, route_file: str, base_url: str) -> list[AuditFinding]:
    (tmp_path / "api.py").write_text(route_file)
    return EndpointAuditor(_make_config(tmp_path, live=True, base_url=base_url)).run()


@pytest.mark.parametrize(
    ("status", "severity"), [(500, Severity.ERROR), (503, Severity.ERROR), (404, Severity.WARNING)]
)
def test_live_probe_reports_error_statuses(
    tmp_path: Path, probe_server: _ProbeServer, status: int, severity: Severity
) -> None:
    probe_server.status = status
    findings = _probe(tmp_path, _GET_ROUTE_FILE, probe_server.url)

    probe_findings = [f for f in findings if f"returned {status}" in f.message]
    assert len(probe_findings) == 1
    assert probe_findings[0].severity == severity
    assert probe_server.hits == ["/health"]


def test_live_probe_quiet_on_success(tmp_path: Path, probe_server: _ProbeServer) -> None:
    findings = _probe(tmp_path, _GET_ROUTE_FILE, probe_server.url)

    assert not [f for f in findings if "Live probe" in f.message]
    assert probe_server.hits == ["/health"]


def test_live_probe_server_unreachable(tmp_path: Path) -> None:
    """Live probe reports INFO when nothing listens on the base URL."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    findings = _probe(tmp_path, _GET_ROUTE_FILE, f"http://127.0.0.1:{port}")

    probe_findings = [f for f in findings if "Could not reach" in f.message]
    assert len(probe_findings) == 1
    assert probe_findings[0].severity == Severity.INFO


@pytest.mark.parametrize("base_url", ["file:///etc/passwd", "ftp://127.0.0.1", "localhost:8000"])
def test_live_probe_rejects_non_http_base_url(tmp_path: Path, base_url: str) -> None:
    findings = _probe(tmp_path, _GET_ROUTE_FILE, base_url)

    invalid = [f for f in findings if "Invalid base URL" in f.message]
    assert len(invalid) == 1
    assert invalid[0].severity == Severity.WARNING
    assert not [f for f in findings if "Live probe" in f.message]


@pytest.mark.parametrize("route_file", [_POST_ROUTE_FILE, _PARAM_ROUTE_FILE])
def test_live_probe_skips_non_get_and_parameterized(
    tmp_path: Path, probe_server: _ProbeServer, route_file: str
) -> None:
    """Live probe only sends GETs to concrete paths."""
    _probe(tmp_path, route_file, probe_server.url)

    assert probe_server.hits == []
