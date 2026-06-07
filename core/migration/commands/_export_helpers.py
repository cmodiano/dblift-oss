"""Pure-function helpers for ``export-schema``.

Pulled out of :mod:`core.migration.commands.export_schema_command`
so the orchestrator file can stay focused on the
:class:`SchemaExporter` pipeline.

These four helpers are dialect-agnostic transformations that do not
touch a database, a logger or any global state, so they live here as
free functions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from core.sql_model.base import ConstraintType, SqlObject
from core.sql_model.index import Index
from core.sql_model.table import Table


def _get_quirks_from_config(config: Any) -> Any:
    """Resolve quirks from a ``DbliftConfig.database.type``, or ``None``."""
    db_type = getattr(getattr(config, "database", None), "type", None)
    if not db_type or not isinstance(db_type, str):
        return None
    from db.provider_registry import ProviderRegistry

    return ProviderRegistry.get_quirks(db_type)


def _normalize_identifier(identifier: Optional[str]) -> str:
    """Normalize an identifier for comparison (case-insensitive, no quoting)."""
    if not identifier:
        return ""

    normalized = identifier.strip()
    if not normalized:
        return ""

    normalized = normalized.strip("\"'`[]")
    return normalized.lower()


def _normalize_schema_for_dialect(schema: Optional[str], dialect: str) -> str:
    """Normalize a schema name for *dialect*.

    Story 26-9: schema-name normalisation reads ``uppercase_identifiers``
    and ``default_schema_name`` from the plugin's quirks, so this
    function carries no dialect names. Adding a new dialect with a
    different default = override ``default_schema_name`` in its
    ``quirks.py`` — no edit here.
    """
    from db.provider_registry import ProviderRegistry

    quirks = ProviderRegistry.get_quirks((dialect or "").lower())
    if schema and schema.strip():
        val = schema.strip()
        return val.upper() if quirks.uppercase_identifiers else val.lower()
    # None or empty schema — fall back to the dialect's default if any.
    return quirks.default_schema_name or ""


def _remove_redundant_unique_constraints(objects: List[SqlObject]) -> None:
    """Drop UNIQUE constraints whose column set is already covered by a unique index.

    Mutates each ``Table`` in *objects* in place. Without this step the
    exported DDL emits both a UNIQUE INDEX and a UNIQUE CONSTRAINT for
    the same column set, which the database then refuses or silently
    deduplicates.
    """
    if not objects:
        return

    unique_index_names: Dict[Tuple[str, str], Set[str]] = {}
    unique_index_columns: Dict[Tuple[str, str], Set[Tuple[str, ...]]] = {}

    # Gather unique indexes
    for obj in objects:
        if isinstance(obj, Index) and getattr(obj, "unique", False):
            table_name = _normalize_identifier(getattr(obj, "table_name", None))
            if not table_name:
                continue
            table_schema = _normalize_identifier(
                getattr(obj, "table_schema", None) or getattr(obj, "schema", None)
            )
            table_key = (table_schema, table_name)

            index_name = _normalize_identifier(getattr(obj, "name", None))
            if index_name:
                unique_index_names.setdefault(table_key, set()).add(index_name)

            columns = [
                _normalize_identifier(column)
                for column in getattr(obj, "columns", []) or []
                if column
            ]
            if columns:
                unique_index_columns.setdefault(table_key, set()).add(tuple(columns))

    if not unique_index_names and not unique_index_columns:
        return

    # Remove matching unique constraints from tables
    for obj in objects:
        if not isinstance(obj, Table) or not getattr(obj, "constraints", None):
            continue

        table_schema = _normalize_identifier(getattr(obj, "schema", None))
        table_name = _normalize_identifier(getattr(obj, "name", None))
        table_key = (table_schema, table_name)

        name_matches = unique_index_names.get(table_key, set())
        column_matches = unique_index_columns.get(table_key, set())

        if not name_matches and not column_matches:
            continue

        filtered_constraints = []
        for constraint in obj.constraints:
            constraint_type = getattr(constraint, "constraint_type", None)
            if constraint_type == ConstraintType.UNIQUE:
                constraint_name = _normalize_identifier(getattr(constraint, "name", None))
                constraint_columns = tuple(
                    _normalize_identifier(col)
                    for col in getattr(constraint, "column_names", []) or []
                )

                if constraint_name and constraint_name in name_matches:
                    continue
                if constraint_columns and constraint_columns in column_matches:
                    continue

            filtered_constraints.append(constraint)

        obj.constraints = filtered_constraints
