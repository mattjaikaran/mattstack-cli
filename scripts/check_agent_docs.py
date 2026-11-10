#!/usr/bin/env python3
"""Check that the repository's agent docs keep AGENTS.md as the only source.

Rules:
    1. ``AGENTS.md`` exists and has every required ``## `` heading.
    2. ``CLAUDE.md`` exists and its first non-blank line is exactly ``@AGENTS.md``.
    3. Relative Markdown links and ``@path`` imports in ``AGENTS.md``,
       ``CLAUDE.md`` and ``CONTRIBUTING.md`` name existing paths.

Exit 0 on pass, 1 on failure.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_HEADINGS = (
    "Project overview",
    "Commands",
    "Code standards",
    "Testing policy",
    "Git and commits",
    "Spec workflow",
    "Security",
)
AGENT_DOCS = ("AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md")
POINTER = "@AGENTS.md"
LINK_TARGET = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
IMPORT_LINE = re.compile(r"^@(\S+)$")
SKIP_PREFIXES = ("http://", "https://", "mailto:")


def _unfenced_lines(text: str) -> list[str]:
    """Return the lines outside fenced code blocks."""
    lines: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        marker = line.strip()[:3]
        if marker in ("```", "~~~"):
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return lines


def _link_targets(text: str) -> list[tuple[str, str]]:
    """Return ``(line, target)`` for every link and ``@path`` import outside fences."""
    found: list[tuple[str, str]] = []
    for line in _unfenced_lines(text):
        found.extend((line, target) for target in LINK_TARGET.findall(line))
        import_line = IMPORT_LINE.match(line.strip())
        if import_line:
            found.append((line, import_line.group(1)))
    return found


def _relative_target(target: str) -> str | None:
    """Return the path a target names, or None when the target is not checkable."""
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = target.split()[0] if target else ""
    if not target or target.startswith("#") or target.startswith(SKIP_PREFIXES):
        return None
    return target.split("#", 1)[0]


def check(root: Path) -> list[str]:
    """Return one ``<file>: <problem>`` string per problem under ``root``."""
    problems: list[str] = []

    agents = root / "AGENTS.md"
    if not agents.is_file():
        problems.append("AGENTS.md: file is missing")
    else:
        headings = {
            line.strip()
            for line in _unfenced_lines(agents.read_text(encoding="utf-8"))
            if line.strip().startswith("## ")
        }
        for heading in REQUIRED_HEADINGS:
            if f"## {heading}" not in headings:
                problems.append(f"AGENTS.md: missing heading '## {heading}'")

    claude = root / "CLAUDE.md"
    if not claude.is_file():
        problems.append("CLAUDE.md: file is missing")
    else:
        lines = [
            line.strip() for line in claude.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        first = lines[0] if lines else ""
        if first != POINTER:
            problems.append(f"CLAUDE.md: first non-blank line is {first!r}, expected {POINTER!r}")

    for name in AGENT_DOCS:
        path = root / name
        if not path.is_file():
            continue
        for line, target in _link_targets(path.read_text(encoding="utf-8")):
            relative = _relative_target(target)
            if relative is not None and not (root / relative).exists():
                problems.append(f"{name}: {relative!r} does not exist (line: {line.strip()})")

    return problems


def main(argv: list[str] | None = None) -> int:
    """Check the repository root, or the root passed as the only argument."""
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]) if args else PROJECT_ROOT

    problems = check(root)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print("Agent docs check passed: AGENTS.md is the source and CLAUDE.md imports it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
