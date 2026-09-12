"""Gauntlet integration: mattstack's verification engine boundary.

Gauntlet owns every check. MattStack owns the scaffold, the project
configuration, and the presentation of findings.

- `models`  — typed models for the Gauntlet JSON contract.
- `client`  — subprocess boundary and `gauntlet.toml` caller settings.
- `init`    — generates `gauntlet.toml` for a scaffolded project.
- `report`  — renders findings for the terminal, JSON, and HTML.
"""

from __future__ import annotations

from mattstack.gauntlet.client import (
    DEFAULT_TIER,
    GauntletConfig,
    GauntletError,
    GauntletUnavailableError,
    check,
    find_config_file,
    load_config,
    resolve_binary,
)
from mattstack.gauntlet.init import CONFIG_FILENAME, generate_config, write_config
from mattstack.gauntlet.models import (
    ENGINES,
    SUPPORTED_SCHEMA_VERSION,
    CheckStatus,
    Finding,
    RunResult,
    RunStatus,
    SchemaError,
    Severity,
)

__all__ = [
    "CONFIG_FILENAME",
    "DEFAULT_TIER",
    "ENGINES",
    "SUPPORTED_SCHEMA_VERSION",
    "CheckStatus",
    "Finding",
    "GauntletConfig",
    "GauntletError",
    "GauntletUnavailableError",
    "RunResult",
    "RunStatus",
    "SchemaError",
    "Severity",
    "check",
    "find_config_file",
    "generate_config",
    "load_config",
    "resolve_binary",
    "write_config",
]
