# ─── Build stage ────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml README.md ./
RUN uv sync --no-dev

# ─── Runtime stage ───────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Non-root user for security
RUN groupadd -r mcpuser && useradd -r -g mcpuser mcpuser

# Copy installed dependencies from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy source and config
COPY src/ ./src/
COPY config/ ./config/

RUN chown -R mcpuser:mcpuser /app
USER mcpuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"

CMD ["python", "-m", "src.server.main"]
