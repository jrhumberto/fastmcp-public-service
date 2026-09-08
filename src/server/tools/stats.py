"""
get_statistics — Aggregate statistics for dashboard and summary queries.
"""

import logging

from ..config.security import require_allowlist
from ..db.pool import get_pool
from ..observability.instrument import instrument_tool

logger = logging.getLogger(__name__)


@instrument_tool("get_statistics")
@require_allowlist("get_statistics")
async def get_statistics(group_by: str = "status") -> dict:
    """
    Return aggregated record counts grouped by a field.

    Args:
        group_by: Field name to group counts by (default: 'status')

    Returns:
        Dictionary with group labels and counts
    """
    allowed_group_fields = {"status", "type", "category"}
    if group_by not in allowed_group_fields:
        raise ValueError(
            f"Invalid group_by field '{group_by}'. "
            f"Allowed: {sorted(allowed_group_fields)}"
        )

    rows = await get_pool().fetch(
        f"""
        SELECT {group_by} AS label, COUNT(*) AS count
        FROM records
        GROUP BY {group_by}
        ORDER BY count DESC
        """,
    )

    total = sum(r["count"] for r in rows)
    logger.info("get_statistics: group_by=%r groups=%d total=%d", group_by, len(rows), total)

    return {
        "group_by": group_by,
        "total": total,
        "breakdown": rows,
    }
