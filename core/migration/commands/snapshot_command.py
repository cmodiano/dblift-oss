"""Core implementation of the snapshot command.

Business logic extracted from cli/snapshot_command.py to respect
the architecture: API → Core → DB (not API → CLI).

This command exports database schema snapshots (JSON model format) from two sources:
1. database-stored: Load the latest snapshot from the database (default)
2. live-database: Capture a new snapshot from live database introspection
"""

import json
import logging
import sys
import traceback
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional, Tuple

from core.logger import DbliftLogger, Log
from core.migration.snapshots.schema_snapshot import SchemaSnapshotPayload
from core.migration.snapshots.schema_snapshot_service import SchemaSnapshotService
from db.provider_capabilities import get_provider_display_url
from db.provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


class SnapshotSource(str, Enum):
    """Source for snapshot data."""

    DATABASE_STORED = "database-stored"
    LIVE_DATABASE = "live-database"


def _json_default(obj: Any) -> Any:
    """Serializer for objects not handled by default json encoder."""
    from datetime import date, datetime, time, timezone

    if isinstance(obj, (datetime, date, time)):
        if isinstance(obj, datetime) and obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.isoformat()
    if isinstance(obj, Enum):
        return getattr(obj, "value", obj.name)
    return str(obj)


def snapshot(
    config: Any,
    output: Optional[str] = None,
    source: str = "database-stored",
    log: Optional[Log] = None,
    provider: Any = None,
    min_confidence: Optional[float] = None,
) -> Tuple[bool, Optional[str]]:
    """Export database schema snapshot to a JSON model file.

    Args:
        config: DBLift configuration object
        output: Output file path for the snapshot JSON model
        source: Source for snapshot data:
            - "database-stored": Load latest snapshot from database (default)
            - "live-database": Capture new snapshot from live database introspection
        log: Optional DbliftLogger instance
        provider: Optional pre-initialized provider. When supplied, it is
            reused instead of calling ``ProviderRegistry.create_provider`` —
            required by the API surface (``DBLiftClient.snapshot``) to avoid
            creating a second provider context inside the same process.
        min_confidence: Optional minimum acceptable overall confidence score
            (0.0-1.0). When set and the captured live-database snapshot
            scores below this value, the command fails with an error
            pointing at the score and the reason (B8-BUG-05). Useful to
            bypass HIGH-only gating when targeting emulators (CosmosDB,
            SQL Server dev) whose metadata views are incomplete.

    Returns:
        Tuple of (success: bool, error_message: Optional[str]).
        error_message is None on success, or a human-readable failure reason.
    """
    start_time = datetime.now()
    _captured_error: List[str] = []

    # Use provided log if available, otherwise use standard logger
    if log:
        _raw_error = log.error
        log_func = log.info
        debug_func = log.debug
    else:
        _raw_error = logger.error  # type: ignore[assignment]
        log_func = logger.info  # type: ignore[assignment]
        debug_func = logger.debug  # type: ignore[assignment]

    def error_func(msg: str, *args: Any, **kwargs: Any) -> None:
        _captured_error[:] = [str(msg)]
        _raw_error(msg, *args, **kwargs)

    try:
        # Validate source
        try:
            source_enum = SnapshotSource(source.lower())
        except ValueError:
            error_func(f"Invalid source '{source}'. Must be one of: database-stored, live-database")
            return False, _captured_error[0]

        # Validate output
        if not output:
            error_func("Output file path is required (--output)")
            return False, _captured_error[0]

        output_path = Path(output)
        if output_path.exists() and not output_path.is_file():
            error_func(f"Output path '{output_path}' exists but is not a file")
            return False, _captured_error[0]

        # Create provider (or reuse the one already owned by a DBLiftClient —
        # spinning up a second Database provider in the same process re-initialises
        # the provider while the first one is still live and deadlocks; B8-BUG-03).
        if provider is None:
            provider = ProviderRegistry.create_provider(config, log=log)
        if not provider.is_connected():
            provider.create_connection()

        # Get snapshot service
        from core.migration.executor.migration_executor import MigrationExecutor

        executor = MigrationExecutor(provider, config, log if log else DbliftLogger())
        snapshot_service: Optional[SchemaSnapshotService] = getattr(
            executor, "snapshot_service", None
        )

        if not snapshot_service:
            error_func("Snapshot service is unavailable")
            return False, _captured_error[0]

        # Build filters list for logging
        filters = [f"--source={source}", f"--output={output}"]

        # Get database name and schema name for header
        database_name = getattr(config.database, "database_name", None) or getattr(
            config.database, "database", None
        )
        schema_name = getattr(config.database, "schema", None)

        # Get database URL for report metadata.
        try:
            database_url = get_provider_display_url(provider, config)
        except Exception as e:
            logger.debug(f"Could not get database URL: {e}")
            database_url = None
        # Mask database URL if we have it
        database_url_masked = None
        if database_url:
            from core.utils.url_masking import mask_database_url

            database_url_masked = mask_database_url(str(database_url))
            debug_func(f"Database URL: {database_url_masked}")
        else:
            debug_func("Could not determine database URL for logging")

        # Print uniform header to console (only if log is console-based)
        if log:
            from core.logger.log import ConsoleLog, MultiLog

            should_print_header = False
            if isinstance(log, MultiLog):
                for log_item in log.logs:
                    if isinstance(log_item, ConsoleLog):
                        should_print_header = True
                        break
            elif isinstance(log, ConsoleLog):
                should_print_header = True

            if should_print_header:
                # Print main header once before first command (only for console)
                from core.logger.log import TextFormatter

                current_module = sys.modules[__name__]

                # Use a module-level flag to track if main header has been printed
                if not hasattr(current_module, "_console_main_header_printed"):
                    current_module._console_main_header_printed = False  # type: ignore[attr-defined]

                if not current_module._console_main_header_printed:
                    from core.migration.commands.base_command import _render_main_header_panel

                    formatter = TextFormatter()
                    main_header = formatter.format_header(schema_name, database_name)
                    if main_header:
                        # Mirror base_command: route the banner to stderr so
                        # ``--format json`` keeps a clean stdout contract.
                        print(  # lint: allow-print  banner fallback
                            _render_main_header_panel(main_header), file=sys.stderr
                        )
                    current_module._console_main_header_printed = True  # type: ignore[attr-defined]

                from rich import box
                from rich.panel import Panel

                from core.logger.console import get_stdout_console
                from core.migration.commands.base_command import _props_text

                lines = []
                if database_name:
                    lines.append(f"Database: {database_name}")
                if schema_name:
                    lines.append(f"Schema: {schema_name}")
                lines.append(f"Database URL: {database_url_masked or '<not available>'}")
                if filters:
                    lines.append(f"Filtering Options: {' '.join(filters)}")
                get_stdout_console().print(
                    Panel(
                        _props_text(*lines),
                        title="DBLIFT COMMAND: SNAPSHOT",
                        box=box.HEAVY,
                        expand=True,
                    )
                )

        # Get snapshot payload based on source
        payload: Optional[SchemaSnapshotPayload] = None

        from core.logger.console import console_status

        if source_enum == SnapshotSource.DATABASE_STORED:
            log_func("Loading latest snapshot from database...")
            with console_status("Loading snapshot from database..."):
                snapshot_data = snapshot_service.load_latest_snapshot()
            if not snapshot_data:
                error_func(
                    "No snapshot found in database. Use --source=live-database to capture one."
                )
                return False, _captured_error[0]
            payload = snapshot_data.payload
            log_func(
                f"Loaded snapshot {snapshot_data.snapshot_id} captured at {snapshot_data.captured_at_iso}"
            )

        elif source_enum == SnapshotSource.LIVE_DATABASE:
            log_func("Capturing snapshot from live database...")
            with console_status("Capturing schema from live database..."):
                payload = snapshot_service.build_live_payload()
            log_func("Snapshot captured successfully")

        if not payload:
            error_func("Failed to obtain snapshot payload")
            return False, _captured_error[0]

        # B8-BUG-05: enforce --min-confidence if provided. The payload's
        # validation metadata is populated by
        # SchemaSnapshotService._validate_snapshot_accuracy() for
        # live-database captures. For database-stored snapshots the metadata
        # is whatever was written at capture time.
        if min_confidence is not None:
            if not (0.0 <= min_confidence <= 1.0):
                error_func(f"--min-confidence must be in [0.0, 1.0]; got {min_confidence}.")
                return False, _captured_error[0]
            validation_meta = (payload.metadata or {}).get("validation", {})
            confidence = validation_meta.get("confidence", {}) if validation_meta else {}
            overall_score = float(confidence.get("overall_score", 0.0) or 0.0)
            confidence_level = confidence.get("confidence_level", "UNKNOWN")
            if overall_score < min_confidence:
                error_func(
                    f"Snapshot confidence {overall_score:.1%} ({confidence_level}) "
                    f"is below the required minimum {min_confidence:.1%}. "
                    f"Lower --min-confidence or investigate the validation warnings."
                )
                _log_command_footer(log_func, False, start_time, log)
                return False, _captured_error[0]
            debug_func(
                f"Snapshot confidence {overall_score:.1%} ({confidence_level}) "
                f">= --min-confidence {min_confidence:.1%}; accepted."
            )

        # Write snapshot to file
        log_func(f"Writing snapshot to {output_path}...")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write as JSON (pretty-printed)
        payload_dict = payload.to_dict()
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(payload_dict, f, indent=2, default=_json_default, ensure_ascii=False)

        log_func(f"Snapshot written successfully to {output_path}")

        _log_command_footer(log_func, True, start_time, log)
        return True, None

    except Exception as e:
        error_func(f"Snapshot operation failed: {str(e)}")
        _log_command_footer(log_func, False, start_time, log)
        debug_func(traceback.format_exc())
        if log and hasattr(log, "error_with_exception"):
            log.error_with_exception("Failed to export snapshot", e)
        return False, _captured_error[0]


def _log_command_footer(
    log_func: Any, success: bool, start_time: datetime, log: Any = None
) -> None:
    """Log command completion footer with execution time.

    Args:
        log_func: Logging function to use
        success: Whether command succeeded
        start_time: Command start time
        log: Optional DbliftLogger instance
    """
    end_time = datetime.now()
    execution_time_ms = int((end_time - start_time).total_seconds() * 1000)

    if execution_time_ms < 1000:
        time_str = f"{execution_time_ms} ms"
    elif execution_time_ms < 60000:
        time_str = f"{execution_time_ms / 1000.0:.2f} s"
    else:
        time_str = f"{execution_time_ms / 60000.0:.2f} min"

    from rich import box
    from rich.panel import Panel
    from rich.text import Text

    from core.logger.console import get_stdout_console

    _STATUS_STYLE = {"SUCCESS": "bold green", "FAILED": "bold red"}
    title = "SUCCESS" if success else "FAILED"
    border_style = _STATUS_STYLE[title]
    message = (
        f"Command SNAPSHOT completed successfully (Execution time: {time_str})"
        if success
        else f"Command SNAPSHOT failed (Execution time: {time_str})"
    )
    get_stdout_console().print(
        Panel(Text(message), title=title, box=box.HEAVY, border_style=border_style, expand=True)
    )

    if log and hasattr(log, "set_command_completed"):
        try:
            log.set_command_completed(success=success, message=message, command_type="SNAPSHOT")
        except Exception as e:
            logger.debug(f"Could not call set_command_completed: {e}")
