.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down logs test test-local lint format typecheck check openapi reindex

help:  ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up:  ## Build and start the whole stack (API on http://localhost:8000/docs)
	$(COMPOSE) up -d --build

down:  ## Stop the stack and remove volumes
	$(COMPOSE) --profile test down -v

logs:  ## Follow application logs
	$(COMPOSE) logs -f app

test:  ## Run all tests inside Docker
	$(COMPOSE) --profile test run --rm --build tests

test-local:  ## Run tests from the host (needs `make up` or local PG/ES)
	uv run pytest

lint:  ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

format:  ## Auto-format the code
	uv run ruff check --fix .
	uv run ruff format .

typecheck:  ## Static type checking
	uv run mypy app tests

check: lint typecheck test-local  ## Everything CI runs

openapi:  ## Regenerate docs.json from the code
	uv run python -m app.cli export-openapi docs.json

reindex:  ## Rebuild the search index from the database (zero downtime)
	$(COMPOSE) exec app python -m app.cli reindex
