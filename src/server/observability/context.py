"""
Telemetry singleton — module-level access to the shared Telemetry instance.

Mirrors the db/pool.py singleton pattern:
  - set_telemetry() is called once in main.py immediately after setup_telemetry()
  - get_telemetry() is called by @instrument_tool at each tool invocation
  - Returns None when not yet initialized so decorators can no-op safely in tests
"""

from .telemetry import Telemetry

_telemetry: Telemetry | None = None


def set_telemetry(t: Telemetry | None) -> None:
    """Store (or clear) the server-wide Telemetry instance. Called from main.py lifespan."""
    global _telemetry
    _telemetry = t


def get_telemetry() -> Telemetry | None:
    """
    Return the active Telemetry instance, or None if not initialized.
    Callers should treat None as 'skip instrumentation' — never raise.
    """
    return _telemetry
