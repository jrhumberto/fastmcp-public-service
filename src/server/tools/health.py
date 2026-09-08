"""
get_pool_status — Health check tool exposing DB pool and server status.
"""

import logging

from ..db.pool import get_pool

logger = logging.getLogger(__name__)


async def get_pool_status() -> dict:
    """
    Return current database connection pool status and server health.
    Not subject to allowlist — always accessible for monitoring.

    Returns:
        Pool size, idle connections, and overall health status
    """
    pool_status = await get_pool().health_check()
    logger.debug(f"get_pool_status: {pool_status}")
    return {"server": "healthy", "database": pool_status}
