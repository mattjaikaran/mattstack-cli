"""Serialise package.json the way the frontend formatter canonicalises it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEPENDENCY_SECTIONS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)


def write_package_json(path: Path, data: dict[str, Any]) -> None:
    """Write ``data`` with dependency names sorted, so ``bun run format`` is a no-op.

    Oxfmt sorts each dependency section; appending a tool leaves a file that the
    first ``just setup`` rewrites. Sorting here keeps the initial commit clean.
    """
    for section in _DEPENDENCY_SECTIONS:
        entries = data.get(section)
        if isinstance(entries, dict):
            data[section] = {name: entries[name] for name in sorted(entries)}
    path.write_text(json.dumps(data, indent=2) + "\n")
