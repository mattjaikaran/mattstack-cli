"""Plan generated writes, refuse overwrites, then apply in one step."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from mattstack.utils.console import console


@dataclass
class FilePlan:
    """New files and edits to existing files, collected before any write."""

    root: Path
    creates: dict[Path, str] = field(default_factory=dict)
    updates: dict[Path, str] = field(default_factory=dict)

    def create(self, path: Path, content: str) -> None:
        self.creates[path] = content

    def ensure_package(self, directory: Path) -> None:
        init = directory / "__init__.py"
        if not init.exists() and init not in self.creates:
            self.creates[init] = ""

    def text(self, path: Path) -> str:
        """Content *path* will have once applied: planned, else on disk, else ""."""
        if path in self.creates:
            return self.creates[path]
        if path in self.updates:
            return self.updates[path]
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def write(self, path: Path, content: str) -> None:
        """Plan *content* for *path*: an update when it exists, else a create."""
        if path in self.creates or not path.exists():
            self.creates[path] = content
        else:
            self.updates[path] = content

    def append_import(self, init_file: Path, line: str) -> None:
        """Add *line* to a package `__init__.py` unless it is already there."""
        current = self.text(init_file)
        if line in current.splitlines():
            return
        if current and not current.endswith("\n"):
            current += "\n"
        self.write(init_file, current + line + "\n")

    def update(self, path: Path, content: str) -> None:
        self.updates[path] = content

    def conflicts(self) -> list[Path]:
        return sorted(p for p, content in self.creates.items() if p.exists() and content)

    def outside_root(self) -> list[Path]:
        """Planned paths that resolve outside the project root, e.g. through `..`."""
        root = self.root.resolve()
        planned = [*self.creates, *self.updates]
        return sorted(p for p in planned if not p.resolve().is_relative_to(root))

    def _rel(self, path: Path) -> str:
        return os.path.relpath(path, self.root)

    def apply(self, *, dry_run: bool) -> None:
        for path, content in sorted(self.creates.items()):
            if dry_run:
                console.print(f"  Would create: {self._rel(path)}", markup=False, highlight=False)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and not content:
                continue
            path.write_text(content, encoding="utf-8")
            console.print(f"  Created {self._rel(path)}", markup=False, highlight=False)
        for path, content in sorted(self.updates.items()):
            if dry_run:
                console.print(f"  Would update: {self._rel(path)}", markup=False, highlight=False)
                continue
            path.write_text(content, encoding="utf-8")
            console.print(f"  Updated {self._rel(path)}", markup=False, highlight=False)
