.PHONY: install dev check test test-unit test-integration lint format clean observe-up observe-down

# Standardized commands for fastmcp-production-template
# Uses `uv` for fast Python package management

install:
	uv sync --all-extras

dev:
	uv run python -m src.server.main

# Run lint + type check + unit tests (CI default)
check: lint test-unit

# Unit tests only — no database required (CI default, pre-commit safe)
test-unit:
	uv run pytest tests/ -v -m "not integration"

# Integration tests — requires DATABASE_URL to point at a live PostgreSQL instance
# Quick start: docker compose -f docker/docker-compose.yml up -d postgres
# Then:        DATABASE_URL=postgresql://mcpuser:mcppassword@localhost:5432/mcpdb make test-integration
test-integration:
	uv run pytest tests/ -v -m integration

# Backwards-compatible alias
test: test-unit

lint:
	uv run ruff check src/ tests/
	uv run mypy src/ tests/ --ignore-missing-imports
	uv run bandit -r src/ -lll

format:
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

# Start the Grafana LGTM observability stack alongside the MCP server
observe-up:
	docker compose -f docker/docker-compose.yml -f docker/docker-compose.observe.yml up -d
	@echo "Grafana UI → http://localhost:3000  (no login required)"
	@echo "OTLP gRPC  → localhost:4317"
	@echo "OTLP HTTP  → localhost:4318"

observe-down:
	docker compose -f docker/docker-compose.yml -f docker/docker-compose.observe.yml down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
