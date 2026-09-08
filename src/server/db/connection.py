"""
Async PostgreSQL connection pool using asyncpg.
Supports min/max pool sizing, health checks, and graceful shutdown.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg

logger = logging.getLogger(__name__)


class DatabasePool:
    """
    Production-grade async PostgreSQL connection pool.

    Features:
    - Configurable min/max pool size
    - Health check endpoint
    - Graceful initialize and close lifecycle
    - Context manager for safe connection acquisition
    """

    def __init__(self, dsn: str, min_size: int = 5, max_size: int = 20):
        self._dsn = dsn
        self._min = min_size
        self._max = max_size
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        """Create the connection pool. Call once on server startup."""
        logger.info(f"Initializing DB pool (min={self._min}, max={self._max})")
        self._pool = await asyncpg.create_pool(
            self._dsn,
            min_size=self._min,
            max_size=self._max,
            command_timeout=30,
        )
        logger.info("DB pool initialized successfully")

    async def close(self) -> None:
        """Gracefully close all pool connections. Call on server shutdown."""
        if self._pool:
            await self._pool.close()
            logger.info("DB pool closed")

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[asyncpg.Connection]:
        """Acquire a connection from the pool as a context manager."""
        if not self._pool:
            raise RuntimeError("DatabasePool not initialized. Call initialize() first.")
        async with self._pool.acquire() as conn:
            yield conn

    async def health_check(self) -> dict:
        """Return current pool status for health monitoring."""
        if not self._pool:
            return {"status": "uninitialized", "size": 0, "idle": 0}
        return {
            "status": "healthy",
            "size": self._pool.get_size(),
            "idle": self._pool.get_idle_size(),
            "min_size": self._min,
            "max_size": self._max,
        }

    async def execute(self, query: str, *args) -> str:
        """Execute a write query (INSERT, UPDATE, DELETE)."""
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> list[dict]:
        """Execute a read query and return list of row dicts."""
        async with self.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]

    async def fetchrow(self, query: str, *args) -> dict | None:
        """Execute a read query and return a single row dict."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def fetchval(self, query: str, *args):
        """Execute a read query and return a single scalar value."""
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)
