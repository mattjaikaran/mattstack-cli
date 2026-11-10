.PHONY: help setup dev test lint format clean gauntlet gauntlet-quick gauntlet-gate arch-check filelength-check typecheck smoke-scaffold

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies
	uv sync

dev: ## Install in editable mode
	uv pip install -e ".[dev]"

test: ## Run tests
	uv run pytest -v

lint: ## Run linter
	uv run ruff check src/ tests/

format: ## Format code
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

clean: ## Clean build artifacts
	rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +


gauntlet: ## Run all gauntlet gates
	uv run python scripts/gauntlet.py

gauntlet-quick: ## Run gauntlet skipping mutation + audit
	uv run python scripts/gauntlet.py --quick

gauntlet-gate: ## Run a single gauntlet gate (usage: make gauntlet-gate GATE=lint)
	uv run python scripts/gauntlet.py --gate $(GATE)

smoke-scaffold: ## Scaffold presets and run just ci in each (needs network, just, uv, bun; usage: make smoke-scaffold ARGS="--preset starter-api")
	uv run python scripts/smoke_scaffold.py $(ARGS)

arch-check: ## Check architecture layer enforcement
	uv run python scripts/check_architecture.py

filelength-check: ## Check file length limits
	uv run python scripts/check_file_length.py

typecheck: ## Run mypy type checking
	uv run mypy src/
