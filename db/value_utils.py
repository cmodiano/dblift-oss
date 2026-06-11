"""Small value-conversion helpers shared by providers."""

import json
from typing import Any, Optional


def to_python_string(value: Any) -> Optional[str]:
    """Return a Python string, or None if value is None."""
    if value is None:
        return None
    return str(value)


def get_row_value(row: Any, key: str, default: Any = None) -> Any:
    """Return a value from mapping-like or attribute-like database rows."""
    if row is None:
        return default
    if isinstance(row, dict):
        if key in row:
            return row[key]
        lower_key = key.lower()
        upper_key = key.upper()
        if lower_key in row:
            return row[lower_key]
        if upper_key in row:
            return row[upper_key]
        for row_key, value in row.items():
            if str(row_key).lower() == lower_key:
                return value
        return default
    return getattr(row, key, default)


def parse_json_array(value: Any) -> list[Any]:
    """Parse a JSON array value, returning an empty list for invalid input."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []
