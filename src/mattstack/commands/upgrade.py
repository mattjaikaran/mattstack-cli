"""Upgrade command: pull latest boilerplate changes into existing project.

Each component is compared against the upstream boilerplate of its resolved
framework (mattstack.yml metadata first, manifest detection second), using
the user's repo overrides. Upgrade previews by default: it writes new or
modified files only with --force, and never after a failed clone or for a
component whose framework is unknown.
"""

from __future__ import annotations

import difflib
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import typer
from rich.markup import escape
from rich.table import Table

from mattstack.config import BackendFramework, FrontendFramework, get_repo_urls
from mattstack.stack import ProjectStack, load_stack, unknown_framework_message
from mattstack.utils.console import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from mattstack.utils.git import clone_repo, remove_git_history

COMPONENTS: tuple[str, ...] = ("backend", "frontend")

# Files that are typically user-customized and should never be overwritten
SKIP_FILES: set[str] = {"README.md", ".env", ".env.local", "CLAUDE.md"}

# Directories to ignore when comparing file trees
IGNORE_DIRS: set[str] = {".git", "__pycache__", "node_modules", ".venv", ".ruff_cache"}

# Longest diff shown per modified file in a preview
MAX_DIFF_LINES = 200


@dataclass
class UpgradeReport:
    """Summary of changes for a single component upgrade."""

    component: str
    repo_key: str = ""
    new_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    applied: int = 0
    skipped: int = 0
    error: str | None = None

    @property
    def total_changes(self) -> int:
        return len(self.new_files) + len(self.modified_files) + len(self.deleted_files)

    @property
    def has_changes(self) -> bool:
        return self.total_changes > 0

    @property
    def pending(self) -> int:
        """Upstream files that --force would write."""
        return len(self.new_files) + len(self.modified_files)


def run_upgrade(
    path: Path,
    *,
    component: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Main upgrade entry point. Compares project against fresh boilerplate clones.

    Exits 1 when any component could not be compared.
    """
    project_path = path.resolve()

    if not project_path.is_dir():
        print_error(f"Not a directory: {project_path}")
        raise typer.Exit(code=1)

    stack = load_stack(project_path)
    components = _detect_components(stack)
    if not components:
        print_error("No recognized components found (backend/frontend)")
        raise typer.Exit(code=1)

    if component:
        if component not in COMPONENTS:
            print_error(f"Unknown component: '{component}'. Valid: {', '.join(COMPONENTS)}")
            raise typer.Exit(code=1)
        if component not in components:
            print_error(f"Component '{component}' not found in project at {stack.root}")
            raise typer.Exit(code=1)
        components = [component]

    label = "Upgrade (dry run):" if dry_run else "Upgrading:"
    console.print(f"\n[bold cyan]{label}[/bold cyan] {escape(str(stack.root))}\n")

    # Clone and compare every selected component before writing anything, so
    # a later failure cannot leave the project half-upgraded.
    with tempfile.TemporaryDirectory() as tmp_dir:
        plans = [_plan_component(stack, comp, Path(tmp_dir)) for comp in components]
        reports = [plan.report for plan in plans]
        failed = any(report.error for report in reports)
        apply = force and not dry_run and not failed

        for plan in plans:
            if plan.report.error or not plan.report.has_changes:
                continue
            _print_changes(plan.report)
            if not apply:
                _print_diffs(plan.upstream, plan.target, plan.report.modified_files)

        if apply:
            for plan in plans:
                _apply(plan)
        else:
            for report in reports:
                report.skipped = report.pending

    _print_summary(reports, dry_run=dry_run, applied=apply)
    if failed:
        if force and not dry_run:
            print_error("No files were changed because a component could not be checked.")
        raise typer.Exit(code=1)


def _detect_components(stack: ProjectStack) -> list[str]:
    """Return the components that exist in the project."""
    present = {"backend": stack.has_backend, "frontend": stack.has_frontend}
    return [comp for comp in COMPONENTS if present[comp]]


@dataclass
class _Plan:
    """A compared component: its report, fresh upstream clone, and project dir."""

    report: UpgradeReport
    upstream: Path
    target: Path


def _plan_component(stack: ProjectStack, component: str, workdir: Path) -> _Plan:
    """Clone one component's own upstream boilerplate and compare it. Writes nothing."""
    report = UpgradeReport(component=component)
    project = stack.project
    framework: BackendFramework | FrontendFramework | None
    if component == "backend":
        framework, target_dir = project.backend_framework, project.backend_dir
    else:
        framework, target_dir = project.frontend_framework, project.frontend_dir
    plan = _Plan(report=report, upstream=workdir / component, target=target_dir)

    if framework is None:
        report.error = f"cannot determine the {component} framework"
        print_error(f"{component}: {unknown_framework_message([component])}")
        return plan

    report.repo_key = framework.value
    url = get_repo_urls().get(report.repo_key)
    if not isinstance(url, str) or not url:
        report.error = f"no repository URL configured for {report.repo_key}"
        print_error(f"{component}: {report.error}")
        return plan

    print_info(f"Checking {component} against upstream {report.repo_key} ({url})...")
    if not clone_repo(url, plan.upstream):
        report.error = f"failed to clone {report.repo_key} from {url}"
        print_error(f"{component}: {report.error}")
        return plan
    remove_git_history(plan.upstream)

    new_files, modified_files, deleted_files = _compare_directories(plan.upstream, target_dir)
    report.new_files = new_files
    report.modified_files = modified_files
    report.deleted_files = deleted_files
    if not report.has_changes:
        print_success(f"{component}: already up to date with {report.repo_key}")
    return plan


def _apply(plan: _Plan) -> None:
    """Copy new and modified upstream files into the project. Deletions are ignored."""
    report = plan.report
    for rel_path in [*report.new_files, *report.modified_files]:
        dst_file = plan.target / rel_path
        if _has_symlink(dst_file, plan.target):
            print_warning(f"Skipping symlink path: {rel_path}")
            continue
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plan.upstream / rel_path, dst_file)
        report.applied += 1


def _has_symlink(path: Path, root: Path) -> bool:
    """Reject symlinks in a file path, including its component root."""
    return any(
        candidate.is_symlink()
        for candidate in (path, *path.parents)
        if candidate.is_relative_to(root)
    )


def _comparable(path: Path, rel: Path) -> bool:
    """True when ``path`` is a regular file that upgrade may compare or write."""
    if any(part in IGNORE_DIRS for part in rel.parts) or rel.name in SKIP_FILES:
        return False
    return path.is_file() and not path.is_symlink()


def _compare_directories(source: Path, target: Path) -> tuple[list[str], list[str], list[str]]:
    """Compare source (fresh clone) with target (existing project).

    Returns (new_files, modified_files, deleted_files) as relative path strings.
    Symlinks and paths where the project has a directory are never written,
    so they are left out.
    """
    new_files: list[str] = []
    modified_files: list[str] = []

    for src_file in sorted(source.rglob("*")):
        rel = src_file.relative_to(source)
        if not _comparable(src_file, rel):
            continue
        target_file = target / rel
        if _has_symlink(target_file, target) or target_file.is_dir():
            continue
        if not target_file.exists():
            new_files.append(str(rel))
        elif src_file.read_bytes() != target_file.read_bytes():
            modified_files.append(str(rel))

    deleted_files: list[str] = []
    for tgt_file in sorted(target.rglob("*")):
        rel = tgt_file.relative_to(target)
        if _comparable(tgt_file, rel) and not (source / rel).exists():
            deleted_files.append(str(rel))

    return new_files, modified_files, deleted_files


def _print_changes(report: UpgradeReport) -> None:
    """Print a Rich table of detected changes for a component."""
    table = Table(
        title=f"{report.component} changes ({report.repo_key})",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Status", style="bold", width=10)
    table.add_column("File")

    for f in report.new_files:
        table.add_row("[green]new[/green]", escape(f))
    for f in report.modified_files:
        table.add_row("[yellow]modified[/yellow]", escape(f))
    for f in report.deleted_files:
        table.add_row("[red]deleted[/red]", escape(f))

    console.print(table)
    console.print()


def _print_diffs(upstream: Path, target: Path, modified_files: list[str]) -> None:
    """Print a unified diff (project -> upstream) for each modified text file."""
    for rel in modified_files:
        try:
            ours = (target / rel).read_text(encoding="utf-8").splitlines(keepends=True)
            theirs = (upstream / rel).read_text(encoding="utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            console.print(f"[dim]Binary file differs: {escape(rel)}[/dim]")
            continue
        diff = list(difflib.unified_diff(ours, theirs, f"project/{rel}", f"upstream/{rel}"))
        shown = "".join(diff[:MAX_DIFF_LINES]).rstrip("\n")
        console.print(shown, markup=False, highlight=False)
        if len(diff) > MAX_DIFF_LINES:
            console.print(f"[dim]... {len(diff) - MAX_DIFF_LINES} more diff line(s)[/dim]")
        console.print()


def _print_summary(
    reports: list[UpgradeReport], *, dry_run: bool = False, applied: bool = False
) -> None:
    """Print final summary across all components."""
    failed = [r for r in reports if r.error]
    compared = [r for r in reports if not r.error]

    if compared and not any(r.has_changes for r in compared):
        names = ", ".join(r.component for r in compared)
        print_success(f"Up to date: {names}")
    elif compared:
        console.print("[bold]Summary:[/bold]")
        console.print(f"  New files:      {sum(len(r.new_files) for r in compared)}")
        console.print(f"  Modified files: {sum(len(r.modified_files) for r in compared)}")
        console.print(f"  Deleted files:  {sum(len(r.deleted_files) for r in compared)} (ignored)")
        pending = sum(r.pending for r in compared)
        if dry_run:
            print_info("Dry run complete. No files were changed.")
        elif applied:
            console.print(f"  Applied:        {sum(r.applied for r in compared)}")
        elif pending and not failed:
            print_warning(
                f"No files were changed. Re-run with --force to apply {pending} new or "
                "modified file(s) listed above."
            )

    if failed:
        for report in failed:
            print_error(f"{report.component}: not checked ({report.error})")

    console.print()
