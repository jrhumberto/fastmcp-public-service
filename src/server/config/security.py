"""
Tool-level allowlist security.
Prevents unauthorized tool access and prompt injection via explicit allowlisting.
"""

import logging
from functools import wraps
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_allowlist: set[str] = set()


def load_allowlist(path: str = "config/allowlist.yaml") -> set[str]:
    """Load allowed tool names from YAML config."""
    allowlist_path = Path(path)
    if not allowlist_path.exists():
        logger.warning(f"Allowlist file not found at {path}. All tools blocked.")
        return set()
    with open(allowlist_path) as f:
        config = yaml.safe_load(f) or {}
    tools = set(config.get("allowed_tools", []))
    logger.info(f"Loaded allowlist with {len(tools)} tools: {tools}")
    return tools


def initialize_allowlist(path: str = "config/allowlist.yaml") -> None:
    global _allowlist
    _allowlist = load_allowlist(path)


def is_allowed(tool_name: str) -> bool:
    return tool_name in _allowlist


def require_allowlist(tool_name: str):
    """Decorator to enforce allowlist on any tool function."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not is_allowed(tool_name):
                logger.warning(f"Blocked access to tool '{tool_name}' — not in allowlist")
                raise PermissionError(
                    f"Tool '{tool_name}' is not permitted. "
                    "Contact your administrator to update the allowlist."
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator
