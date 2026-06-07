"""Migration-file metadata helpers for ``export-schema``.

Pulled out of :mod:`core.migration.commands.export_schema_command` to
keep the orchestrator module focused. These four functions are pure /
nearly-pure side-effect-free helpers:

- ``_generate_migration_header`` / ``_generate_migration_footer``
  produce the SQL comment block that wraps each generated script.
- ``_populate_export_result_metadata`` enriches the
  :class:`ExportSchemaResult` with database connection info pulled
  from the provider.
- ``_log_command_footer`` writes the closing banner of the export
  command to whatever logger the caller passes in.

``cli/snapshot_command.py`` historically imports
``_log_command_footer`` from
:mod:`core.migration.commands.export_schema_command`; the original
module re-exports it from here so that import path stays valid.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Optional

from db.provider_capabilities import ensure_provider_connection, get_provider_driver_display

logger = logging.getLogger(__name__)


def _generate_migration_header(
    file_name: str,
    object_count: int,
    dialect: str,
    description: Optional[str] = None,
) -> str:
    """Generate the comment block prepended to every exported migration file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_lines = [
        "-- Migration: Schema Export",
        f"-- File: {file_name}",
    ]

    if description:
        header_lines.append(f"-- Description: {description}")
    else:
        header_lines.append("-- Description: Exported database schema")

    header_lines.extend(
        [
            f"-- Generated: {timestamp}",
            f"-- Source: Existing database schema ({dialect})",
            "--",
            "-- Note: These objects already exist in the database.",
            "--       This migration will be marked as executed without running.",
            "--       Run with: dblift migrate --mark-as-executed",
            "--",
            f"-- Object count: {object_count}",
            "--",
        ]
    )
    try:
        from db.provider_registry import ProviderRegistry

        quirks = ProviderRegistry.get_quirks((dialect or "").lower())
        header_lines.extend(quirks.script_header_session_init())
    except Exception as exc:
        logger.debug("Could not add dialect session init to export header: %s", exc)

    return "\n".join(header_lines)


def _generate_migration_footer() -> str:
    """Return the comment block appended to every exported migration file."""
    return "\n-- End of migration\n"


def _populate_export_result_metadata(
    result: Any,
    provider: Any,
    schema_version: Optional[str],
    database_url_masked: Optional[str],
    database_url: Optional[str] = None,
) -> None:
    """Populate database connection information on *result*.

    Mutates *result* in place. Connection lookup failures are swallowed
    at debug level — metadata is informative, not part of the export
    contract.
    """
    try:
        # Set schema version
        if schema_version:
            result.current_schema_version = schema_version

        # Set database URL
        if database_url_masked:
            result.database_url_masked = database_url_masked

        # Extract server name from original URL (before masking)
        if database_url:
            match = re.search(r"://([^:/]+)", str(database_url))
            if match:
                result.server_name = match.group(1)
        elif database_url_masked:
            # Fallback to masked URL if original not available
            match = re.search(r"://([^:/]+)", database_url_masked)
            if match:
                result.server_name = match.group(1)

        # Get database version
        if hasattr(provider, "get_database_version"):
            try:
                ensure_provider_connection(provider)
                result.db_version = provider.get_database_version()
            except Exception as e:
                logger.debug(f"db_version not available: {e}")

        # Get driver info from plugin-declared quirks.
        try:
            result.native_driver = get_provider_driver_display(provider)
        except Exception as e:
            logger.debug(f"native_driver not available: {e}")
    except Exception as e:
        logger.debug(f"Metadata population failed, continuing anyway: {e}")


def _log_command_footer(
    log_func: Any, success: bool, start_time: datetime, log: Any = None
) -> None:
    """Write the closing banner of an EXPORT-SCHEMA run via *log_func*."""
    end_time = datetime.now()
    execution_time_ms = int((end_time - start_time).total_seconds() * 1000)

    if execution_time_ms < 1000:
        time_str = f"{execution_time_ms} ms"
    elif execution_time_ms < 60000:
        time_str = f"{execution_time_ms / 1000.0:.2f} s"
    else:
        time_str = f"{execution_time_ms / 60000.0:.2f} min"

    if success:
        message = f"Command EXPORT-SCHEMA completed successfully (Execution time: {time_str})"
    else:
        message = f"Command EXPORT-SCHEMA failed (Execution time: {time_str})"

    log_func("-" * 80)
    log_func(message)
    log_func("=" * 80)

    if log and hasattr(log, "set_command_completed"):
        try:
            # Try to get result from log if it was set earlier
            result = getattr(log, "_export_schema_result", None)
            log.set_command_completed(
                success=success, message=message, command_type="EXPORT-SCHEMA", result=result
            )
        except Exception as e:
            logger.debug(f"Could not call set_command_completed: {e}")
