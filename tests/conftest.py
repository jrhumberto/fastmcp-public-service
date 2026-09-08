"""
Shared pytest fixtures for the fastmcp-production-template test suite.
"""

from unittest.mock import MagicMock

import pytest

from src.server.observability import context
from src.server.observability.telemetry import Telemetry


@pytest.fixture
def mock_telemetry():
    """
    Injects a real Telemetry instance (with MagicMock fields) into the singleton and
    tears it down after each test.

    We use a real Telemetry dataclass instance rather than MagicMock(spec=Telemetry)
    because dataclass fields are instance attributes — spec only sees class-level names.
    MagicMock fields automatically support context-manager protocol for the tracer span.

    Usage:
        async def test_something(mock_telemetry):
            mock_telemetry.tool_calls.add.assert_called_once_with(1, {"tool": "my_tool"})
    """
    tel = Telemetry(
        tracer=MagicMock(),
        tool_calls=MagicMock(),
        tool_errors=MagicMock(),
        tool_duration=MagicMock(),
        db_pool_size=MagicMock(),
    )
    original = context._telemetry
    context._telemetry = tel
    yield tel
    context._telemetry = original
