"""Small coercion helpers shared by offline planning modules."""

from __future__ import annotations

from typing import Any, Optional


def optional_int(value: Any) -> Optional[int]:
    """Return value as an int when possible, otherwise None."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
