"""
Diff command implementation.

Orchestrator for the ``diff`` CLI command. The heavy lifting lives in the
companion modules (PR-G5):
- ``_diff_object_specs``  : ``_OBJECT_TYPE_SPECS`` dispatcher table
- ``_diff_snapshot``      : ``run_snapshot_diff`` comparator wiring
- ``_diff_output``        : per-object-type tree/panel renderers
"""

import copy
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from config import DbliftConfig

if TYPE_CHECKING:
    from core.migration.journals.migration_journal import MigrationJournal
    from core.migration.placeholders.placeholder_service import PlaceholderService
from core.logger import Log
from core.logger.results import DiffResult
from core.migration.commands._diff_output import (
    DIFF_OBJECT_TYPE_LOGGERS,
    log_diff_footer,
    log_diff_header,
)
from core.migration.commands._diff_snapshot import run_snapshot_diff
from core.migration.executor.execution_engine import ExecutionEngine
from core.migration.executor.migration_helpers import MigrationHelpers
from core.migration.history.migration_history_manager import MigrationHistoryManager
from core.migration.rules.migration_rules import MigrationRules
from core.migration.scripting.migration_script_manager import MigrationScriptManager
from core.migration.snapshots import SchemaSnapshotService
from core.migration.state.migration_state import MigrationState
from core.migration.state.migration_state_manager import MigrationStateManager
from core.migration.ui.migration_ui import MigrationUI
from core.sql_validator.migration_validator import MigrationValidator
from db.base_provider import BaseProvider
from db.provider_capabilities import ensure_provider_connection

from .base_command import BaseCommand, BaseCommandContext


class DiffCommand(BaseCommand):
    """Handles the 'diff' command execution."""

    _has_own_console_footer = True  # log_diff_footer renders the SUMMARY panel

    def __init__(
        self,
        ctx_or_config: Optional[Union[BaseCommandContext, DbliftConfig]] = None,
        log: Optional[Log] = None,
        provider: Optional[BaseProvider] = None,
        script_manager: Optional[MigrationScriptManager] = None,
        history_manager: Optional[MigrationHistoryManager] = None,
        validator: Optional[MigrationValidator] = None,
        execution_engine: Optional[ExecutionEngine] = None,
        migration_helpers: Optional[MigrationHelpers] = None,
        state_manager: Optional[MigrationStateManager] = None,
        migration_ui: Optional[MigrationUI] = None,
        migration_rules: Optional[MigrationRules] = None,
        journal: Optional["MigrationJournal"] = None,
        placeholder_service: Optional["PlaceholderService"] = None,
        snapshot_service: Optional[SchemaSnapshotService] = None,
        config: Optional[DbliftConfig] = None,
    ):
        """Initialize diff command.

        Args:
            ctx_or_config: A :class:`~.base_command.BaseCommandContext` (preferred)
                or the application config (legacy).
            snapshot_service: Optional snapshot service
            (remaining args are legacy; ignored when ctx provided)
        """
        super().__init__(
            ctx_or_config,
            log=log,
            provider=provider,
            script_manager=script_manager,
            history_manager=history_manager,
            validator=validator,
            execution_engine=execution_engine,
            migration_helpers=migration_helpers,
            state_manager=state_manager,
            migration_ui=migration_ui,
            migration_rules=migration_rules,
            journal=journal,
            placeholder_service=placeholder_service,
            config=config,
        )
        self.snapshot_service = snapshot_service

    def execute(
        self,
        scripts_dir: Path,
        target_version: Optional[str] = None,
        tags: Optional[str] = None,
        exclude_tags: Optional[str] = None,
        versions: Optional[str] = None,
        exclude_versions: Optional[str] = None,
        ignore_unmanaged: bool = False,
        recursive: bool = True,
        additional_dirs: Optional[List[Path]] = None,
        dir_recursive_map: Optional[Dict[Path, bool]] = None,
        snapshot_model_path: Optional[Path] = None,
    ) -> DiffResult:
        """Compare applied migrations against live database schema for drift detection.

        Args:
            scripts_dir: Directory containing migration scripts
            target_version: Compare only up to this version
            tags: Compare only migrations with these tags
            exclude_tags: Exclude migrations with these tags
            versions: Compare only specific versions
            exclude_versions: Exclude specific versions
            ignore_unmanaged: Hide unmanaged objects section
            recursive: Search scripts directory recursively
            additional_dirs: Additional script directories
            dir_recursive_map: Optional mapping of directory paths to their recursive settings
            snapshot_model_path: Optional path to a snapshot model file to compare against

        Returns:
            DiffResult containing comparison results
        """
        result = DiffResult()
        # source_type is refined later based on actual source (snapshot file vs stored snapshot).
        result.source_type = "Snapshot"
        db_type = (self.config.database.type or "Unknown").upper()
        result.target_type = f"{db_type} Database"

        # Populate database connection information
        try:
            self._populate_database_info(result)
        except Exception as db_info_error:
            # In tests, database info population might fail with Mock objects - log and continue
            self.log.debug(f"Could not populate database info: {db_info_error}")

        try:
            # Ensure provider connection is active before any database operations
            # This is critical as various operations may close the connection
            try:
                ensure_provider_connection(self.provider)
                self.log.debug("Established provider connection for diff command")
            except Exception as e:
                self.log.error(f"Failed to establish database connection: {e}")
                result.set_error(f"Database connection failed: {e}")
                self._log_command_completion("diff", result)
                result.complete()
                return result

            # Ensure schema and history table exist (this establishes the connection)
            try:
                self.history_manager.create_schema_and_history_table(create_schema=False)
            except Exception as schema_error:
                # In tests, schema creation might fail with Mock objects - log and continue
                self.log.debug(
                    f"Could not create schema/history table (may be expected in tests): {schema_error}"
                )

            # Log command execution with connection info (after connection is established)
            # Convert list parameters to strings for logging (if they came from API)
            tags_str = ",".join(tags) if isinstance(tags, list) else tags
            exclude_tags_str = (
                ",".join(exclude_tags) if isinstance(exclude_tags, list) else exclude_tags
            )
            versions_str = ",".join(versions) if isinstance(versions, list) else versions
            exclude_versions_str = (
                ",".join(exclude_versions)
                if isinstance(exclude_versions, list)
                else exclude_versions
            )

            try:
                self._log_command_header_update(
                    "diff",
                    target_version=target_version,
                    tags=tags_str,
                    exclude_tags=exclude_tags_str,
                    versions=versions_str,
                    exclude_versions=exclude_versions_str,
                    ignore_unmanaged=ignore_unmanaged,
                )
            except Exception as header_error:
                # In tests, header update might fail with Mock objects - log and continue
                self.log.debug(f"Could not update command header: {header_error}")

            self.log.debug("Starting drift detection...")
            self.log.debug("Comparing applied migrations vs live database schema")

            try:
                migration_state = self.state_manager.build_state(
                    scripts_dir,
                    recursive=recursive,
                    additional_dirs=additional_dirs,
                    dir_recursive_map=dir_recursive_map,
                    target_version=target_version,
                    tags=tags,
                    exclude_tags=exclude_tags,
                    versions=versions,
                    exclude_versions=exclude_versions,
                )
            except Exception as e:
                # If build_state fails, create empty state
                self.log.debug(f"Could not build migration state: {e}")
                migration_state = MigrationState()

            if not getattr(migration_state, "applied_objects", []):
                self.log.warn("No migrations have been applied yet")
                result.success = True
                self._log_command_completion("diff", result)
                result.complete()
                return result

            snapshot_payload = None
            snapshot_metadata: Dict[str, Any] = {}

            def _snapshot_error(message: str) -> DiffResult:
                self.log.error(message)
                result.set_error(message)
                self._log_command_completion("diff", result)
                result.complete()
                return result

            if snapshot_model_path:
                if not self.snapshot_service:
                    return _snapshot_error(
                        "Snapshot service is not available to load the specified snapshot model."
                    )
                try:
                    payload = self.snapshot_service.load_snapshot_payload_from_path(
                        snapshot_model_path
                    )
                    snapshot_payload = payload
                    snapshot_metadata = copy.deepcopy(payload.metadata)
                    snapshot_metadata.setdefault("snapshot", {}).update(
                        {"source": "file", "path": str(snapshot_model_path)}
                    )
                    result.source_type = "Snapshot Model"
                except Exception as exc:
                    return _snapshot_error(
                        f"Failed to load snapshot model file '{snapshot_model_path}': {exc}"
                    )
            else:
                if not self.snapshot_service:
                    return _snapshot_error(
                        "No schema snapshot is available and snapshot capture is disabled."
                    )
                try:
                    snapshot = self.snapshot_service.load_latest_snapshot()
                except Exception as exc:
                    return _snapshot_error(f"Failed to load latest schema snapshot: {exc}")

                if snapshot:
                    snapshot_payload = snapshot.payload
                    snapshot_metadata = copy.deepcopy(snapshot.metadata)
                    snapshot_metadata.setdefault("snapshot", {}).setdefault("source", "database")
                    result.source_type = "Stored Snapshot"
                else:
                    db_type = (getattr(self.config.database, "type", "") or "").lower()
                    from db.provider_registry import ProviderRegistry

                    if ProviderRegistry.get_quirks(db_type).is_nosql:
                        return _snapshot_error(
                            "No schema snapshot found. Run migrations to capture "
                            "a NoSQL database-stored snapshot, or provide "
                            "--snapshot-model to diff against a declarative schema model."
                        )
                    return _snapshot_error(
                        "No schema snapshot found. Run migrations or provide --snapshot-model to diff against a schema model."
                    )

            snapshot_result = run_snapshot_diff(
                result=result,
                snapshot_payload=snapshot_payload,
                snapshot_metadata=snapshot_metadata,
                ignore_unmanaged=ignore_unmanaged,
                snapshot_service=self.snapshot_service,
                provider=self.provider,
                config=self.config,
                log=self.log,
            )
            if snapshot_result is None:
                return _snapshot_error("Schema snapshot comparison failed.")

            # Display validation results if available in metadata
            self._log_validation_results(snapshot_metadata)

            self._log_diff_summary(snapshot_result)
            if snapshot_result.has_unmanaged_objects and not ignore_unmanaged:
                self.log.info(
                    f"\nUnmanaged objects detected: {snapshot_result.get_unmanaged_count()} (use --ignore-unmanaged to hide)"
                )
            self._log_command_completion("diff", snapshot_result)
            snapshot_result.complete()
            return snapshot_result

        except Exception as e:
            # Capture full traceback for debugging
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            # Log traceback to debug
            if hasattr(self.log, "debug"):
                self.log.debug(f"Diff exception traceback:\n{tb_str}")
            self.log.error(f"Diff operation failed: {e}")
            result.set_error(f"Diff operation failed: {e}")
            self._log_command_completion("diff", result)
            result.complete()
            return result

    def _log_diff_summary(self, result: DiffResult) -> None:
        """Log comprehensive diff summary showing only differences with details.

        Args:
            result: DiffResult with schema differences
        """
        if not isinstance(result, DiffResult) or not result.schema_diff:
            return
        schema_diff = result.schema_diff
        log_diff_header(self.log, result)
        for logger_fn in DIFF_OBJECT_TYPE_LOGGERS:
            logger_fn(self.log, schema_diff)
        log_diff_footer(self.log, result)

    def _log_validation_results(self, snapshot_metadata: Dict[str, Any]) -> None:
        """Log validation and introspection quality results if available.

        Args:
            snapshot_metadata: Snapshot metadata dictionary that may contain validation results
        """
        if not snapshot_metadata:
            return

        validation_metadata = snapshot_metadata.get("validation")
        introspection_quality = snapshot_metadata.get("introspection_quality")

        if not validation_metadata and not introspection_quality:
            return

        self.log.info("")
        self.log.info("=" * 80)
        self.log.info("INTROSPECTION QUALITY & VALIDATION")
        self.log.info("=" * 80)

        # Display introspection quality
        if introspection_quality:
            self.log.info("\nIntrospection Quality:")
            completeness = introspection_quality.get("completeness_score", 0)
            confidence = introspection_quality.get("confidence_level", "UNKNOWN")
            error_count = introspection_quality.get("error_count", 0)
            warning_count = introspection_quality.get("warning_count", 0)

            self.log.info(f"  Completeness: {completeness:.1%}")
            self.log.info(f"  Confidence Level: {confidence}")
            if error_count > 0:
                self.log.warning(f"  Errors: {error_count}")
            if warning_count > 0:
                self.log.warning(f"  Warnings: {warning_count}")
            if error_count == 0 and warning_count == 0:
                self.log.info("  ✓ No errors or warnings")

        # Display validation results
        if validation_metadata:
            self.log.info("\nValidation Results:")
            overall_passed = validation_metadata.get("overall_passed", True)
            confidence = validation_metadata.get("confidence", {})
            total_errors = validation_metadata.get("total_errors", 0)
            total_warnings = validation_metadata.get("total_warnings", 0)

            status_icon = "✓" if overall_passed else "✗"
            status_text = "PASSED" if overall_passed else "FAILED"
            self.log.info(f"  Overall Status: {status_icon} {status_text}")

            if confidence:
                confidence_level = confidence.get("confidence_level", "UNKNOWN")
                overall_score = confidence.get("overall_score", 0)
                self.log.info(f"  Confidence: {confidence_level} ({overall_score:.1%})")

                # Show breakdown if available
                breakdown = confidence.get("breakdown", {})
                if breakdown:
                    # The `error_rate` key stores a quality score where 1.0 means "no errors";
                    # rendering it as "Error_Rate: 100.0%" reads like "100% errors". Display
                    # it as "Success_Rate" instead (BUG-06). The dict key stays unchanged
                    # for backwards compatibility with persisted reports/JSON consumers.
                    label_overrides = {"error_rate": "Success_Rate"}
                    self.log.info("  Score Breakdown:")
                    for component, details in breakdown.items():
                        score = details.get("score", 0)
                        label = label_overrides.get(component, component.title())
                        self.log.info(f"    {label}: {score:.1%}")

            if total_errors > 0:
                self.log.warning(f"  Validation Errors: {total_errors}")
            if total_warnings > 0:
                self.log.warning(f"  Validation Warnings: {total_warnings}")
            if total_errors == 0 and total_warnings == 0:
                self.log.info("  ✓ No validation issues")
        self.log.info("=" * 80)
