"""
FastMCP Production Server — Entry Point
"""

from contextlib import asynccontextmanager

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config.security import initialize_allowlist
from .config.settings import Settings
from .db.connection import DatabasePool
from .db.pool import get_pool, set_pool
from .observability.context import set_telemetry
from .observability.telemetry import setup_telemetry
from .tools import detail, health, search, stats

settings = Settings()
telemetry = setup_telemetry(
    settings.service_name,
    otel_enabled=settings.otel_enabled,
    otlp_endpoint=settings.otel_exporter_otlp_endpoint,
)
set_telemetry(telemetry)  # make available to @instrument_tool decorators

db_pool = DatabasePool(
    dsn=settings.database_url,
    min_size=settings.db_pool_min,
    max_size=settings.db_pool_max,
)


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Initialize and teardown resources."""
    initialize_allowlist(settings.allowlist_path)
    await db_pool.initialize()
    set_pool(db_pool)  # make pool available to tools via singleton
    yield
    await db_pool.close()


mcp = FastMCP(
    name=settings.service_name,
    instructions=settings.service_description,
    lifespan=lifespan,
)

# Register tools
mcp.add_tool(search.search_records)
mcp.add_tool(detail.get_record_detail)
mcp.add_tool(stats.get_statistics)
mcp.add_tool(health.get_pool_status)


@mcp.custom_route("/health", methods=["GET"])
async def http_health(request: Request) -> JSONResponse:
    """HTTP health endpoint for Kubernetes liveness/readiness probes."""
    try:
        pool = get_pool()
        pool_status = await pool.health_check()
        return JSONResponse({"status": "ok", "pool": pool_status})
    except RuntimeError:
        return JSONResponse(
            {"status": "degraded", "detail": "database pool not initialized"},
            status_code=503,
        )


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=settings.port)
