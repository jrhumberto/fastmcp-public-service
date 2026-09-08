"""
search_records — Generic search tool with filtering, pagination, and observability.
"""

import asyncio
import logging
from typing import Any

from ..config.security import require_allowlist
from ..db.pool import get_pool
from ..observability.instrument import instrument_tool

logger = logging.getLogger(__name__)


@instrument_tool("search_records")
@require_allowlist("search_records")
async def search_records(
    query: str,
    limit: int = 20,
    offset: int = 0,
    filters: dict[str, Any] | None = None,
) -> dict:
    """
    Search records using a full-text query with optional field filters.

    Args:
        query: Search term to match against record fields
        limit: Maximum number of results to return (default: 20, max: 100)
        offset: Pagination offset (default: 0)
        filters: Optional key-value pairs for exact field matching

    Returns:
        Dictionary with 'results' list and 'total' count
    """
    limit = min(limit, 100)  # enforce max page size

    # Validate filter column names against an allowlist to prevent SQL injection
    allowed_filter_cols = {"status", "type", "category"}
    if filters:
        invalid = set(filters) - allowed_filter_cols
        if invalid:
            raise ValueError(
                f"Invalid filter column(s): {invalid}. "
                f"Allowed: {sorted(allowed_filter_cols)}"
            )

    try:
        # Build parameterized query — never use string interpolation for values
        where_clauses = ["(name ILIKE $1 OR description ILIKE $1)"]
        params: list[Any] = [f"%{query}%"]

        if filters:
            for i, (col, val) in enumerate(filters.items(), start=2):
                where_clauses.append(f"{col} = ${i}")  # col is safe: validated above
                params.append(val)

        where_sql = " AND ".join(where_clauses)
        sql = f"""
            SELECT id, name, description, status, created_at
            FROM records
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """
        params.extend([limit, offset])

        count_sql = f"SELECT COUNT(*) FROM records WHERE {where_sql}"
        count_params = params[: len(params) - 2]

        db = get_pool()
        results, total = await asyncio.gather(
            db.fetch(sql, *params),
            db.fetchval(count_sql, *count_params),
        )

        logger.info(
            "search_records: query=%r results=%d total=%d", query, len(results), total
        )

        return {
            "results": results,
            "total": total,
            "limit": limit,
            "offset": offset,
            "query": query,
        }

    except Exception as e:
        logger.error("search_records failed: %s", e)
        raise
