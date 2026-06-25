"""Undo recording with re-apply detection for database providers."""

from __future__ import annotations

import datetime
import os
from typing import Any, Optional

from db.exceptions import DB_OPERATION_EXCEPTIONS
from db.value_utils import to_python_string


class BaseUndoManager:
    """Records undo operations with re-apply detection for providers.

    The manager owns the shared undo flow:

    1. Look up an existing ``UNDO_SQL`` row for the given version.
    2. If one exists and the migration has not been re-applied since, refuse
       to record a second undo (cannot undo twice without reapplying).
    3. Otherwise fetch the latest successful ``SQL``/``PYTHON`` row,
       synthesise an ``UNDO_SQL`` migration record, and write it via
       ``provider.record_migration``.

    Connection state, schema qualification, query execution, and history
    recording are delegated to the owning provider.
    """

    def __init__(self, provider: Any) -> None:
        """Store the owning provider used for queries and history writes."""
        self._provider = provider

    @property
    def _log(self) -> Any:
        return self._provider.log

    def record_undo(
        self,
        schema: str,
        version: str,
        table_name: Optional[str] = None,
        script_name: Optional[str] = None,
    ) -> bool:
        """Record an undo operation in the migration history table."""
        provider = self._provider
        table_name = table_name or "dblift_schema_history"
        if not provider.table_exists(schema, table_name):
            self._log.warning(
                f"Migration history table {table_name} does not exist in schema {schema}"
            )
            return False

        qualified_table = provider.get_schema_qualified_name(schema, table_name)

        check_query = f"""
        SELECT description, installed_rank, script FROM {qualified_table}
        WHERE version = ? AND type = 'UNDO_SQL' AND success = TRUE
        ORDER BY installed_rank DESC
        """

        try:
            results = provider.execute_query(check_query, params=[version])
            if results and len(results) > 0:
                undo_rank = results[0].get("installed_rank", 0)

                reapplied_query = f"""
                SELECT installed_rank FROM {qualified_table}
                WHERE version = ? AND type IN ('SQL', 'PYTHON') AND success = TRUE AND installed_rank > ?
                ORDER BY installed_rank DESC
                """
                reapplied_results = provider.execute_query(
                    reapplied_query, params=[version, undo_rank]
                )

                if not reapplied_results or len(reapplied_results) == 0:
                    self._log.debug(
                        f"Found existing UNDO_SQL record for version {version} - "
                        "cannot undo multiple times without reapplying"
                    )
                    return False
                self._log.debug(
                    f"Version {version} was reapplied after being undone - can undo again"
                )

            query = f"""
            SELECT description, installed_rank FROM {qualified_table}
            WHERE version = ? AND type IN ('SQL', 'PYTHON') AND success = TRUE
            ORDER BY installed_rank DESC
            """
            results = provider.execute_query(query, params=[version])
            if not results or len(results) == 0:
                self._log.warning(
                    f"No successful versioned migration found with version {version} "
                    f"in schema {schema}"
                )
                return False

            description = results[0].get("description", "unknown")
            synthesised_script = script_name or f"U{version}__{description}.sql"

            undo_info = {
                "script": synthesised_script,
                "version": version,
                "description": description,
                "type": "UNDO_SQL",
                # Batch-6 BUG-02: ``checksum`` is INT in PostgreSQL/MySQL/etc.
                # Typed NULL on this column breaks strict drivers. ``0`` is the
                # established sentinel for "no checksum" (see migration_validator).
                "checksum": 0,
                "success": True,
                "execution_time": 0,
                "installed_on": datetime.datetime.now(),
                "installed_by": os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
            }

            provider.record_migration(schema, undo_info, table_name)
            self._log.debug(f"Recorded undo operation for version {version} in schema {schema}")
            return True

        except DB_OPERATION_EXCEPTIONS as e:
            error_msg = f"Error recording undo in schema {schema}: {to_python_string(e)}"
            self._log.error_with_exception(error_msg, e)
            raise


__all__ = ["BaseUndoManager"]
