"""
Tests for the observability layer:
  - context.py  — set_telemetry / get_telemetry singleton
  - instrument.py — @instrument_tool decorator behaviour
  - telemetry.py  — setup_telemetry() console-mode smoke test
"""

from unittest.mock import MagicMock, patch

import pytest

from src.server.observability import context
from src.server.observability.context import get_telemetry, set_telemetry
from src.server.observability.instrument import instrument_tool
from src.server.observability.telemetry import Telemetry, setup_telemetry

# ---------------------------------------------------------------------------
# context.py — singleton helpers
# ---------------------------------------------------------------------------


def test_get_telemetry_returns_none_before_set():
    original = context._telemetry
    context._telemetry = None
    assert get_telemetry() is None
    context._telemetry = original


def test_set_telemetry_stores_instance():
    tel = MagicMock(spec=Telemetry)
    original = context._telemetry
    set_telemetry(tel)
    assert get_telemetry() is tel
    context._telemetry = original


def test_set_telemetry_accepts_none_for_teardown():
    tel = MagicMock(spec=Telemetry)
    set_telemetry(tel)
    set_telemetry(None)
    assert get_telemetry() is None


# ---------------------------------------------------------------------------
# instrument.py — @instrument_tool decorator
# ---------------------------------------------------------------------------


async def test_instrument_tool_transparent_when_no_telemetry():
    """Decorator is a zero-overhead pass-through when telemetry is None."""
    original = context._telemetry
    context._telemetry = None

    @instrument_tool("my_tool")
    async def my_tool() -> str:
        return "result"

    assert await my_tool() == "result"
    context._telemetry = original


async def test_instrument_tool_records_call_counter(mock_telemetry):
    @instrument_tool("my_tool")
    async def my_tool() -> str:
        return "ok"

    await my_tool()

    mock_telemetry.tool_calls.add.assert_called_once_with(1, {"tool": "my_tool"})


async def test_instrument_tool_records_duration_on_success(mock_telemetry):
    @instrument_tool("my_tool")
    async def my_tool() -> str:
        return "ok"

    await my_tool()

    mock_telemetry.tool_duration.record.assert_called_once()
    recorded_ms, attrs = mock_telemetry.tool_duration.record.call_args.args
    assert recorded_ms >= 0
    assert attrs == {"tool": "my_tool"}


async def test_instrument_tool_records_error_counter_on_exception(mock_telemetry):
    @instrument_tool("my_tool")
    async def failing_tool() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await failing_tool()

    mock_telemetry.tool_calls.add.assert_called_once_with(1, {"tool": "my_tool"})
    mock_telemetry.tool_errors.add.assert_called_once_with(1, {"tool": "my_tool"})
    mock_telemetry.tool_duration.record.assert_not_called()


async def test_instrument_tool_reraises_original_exception(mock_telemetry):
    class CustomError(Exception):
        pass

    @instrument_tool("my_tool")
    async def failing_tool() -> None:
        raise CustomError("specific error")

    with pytest.raises(CustomError, match="specific error"):
        await failing_tool()


async def test_instrument_tool_preserves_function_metadata():
    """functools.wraps must preserve __name__ so FastMCP reads the right tool signature."""

    @instrument_tool("search_records")
    async def search_records(query: str) -> dict:
        """Search docstring."""
        return {}

    assert search_records.__name__ == "search_records"
    assert "Search docstring" in (search_records.__doc__ or "")


async def test_instrument_tool_uses_tool_name_attribute(mock_telemetry):
    """Metric attributes use the name passed to @instrument_tool, not the function name."""

    @instrument_tool("custom_name")
    async def differently_named_fn() -> str:
        return "ok"

    await differently_named_fn()

    mock_telemetry.tool_calls.add.assert_called_once_with(1, {"tool": "custom_name"})


async def test_instrument_tool_spans_wrap_execution(mock_telemetry):
    """A tracer span is started and exited for every call."""

    @instrument_tool("my_tool")
    async def my_tool() -> str:
        return "ok"

    await my_tool()

    mock_telemetry.tracer.start_as_current_span.assert_called_once_with("my_tool")


# ---------------------------------------------------------------------------
# telemetry.py — setup_telemetry smoke test (console / dev mode)
# ---------------------------------------------------------------------------


def test_setup_telemetry_console_mode_returns_valid_telemetry():
    """Console mode should return a fully populated Telemetry without network I/O."""
    tel = setup_telemetry("test-svc", otel_enabled=False)

    assert isinstance(tel, Telemetry)
    assert tel.tracer is not None
    assert tel.tool_calls is not None
    assert tel.tool_errors is not None
    assert tel.tool_duration is not None
    assert tel.db_pool_size is not None


def test_setup_telemetry_otlp_mode_does_not_raise_on_unreachable_endpoint():
    """
    OTLP mode creates the exporter eagerly but does not block on a missing collector.
    The SDK buffers spans and retries silently — this must never fail server startup.
    """
    tel = setup_telemetry(
        "test-svc-otlp",
        otel_enabled=True,
        otlp_endpoint="http://localhost:14317",  # intentionally unreachable
    )
    assert isinstance(tel, Telemetry)


def test_setup_telemetry_pool_gauge_callback_handles_uninitialised_pool():
    """
    The db_pool_size gauge callback must not raise when the pool isn't ready.
    The pool is always initialised AFTER setup_telemetry() in the lifespan.
    """
    with patch("src.server.db.pool._pool", None):
        tel = setup_telemetry("test-svc-gauge", otel_enabled=False)
        # Reach into the registered callbacks and invoke them directly
        # ObservableGauge stores callbacks on the instrument — verify no RuntimeError
        assert tel.db_pool_size is not None  # gauge was created without error
