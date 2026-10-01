"""User configuration from ~/.mattstack/config.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

USER_CONFIG_DIR = Path.home() / ".mattstack"
USER_CONFIG_PATH = USER_CONFIG_DIR / "config.yaml"

TEMPLATE_CONFIG = """\
# mattstack user configuration
# Place this file at ~/.mattstack/config.yaml

# Custom boilerplate repos (merged with defaults, overrides take precedence)
# repos:
#   django-ninja: https://github.com/myorg/django-boilerplate.git
#   nextjs: https://github.com/myorg/nextjs-boilerplate.git

# Custom presets
# presets:
#   my-fullstack:
#     description: "Our team's fullstack setup"
#     project_type: fullstack
#     variant: starter
#     frontend_framework: react-vite

# Default settings
# defaults:
#   deployment: docker
#   use_celery: true
#   use_redis: true
#   init_git: true
#   package_manager: bun    # bun | npm | yarn | pnpm
"""


def load_user_config() -> dict[str, object]:
    """Load user config from ~/.mattstack/config.yaml. Returns empty dict if missing."""
    if not USER_CONFIG_PATH.is_file():
        return {}
    try:
        data = yaml.safe_load(USER_CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (yaml.YAMLError, OSError):
        return {}


def get_user_repos() -> dict[str, object]:
    """Get custom repo URLs from user config."""
    config = load_user_config()
    repos = config.get("repos", {})
    return repos if isinstance(repos, dict) else {}


def get_user_presets() -> dict[str, object]:
    """Get custom presets from user config."""
    config = load_user_config()
    presets = config.get("presets", {})
    return presets if isinstance(presets, dict) else {}


def get_user_defaults() -> dict[str, object]:
    """Get default settings from user config."""
    config = load_user_config()
    defaults = config.get("defaults", {})
    return defaults if isinstance(defaults, dict) else {}


def init_user_config() -> Path:
    """Create template config at ~/.mattstack/config.yaml."""
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USER_CONFIG_PATH.write_text(TEMPLATE_CONFIG, encoding="utf-8")
    return USER_CONFIG_PATH
