"""
Tests for MCP tool functions.
Uses pytest-asyncio for async test support.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.server.tools.detail import get_record_detail
from src.server.tools.health import get_pool_status
from src.server.tools.search import search_records
from src.server.tools.stats import get_statistics


@pytest.fixture
def mock_pool():
    """Mock DatabasePool for unit tests."""
    pool = AsyncMock()
    pool.health_check = AsyncMock(return_value={
        "status": "healthy", "size": 5, "idle": 3,
        "min_size": 5, "max_size": 20,
    })
    return pool


# ---------------------------------------------------------------------------
# get_pool_status
# ---------------------------------------------------------------------------


async def test_get_pool_status_returns_healthy(mock_pool):
    with patch("src.server.tools.health.get_pool", return_value=mock_pool):
        result = await get_pool_status()
    assert result["server"] == "healthy"
    assert result["database"]["status"] == "healthy"
    assert result["database"]["size"] == 5


# ---------------------------------------------------------------------------
# get_statistics
# ---------------------------------------------------------------------------


async def test_get_statistics_invalid_group_by_raises():
    with patch("src.server.config.security.is_allowed", return_value=True):
        with pytest.raises(ValueError, match="Invalid group_by field"):
            await get_statistics(group_by="injected_field; DROP TABLE records;--")


async def test_get_statistics_valid_group_by(mock_pool):
    mock_pool.fetch = AsyncMock(return_value=[
        {"label": "active", "count": 42},
        {"label": "inactive", "count": 8},
    ])
    with patch("src.server.tools.stats.get_pool", return_value=mock_pool):
        with patch("src.server.config.security.is_allowed", return_value=True):
            result = await get_statistics(group_by="status")
    assert result["total"] == 50
    assert result["group_by"] == "status"
    assert len(result["breakdown"]) == 2


# ---------------------------------------------------------------------------
# search_records
# ---------------------------------------------------------------------------


async def test_search_records_returns_results(mock_pool):
    mock_pool.fetch = AsyncMock(return_value=[
        {"id": "1", "name": "Alpha", "description": "first",
         "status": "active", "created_at": "2024-01-01"},
    ])
    mock_pool.fetchval = AsyncMock(return_value=1)
    with patch("src.server.tools.search.get_pool", return_value=mock_pool):
        with patch("src.server.config.security.is_allowed", return_value=True):
            result = await search_records(query="Alpha")
    assert result["total"] == 1
    assert len(result["results"]) == 1
    assert result["query"] == "Alpha"


async def test_search_records_enforces_max_limit(mock_pool):
    mock_pool.fetch = AsyncMock(return_value=[])
    mock_pool.fetchval = AsyncMock(return_value=0)
    with patch("src.server.tools.search.get_pool", return_value=mock_pool):
        with patch("src.server.config.security.is_allowed", return_value=True):
            result = await search_records(query="x", limit=500)
    assert result["limit"] == 100


async def test_search_records_rejects_invalid_filter_column():
    with patch("src.server.config.security.is_allowed", return_value=True):
        with pytest.raises(ValueError, match="Invalid filter column"):
            await search_records(query="x", filters={"evil_col; DROP TABLE": "val"})


async def test_search_records_valid_filter(mock_pool):
    mock_pool.fetch = AsyncMock(return_value=[])
    mock_pool.fetchval = AsyncMock(return_value=0)
    with patch("src.server.tools.search.get_pool", return_value=mock_pool):
        with patch("src.server.config.security.is_allowed", return_value=True):
            result = await search_records(query="test", filters={"status": "active"})
    assert result["total"] == 0


async def test_search_records_propagates_db_errors(mock_pool):
    mock_pool.fetch = AsyncMock(side_effect=RuntimeError("db error"))
    mock_pool.fetchval = AsyncMock(side_effect=RuntimeError("db error"))
    with patch("src.server.tools.search.get_pool", return_value=mock_pool):
        with patch("src.server.config.security.is_allowed", return_value=True):
            with pytest.raises(RuntimeError, match="db error"):
                await search_records(query="test")


# ---------------------------------------------------------------------------
# get_record_detail
# ---------------------------------------------------------------------------


async def test_get_record_detail_found(mock_pool):
    record_id = str(uuid.uuid4())
    mock_pool.fetchrow = AsyncMock(return_value={
        "id": record_id,
        "name": "Test Record",
        "description": "desc",
        "status": "active",
        "metadata": None,
        "created_at": "2024-01-01",
        "updated_at": "2024-01-01",
    })
    with patch("src.server.tools.detail.get_pool", return_value=mock_pool):
        with patch("src.server.config.security.is_allowed", return_value=True):
            result = await get_record_detail(record_id)
    assert result["id"] == record_id
    assert result["name"] == "Test Record"


async def test_get_record_detail_not_found(mock_pool):
    mock_pool.fetchrow = AsyncMock(return_value=None)
    with patch("src.server.tools.detail.get_pool", return_value=mock_pool):
        with patch("src.server.config.security.is_allowed", return_value=True):
            result = await get_record_detail("nonexistent-id")
    assert "error" in result
    assert result["record_id"] == "nonexistent-id"
