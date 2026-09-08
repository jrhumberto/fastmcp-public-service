"""
Module-level database pool singleton.
Initialized once at server startup via lifespan, accessed by tools directly.
"""

from .connection import DatabasePool

_pool: DatabasePool | None = None


def set_pool(pool: DatabasePool) -> None:
    global _pool
    _pool = pool


def get_pool() -> DatabasePool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Server lifespan may not have run.")
    return _pool
