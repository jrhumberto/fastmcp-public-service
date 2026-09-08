"""
@instrument_tool — decorator that wires OTel tracing and metrics into async tool functions.

Decorator order matters. Place @instrument_tool as the OUTERMOST decorator so that
blocked allowlist calls are also counted (PermissionErrors become tool_errors):

    @instrument_tool("search_records")   # outermost — records all attempts
    @require_allowlist("search_records") # inner — may raise PermissionError
    async def search_records(...):
        ...

When telemetry is not initialized (get_telemetry() returns None), the decorator is a
transparent pass-through — zero overhead, safe for unit tests without OTel setup.
"""

import functools
import time
from collections.abc import Callable, Coroutine
from typing import Any

from .context import get_telemetry


def instrument_tool(tool_name: str) -> Callable[..., Any]:
    """
    Decorator factory that instruments an async tool function with:

    - ``mcp.tool.calls``    counter   — incremented on every invocation
    - ``mcp.tool.errors``   counter   — incremented when the tool raises any exception
    - ``mcp.tool.duration`` histogram — recorded in ms on successful return
    - OTel span             trace     — wraps the full execution including allowlist check

    Args:
        tool_name: Attribute value used for all metric and span labels.
    """

    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            tel = get_telemetry()
            if tel is None:
                # Telemetry not initialized — transparent pass-through (unit test mode)
                return await func(*args, **kwargs)

            attrs = {"tool": tool_name}
            tel.tool_calls.add(1, attrs)
            start = time.monotonic()

            with tel.tracer.start_as_current_span(tool_name):
                try:
                    result = await func(*args, **kwargs)
                    tel.tool_duration.record((time.monotonic() - start) * 1000, attrs)
                    return result
                except Exception:
                    tel.tool_errors.add(1, attrs)
                    raise

        return wrapper

    return decorator
