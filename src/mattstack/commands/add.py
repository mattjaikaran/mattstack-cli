"""Add command: expand existing projects with new layers.

The new component's templates combine the existing project's resolved stack
(persisted mattstack.yml metadata first, manifest detection second) with the
choices for the new component. Existing root files are user files: without
--force, add writes the regenerated version next to them as
`<name>.mattstack-new` and leaves the original byte-identical.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import typer
from rich.markup import escape

from mattstack.config import (
    BackendFramework,
    FrontendFramework,
    ProjectConfig,
    TaskBackend,
    get_repo_urls,
)
from mattstack.post_processors.task_runtime import prepare_runtime
from mattstack.project import save_project_config
from mattstack.stack import ProjectStack, load_stack, unknown_framework_message
from mattstack.utils.console import (
    console,
    create_progress,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from mattstack.utils.git import clone_repo, remove_git_history

VALID_COMPONENTS = ("frontend", "backend", "ios")
NEW_FILE_SUFFIX = ".mattstack-new"


def _validate_framework(component: str, framework: str | None) -> None:
    """Exit unless ``framework`` is valid for ``component``."""
    if not framework:
        return
    choices: dict[str, list[str]] = {
        "frontend": [f.value for f in FrontendFramework],
        "backend": [f.value for f in BackendFramework],
        "ios": [],
    }
    valid = choices[component]
    if not valid:
        print_error(f"--framework does not apply to {component}")
        raise typer.Exit(code=1)
    if framework not in valid:
        print_error(f"Invalid {component} framework '{framework}'. Valid: {', '.join(valid)}")
        raise typer.Exit(code=1)


def _build_config(stack: ProjectStack, adding: str, framework: str | None) -> ProjectConfig:
    """Build the post-add ProjectConfig from the existing stack plus the new component."""
    config = stack.config(
        has_backend=stack.has_backend or adding == "backend",
        has_frontend=stack.has_frontend or adding == "frontend",
        has_ios=stack.has_ios or adding == "ios",
    )
    if adding == "frontend":
        chosen = FrontendFramework(framework) if framework else FrontendFramework.REACT_VITE
        return replace(config, frontend_framework=chosen)
    if adding == "backend":
        backend = BackendFramework(framework) if framework else BackendFramework.DJANGO_NINJA
        # A new backend gets its boilerplate's defaults; ProjectConfig maps
        # Celery to none for NestJS, which runs Bull inside the API.
        return replace(
            config, backend_framework=backend, task_backend=TaskBackend.CELERY, use_redis=True
        )
    return config


def _clone_component(component: str, config: ProjectConfig, *, dry_run: bool) -> bool:
    """Clone the appropriate repo for the given component."""
    if component == "frontend":
        repo_key = config.frontend_repo_key
        dest = config.frontend_dir
    elif component == "backend":
        repo_key = config.backend_repo_key
        dest = config.backend_dir
    else:
        repo_key = "swift-ios"
        dest = config.ios_dir

    url = get_repo_urls()[repo_key]

    if dry_run:
        print_info(f"[dry-run] Would clone {repo_key} ({url}) into {dest.name}/")
        return True

    if not clone_repo(url, dest):
        return False
    remove_git_history(dest)
    print_success(f"Cloned {component} ({repo_key}) into {dest.name}/")
    return True


def _customize_component(component: str, config: ProjectConfig, *, dry_run: bool) -> bool:
    """Run post-processing customization for the new component."""
    if dry_run:
        print_info(f"[dry-run] Would customize {component}")
        return True

    if component == "frontend":
        from mattstack.post_processors.customizer import customize_frontend
        from mattstack.post_processors.frontend_config import setup_frontend_monorepo

        customize_frontend(config)
        setup_frontend_monorepo(config)
    elif component == "backend":
        from mattstack.post_processors.customizer import customize_backend

        customize_backend(config)
    # iOS has no post-processing beyond the clone

    return True


def _root_files(config: ProjectConfig) -> list[tuple[str, str]]:
    from mattstack.templates.docker_compose import generate_docker_compose
    from mattstack.templates.root_env import generate_env_example
    from mattstack.templates.root_makefile import generate_makefile
    from mattstack.templates.root_readme import generate_readme

    files = [
        ("Makefile", generate_makefile(config)),
        (".env.example", generate_env_example(config)),
        ("README.md", generate_readme(config)),
    ]
    if config.has_backend:
        files.append(("docker-compose.yml", generate_docker_compose(config)))
    return files


def _update_root_files(config: ProjectConfig, *, dry_run: bool, force: bool) -> bool:
    """Create missing root files. Replace existing ones only with ``force``.

    Without ``force``, an existing file that differs from the regenerated
    content is left untouched and the new content goes to
    ``<name>.mattstack-new`` so the user can merge it.
    """
    staged: list[str] = []
    for filename, content in _root_files(config):
        filepath = config.path / filename
        exists = filepath.exists()
        if exists and filepath.read_text(encoding="utf-8", errors="replace") == content:
            continue
        if dry_run:
            if not exists:
                print_info(f"[dry-run] Would create {filename}")
            elif force:
                print_info(f"[dry-run] Would overwrite {filename} (--force)")
            else:
                print_info(f"[dry-run] Would keep {filename} and write {filename}{NEW_FILE_SUFFIX}")
            continue
        if exists and not force:
            (config.path / f"{filename}{NEW_FILE_SUFFIX}").write_text(content, encoding="utf-8")
            staged.append(filename)
            continue
        if exists:
            print_warning(f"Overwriting {filename} (--force)")
        filepath.write_text(content, encoding="utf-8")

    if staged:
        print_warning(f"Kept existing {', '.join(staged)}")
        print_info(
            f"Review the regenerated versions in *{NEW_FILE_SUFFIX} files, "
            "or re-run with --force to replace the originals"
        )
    return True


def _save_metadata(config: ProjectConfig, *, dry_run: bool) -> bool:
    """Persist the post-add stack so later commands do not re-guess it."""
    if dry_run:
        print_info("[dry-run] Would record the new stack in mattstack.yml")
        return True
    try:
        save_project_config(config)
    except ValueError as exc:
        print_error(f"Could not update mattstack.yml: {exc}")
        return False
    return True


def _print_next_steps(component: str, config: ProjectConfig) -> None:
    """Print instructions for what to do after adding a component."""
    console.print()
    print_success(f"Added {component} to '{config.name}'!")
    console.print()
    console.print("[bold]Next steps:[/bold]")

    if component == "frontend":
        console.print("  [cyan]cd frontend && bun install[/cyan]")
        console.print("  [cyan]make frontend-dev[/cyan]  # http://localhost:3000")
    elif component == "backend":
        install = "bun install" if config.is_nestjs_backend else "uv sync"
        console.print(f"  [cyan]cd backend && {install}[/cyan]")
        console.print("  [cyan]make up[/cyan]              # Start Docker services")
        console.print("  [cyan]make backend-migrate[/cyan]")
        if config.is_django_backend:
            console.print("  [cyan]make backend-superuser[/cyan]")
        api_url = f"http://localhost:{config.backend_api_port}"
        console.print(f"  [cyan]make backend-dev[/cyan]     # {api_url}")
    elif component == "ios":
        console.print("  [cyan]Open ios/ in Xcode[/cyan]")
        console.print("  [cyan]Update API base URL in the iOS project[/cyan]")

    console.print()


def _require_addable(stack: ProjectStack, component: str) -> None:
    """Exit unless ``component`` can be added to ``stack`` without guessing."""
    exists = {
        "frontend": stack.has_frontend,
        "backend": stack.has_backend,
        "ios": stack.has_ios,
    }
    if exists[component]:
        print_error(f"Project already has a {component} component")
        raise typer.Exit(code=1)
    if not stack.monorepo_layout:
        print_error(
            "add supports the backend/ + frontend/ monorepo layout only; "
            f"this project keeps a component at the root ({stack.root})"
        )
        raise typer.Exit(code=1)
    unknown = stack.unknown_components()
    if unknown:
        print_error(f"{unknown_framework_message(unknown)} add needs it to regenerate root files.")
        raise typer.Exit(code=1)


def run_add(
    component: str,
    project_path: Path,
    framework: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Add a new component (frontend, backend, ios) to an existing project."""
    if component not in VALID_COMPONENTS:
        print_error(
            f"Invalid component: '{component}'. Must be one of: {', '.join(VALID_COMPONENTS)}"
        )
        raise typer.Exit(code=1)

    _validate_framework(component, framework)

    if not project_path.is_dir():
        print_error(f"Project directory not found: {project_path}")
        raise typer.Exit(code=1)

    stack = load_stack(project_path.resolve())
    _require_addable(stack, component)
    if stack.root != project_path.resolve():
        console.print(f"[dim]Project root:[/dim] {escape(str(stack.root))}")

    config = _build_config(stack, component, framework)

    steps: list[tuple[str, Callable[[], bool]]] = [
        (f"Cloning {component}", lambda: _clone_component(component, config, dry_run=dry_run)),
        (
            f"Customizing {component}",
            lambda: _customize_component(component, config, dry_run=dry_run),
        ),
        # Regenerated root files carry TASK_BACKEND; the backend must accept it.
        (
            "Checking task and realtime runtime",
            lambda: prepare_runtime(config, dry_run=dry_run, existing_project=True),
        ),
        (
            "Updating root files",
            lambda: _update_root_files(config, dry_run=dry_run, force=force),
        ),
        ("Recording stack", lambda: _save_metadata(config, dry_run=dry_run)),
    ]

    with create_progress() as progress:
        task = progress.add_task(f"Adding {component}...", total=len(steps))
        for description, step_fn in steps:
            progress.update(task, description=description)
            if step_fn() is False:
                print_error(f"Failed at step: {description}")
                raise typer.Exit(code=1)
            progress.advance(task)

    if dry_run:
        print_info("Dry run complete. No files were changed.")
        return
    _print_next_steps(component, config)
