"""
get_record_detail — Fetch a single record by ID with full field expansion.
"""

import logging

from ..config.security import require_allowlist
from ..db.pool import get_pool
from ..observability.instrument import instrument_tool

logger = logging.getLogger(__name__)


@instrument_tool("get_record_detail")
@require_allowlist("get_record_detail")
async def get_record_detail(record_id: str) -> dict:
    """
    Fetch complete details for a single record by its unique ID.

    Args:
        record_id: Unique identifier of the record

    Returns:
        Full record dictionary, or error if not found
    """
    row = await get_pool().fetchrow(
        """
        SELECT id, name, description, status, metadata, created_at, updated_at
        FROM records
        WHERE id = $1
        """,
        record_id,
    )

    if not row:
        logger.warning("get_record_detail: record_id=%r not found", record_id)
        return {"error": f"Record '{record_id}' not found", "record_id": record_id}

    logger.info("get_record_detail: record_id=%r found", record_id)
    return row
