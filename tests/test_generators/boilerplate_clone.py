"""Boilerplate files a mocked clone needs for the runtime post-processors.

``prepare_runtime`` patches ``api/settings/prod.py`` and validates the health
routes of every new Ninja project, so a clone without them fails generation.
The sources are the ones ``tests/test_tls_health.py`` asserts the anchors on.
"""

from __future__ import annotations

from pathlib import Path

from test_tls_health import HEALTHCHECK, PROD, URLS


def write_ninja_settings(dest: Path) -> None:
    """Write the settings files the USE_TLS health-route patch edits."""
    settings = dest / "api" / "settings"
    settings.mkdir(parents=True, exist_ok=True)
    (settings / "prod.py").write_text(PROD, encoding="utf-8")
    (dest / "api" / "healthcheck.py").write_text(HEALTHCHECK, encoding="utf-8")
    (dest / "api" / "urls.py").write_text(URLS, encoding="utf-8")
