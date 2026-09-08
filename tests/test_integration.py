"""
Integration tests — require a live PostgreSQL database.

These tests are SKIPPED automatically when DATABASE_URL is not set.
They are excluded from the default pytest run and only execute when
the ``integration`` marker is explicitly requested.

Run locally (after starting docker/docker-compose.yml):
    DATABASE_URL=postgresql://mcpuser:mcppassword@localhost:5432/mcpdb \\
        pytest tests/test_integration.py -v

Run via make:
    make test-integration

CI:
    Handled by the ``integration-tests`` job in .github/workflows/ci.yml
    which spins up a postgres:16 service container automatically.
"""

import os
import uuid

import pytest
import pytest_asyncio

from src.server.config.security import initialize_allowlist
from src.server.db.connection import DatabasePool
from src.server.db.pool import set_pool

# ---------------------------------------------------------------------------
# Skip entire module when DATABASE_URL is absent
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL", "")

_skip_reason = "DATABASE_URL not set — skipping integration tests"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason=_skip_reason),
    pytest.mark.asyncio(loop_scope="module"),
]


# ---------------------------------------------------------------------------
# Module-level fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def db_pool():
    """
    Creates a real DatabasePool for the entire test module.
    Initialises the singleton so tool functions can call get_pool().
    Also loads the allowlist so @require_allowlist passes for all tools.
    """
    pool = DatabasePool(dsn=DATABASE_URL, min_size=2, max_size=5)
    await pool.initialize()
    set_pool(pool)
    initialize_allowlist("config/allowlist.yaml")
    yield pool
    await pool.close()


@pytest_asyncio.fixture(loop_scope="module")
async def seeded_records(db_pool: DatabasePool):
    """
    Inserts three test records before each test and deletes them after.
    Uses a short UUID prefix so records are identifiable and isolated.
    """
    tag = str(uuid.uuid4())[:8]
    ids: list[uuid.UUID] = []

    inserts = [
        (f"Integration-{tag}-0", "active",   "typeA", "cat1"),
        (f"Integration-{tag}-1", "active",   "typeA", "cat1"),
        (f"Integration-{tag}-2", "inactive", "typeB", "cat2"),
    ]
    for name, status, type_, category in inserts:
        row = await db_pool.fetchrow(
            """
            INSERT INTO records (name, description, status, type, category)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            name,
            f"Seeded by integration test {tag}",
            status,
            type_,
            category,
        )
        assert row is not None
        ids.append(row["id"])

    yield ids

    for rid in ids:
        await db_pool.execute("DELETE FROM records WHERE id = $1", rid)


# ---------------------------------------------------------------------------
# DatabasePool — low-level behaviour
# ---------------------------------------------------------------------------


class TestDatabasePool:
    async def test_health_check_returns_healthy(self, db_pool: DatabasePool):
        result = await db_pool.health_check()
        assert result["status"] == "healthy"
        assert result["size"] >= 1
        assert "min_size" in result
        assert "max_size" in result

    async def test_fetch_returns_list_of_dicts(self, db_pool: DatabasePool):
        rows = await db_pool.fetch("SELECT 1 AS val")
        assert isinstance(rows, list)
        assert rows[0]["val"] == 1

    async def test_fetchrow_returns_dict(self, db_pool: DatabasePool):
        row = await db_pool.fetchrow("SELECT 42 AS answer")
        assert row is not None
        assert row["answer"] == 42

    async def test_fetchval_returns_scalar(self, db_pool: DatabasePool):
        val = await db_pool.fetchval("SELECT 'hello'::text")
        assert val == "hello"

    async def test_fetchrow_returns_none_for_no_match(self, db_pool: DatabasePool):
        missing_id = str(uuid.uuid4())
        row = await db_pool.fetchrow(
            "SELECT * FROM records WHERE id = $1::uuid", missing_id
        )
        assert row is None

    async def test_execute_runs_write_query(self, db_pool: DatabasePool):
        row = await db_pool.fetchrow(
            "INSERT INTO records (name, status) VALUES ($1, $2) RETURNING id",
            "execute-test-record",
            "active",
        )
        assert row is not None
        inserted_id = row["id"]
        await db_pool.execute("DELETE FROM records WHERE id = $1", inserted_id)


# ---------------------------------------------------------------------------
# search_records — tool behaviour against real data
# ---------------------------------------------------------------------------


class TestSearchRecords:
    async def test_returns_matching_records(self, db_pool: DatabasePool, seeded_records: list):
        from src.server.tools.search import search_records

        result = await search_records(query="Integration-")
        assert result["total"] >= 3
        assert len(result["results"]) >= 3

    async def test_respects_limit(self, db_pool: DatabasePool, seeded_records: list):
        from src.server.tools.search import search_records

        result = await search_records(query="Integration-", limit=1)
        assert len(result["results"]) == 1
        assert result["limit"] == 1

    async def test_pagination_offset(self, db_pool: DatabasePool, seeded_records: list):
        from src.server.tools.search import search_records

        page0 = await search_records(query="Integration-", limit=2, offset=0)
        page1 = await search_records(query="Integration-", limit=2, offset=2)

        ids_page0 = {r["id"] for r in page0["results"]}
        ids_page1 = {r["id"] for r in page1["results"]}
        assert ids_page0.isdisjoint(ids_page1), "Pages must not overlap"

    async def test_status_filter_restricts_results(
        self, db_pool: DatabasePool, seeded_records: list
    ):
        from src.server.tools.search import search_records

        result = await search_records(query="Integration-", filters={"status": "active"})
        assert all(r["status"] == "active" for r in result["results"])

    async def test_invalid_filter_column_raises(self, db_pool: DatabasePool):
        from src.server.tools.search import search_records

        with pytest.raises(ValueError, match="Invalid filter column"):
            await search_records(query="x", filters={"'; DROP TABLE records;--": "x"})

    async def test_max_limit_capped_at_100(self, db_pool: DatabasePool):
        from src.server.tools.search import search_records

        result = await search_records(query="", limit=9999)
        assert result["limit"] == 100

    async def test_response_shape(self, db_pool: DatabasePool, seeded_records: list):
        from src.server.tools.search import search_records

        result = await search_records(query="Integration-")
        assert set(result.keys()) == {"results", "total", "limit", "offset", "query"}


# ---------------------------------------------------------------------------
# get_record_detail — tool behaviour against real data
# ---------------------------------------------------------------------------


class TestGetRecordDetail:
    async def test_returns_full_record_for_known_id(
        self, db_pool: DatabasePool, seeded_records: list
    ):
        from src.server.tools.detail import get_record_detail

        result = await get_record_detail(str(seeded_records[0]))

        assert str(result["id"]) == str(seeded_records[0])
        assert "name" in result
        assert "description" in result
        assert "status" in result
        assert "metadata" in result
        assert "created_at" in result
        assert "updated_at" in result

    async def test_returns_error_dict_for_missing_id(self, db_pool: DatabasePool):
        from src.server.tools.detail import get_record_detail

        result = await get_record_detail(str(uuid.uuid4()))
        assert "error" in result
        assert "record_id" in result

    async def test_does_not_raise_for_missing_id(self, db_pool: DatabasePool):
        from src.server.tools.detail import get_record_detail

        # Must return an error dict, not raise an exception
        result = await get_record_detail(str(uuid.uuid4()))
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# get_statistics — aggregation against real data
# ---------------------------------------------------------------------------


class TestGetStatistics:
    async def test_groups_by_status(self, db_pool: DatabasePool, seeded_records: list):
        from src.server.tools.stats import get_statistics

        result = await get_statistics(group_by="status")
        assert result["group_by"] == "status"
        assert result["total"] > 0
        labels = {row["label"] for row in result["breakdown"]}
        assert "active" in labels

    async def test_total_equals_sum_of_breakdown(
        self, db_pool: DatabasePool, seeded_records: list
    ):
        from src.server.tools.stats import get_statistics

        result = await get_statistics(group_by="status")
        breakdown_sum = sum(row["count"] for row in result["breakdown"])
        assert result["total"] == breakdown_sum

    async def test_groups_by_type(self, db_pool: DatabasePool, seeded_records: list):
        from src.server.tools.stats import get_statistics

        result = await get_statistics(group_by="type")
        assert result["group_by"] == "type"
        labels = {row["label"] for row in result["breakdown"]}
        assert "typeA" in labels

    async def test_invalid_group_by_raises(self, db_pool: DatabasePool):
        from src.server.tools.stats import get_statistics

        with pytest.raises(ValueError, match="Invalid group_by field"):
            await get_statistics(group_by="'; DROP TABLE records;--")

    async def test_response_shape(self, db_pool: DatabasePool, seeded_records: list):
        from src.server.tools.stats import get_statistics

        result = await get_statistics()
        assert set(result.keys()) == {"group_by", "total", "breakdown"}
