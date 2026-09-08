# Contributing to fastmcp-production-template

First off, thank you for considering contributing to `fastmcp-production-template`! It's people like you that make open-source such a great community.

## 1. Where do I go from here?

If you've noticed a bug or have a feature request, please make sure to check our [issue tracker](https://github.com/ManjunathGovindaraju/fastmcp-production-template/issues) to see if someone else has already created a ticket. If not, go ahead and [create one](https://github.com/ManjunathGovindaraju/fastmcp-production-template/issues/new/choose)!

## 2. Setting up your environment

This project uses [`uv`](https://github.com/astral-sh/uv) for dependency management.

```bash
# Clone the repository
git clone https://github.com/ManjunathGovindaraju/fastmcp-production-template.git
cd fastmcp-production-template

# Install dependencies
make install
# Alternatively: uv sync
```

## 3. Development Workflow

We use a `Makefile` to simplify common development tasks:

| Command | What it does |
|---|---|
| `make dev` | Run the MCP server locally |
| `make check` | Lint + type check + unit tests (run this before every PR) |
| `make test-unit` | Unit tests only — no database required, fast |
| `make test-integration` | Integration tests — requires `DATABASE_URL` to point at PostgreSQL |
| `make lint` | Ruff + mypy + Bandit static analysis |
| `make format` | Auto-format with `ruff format` and `ruff check --fix` |
| `make observe-up` | Start MCP server + full Grafana LGTM observability stack |
| `make observe-down` | Stop the observability stack |

**Before submitting a pull request**, ensure `make check` passes cleanly. Integration tests are run automatically in CI against a PostgreSQL service container, so you don't need a local database to contribute — but running them locally is encouraged if your change touches database or tool logic.

```bash
# Minimum required before opening a PR:
make check

# If you touched db/, tools/, or test_integration.py:
docker compose -f docker/docker-compose.yml up -d postgres
DATABASE_URL=postgresql://mcpuser:mcppassword@localhost:5432/mcpdb make test-integration
```

## 4. Submitting a Pull Request

1. Fork the repository.
2. Create a new branch (`git checkout -b feature/your-feature-name`).
3. Make your changes.
4. Run `make check` (lint + type check + unit tests).
5. If you touched `db/`, `tools/`, or integration tests, also run `make test-integration`.
6. Commit your changes (`git commit -m 'Add some feature'`).
7. Push to the branch (`git push origin feature/your-feature-name`).
8. Open a Pull Request.

Please fill out the provided Pull Request template when opening your PR.
