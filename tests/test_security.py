"""
Tests for tool-level allowlist security.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.server.config.security import load_allowlist, require_allowlist


def test_load_allowlist_returns_set(tmp_path):
    allowlist_file = tmp_path / "allowlist.yaml"
    allowlist_file.write_text("allowed_tools:\n  - search_records\n  - get_record_detail\n")
    result = load_allowlist(str(allowlist_file))
    assert result == {"search_records", "get_record_detail"}


def test_load_allowlist_missing_file_returns_empty(tmp_path):
    result = load_allowlist(str(tmp_path / "nonexistent.yaml"))
    assert result == set()


@pytest.mark.asyncio
async def test_require_allowlist_blocks_unlisted_tool():
    with patch("src.server.config.security._allowlist", {"search_records"}):
        @require_allowlist("blocked_tool")
        async def my_tool(ctx):
            return "should not reach here"

        with pytest.raises(PermissionError, match="blocked_tool"):
            await my_tool(MagicMock())


@pytest.mark.asyncio
async def test_require_allowlist_permits_listed_tool():
    with patch("src.server.config.security._allowlist", {"allowed_tool"}):
        @require_allowlist("allowed_tool")
        async def my_tool(ctx):
            return "success"

        result = await my_tool(MagicMock())
        assert result == "success"
