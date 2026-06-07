"""Core implementation of the export-schema command.

Business logic extracted from cli/export_schema_command.py to respect
the architecture: API → Core → DB (not API → CLI).
"""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from core.introspection import IntrospectorFactory
from core.logger import DbliftLogger, Log, NullLog
from core.migration.commands._schema_export_types import (
    _GLOBAL_TYPES,
    _OBJECT_TYPE_KEYS,
    _SCHEMA_FILTERED_TYPES,
    ExportExecutionState,
    ExportSchemaOptions,
    _ExportAborted,
)
from core.migration.snapshots.schema_snapshot import SchemaSnapshotPayload
from core.migration.snapshots.schema_snapshot_service import SchemaSnapshotService
from core.sql_generator import SqlGeneratorFactory
from core.sql_generator.options import OrganizationStrategy, ScriptOptions
from core.sql_model.base import SqlObject, get_object_type_name
from core.sql_model.dialect import SCHEMA_OPTIONAL_DIALECTS
from db.provider_capabilities import ensure_provider_connection, get_provider_display_url
from db.provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


class SchemaExporter:
    """Encapsulates the logic of export_schema() as a class for easier testing and maintenance."""

    def __init__(
        self,
        config: Any,
        options: ExportSchemaOptions,
        executor: Any = None,
        log: Any = None,
        provider: Any = None,
    ) -> None:
        """Bind config, options, and (optionally) an externally-managed executor/provider/log."""
        self.config = config
        self.options = options
        self.executor = executor
        self.log = log if log is not None else NullLog()
        self.start_time = datetime.now()

        # Mutable pipeline state (encapsulated in a single dataclass — SIMP-39)
        self.state = ExportExecutionState()
        # B8-BUG-03: allow caller to inject an already-initialised provider so
        # we don't spin up a second provider context in the same process.
        if provider is not None:
            self.state.provider = provider

    def run(self) -> bool:
        """Thin coordinator that calls all methods in order."""
        self._print_main_banner()
        try:
            if not self._validate_options():
                # BUG-05: options-validation failure used to return False without
                # logging the failure footer — set_command_completed never fired,
                # so CLI reported success (exit 0) despite the printed error.
                _log_command_footer(self.log.info, False, self.start_time, self.log)
                return False

            if not self._setup_infrastructure():
                _log_command_footer(self.log.info, False, self.start_time, self.log)
                return False

            self._print_header()

            all_objects, typed_lists = self._load_schema_objects()

            filtered_objects, typed_lists = self._apply_exclusions_and_filters(
                all_objects, typed_lists
            )

            return self._generate_and_write(filtered_objects, typed_lists)

        except _ExportAborted:
            # Error already logged by the method that raised; just return False
            _log_command_footer(self.log.info, False, self.start_time, self.log)
            return False

        except Exception as exc:
            self.log.error(f"Failed to export schema: {exc}")
            _log_command_footer(self.log.info, False, self.start_time, self.log)
            self.log.error_with_exception("Failed to export schema", exc)

            return False

    def _validate_options(self) -> bool:
        """Validate options and build filters list."""
        options = self.options
        output = options.output
        output_dir = options.output_dir
        split_by_type = options.split_by_type
        source = options.source
        snapshot_model = options.snapshot_model
        tables = options.tables
        types = options.types
        schema = options.schema
        unmanaged_only = options.unmanaged_only
        managed_only = options.managed_only
        # Validate source
        source_lower = source.lower() if source else "live-database"
        valid_sources = ["database-model", "file-model", "live-database"]
        if source_lower not in valid_sources:
            self.log.error(f"Invalid source '{source}'. Must be one of: {', '.join(valid_sources)}")
            return False

        # Build filters list (only actual filters that change what data is included/excluded, not output paths or formatting)
        # Only include non-default values to avoid cluttering the output
        filters = []
        # Source is a filter (changes where data comes from) - only show if not default
        if source_lower != "live-database":
            filters.append(f"--source={source_lower}")
        # Tables filter (changes what tables are included)
        if tables:
            filters.append(f"--tables={tables}")
        # Types filter (changes what object types are included)
        if types:
            filters.append(f"--types={types}")
        # Schema filter (changes what schema is included)
        if schema:
            filters.append(f"--schema={schema}")
        # Unmanaged/managed filters (changes what objects are included)
        if unmanaged_only:
            filters.append("--unmanaged-only")
        if managed_only:
            filters.append("--managed-only")
        # Snapshot model is a filter when source=file-model (changes data source)
        if snapshot_model and source_lower == "file-model":
            filters.append(f"--snapshot-model={snapshot_model}")
        # Note: output, output-dir, split-by-type, include-drops, description are NOT filters
        # They are output/formatting options, not data filters
        self.state.filters = filters

        # Validate source-specific requirements
        if source_lower == "file-model":
            if not snapshot_model:
                self.log.error("--snapshot-model is required when --source=file-model")
                return False
            snapshot_path = Path(snapshot_model)
            if not snapshot_path.exists():
                self.log.error(f"Snapshot model file not found: {snapshot_path}")
                return False
            if not snapshot_path.is_file():
                self.log.error(f"Snapshot model path is not a file: {snapshot_path}")
                return False

        # Validate output options
        if not output and not output_dir:
            self.log.error("Either --output or --output-dir must be specified")
            return False

        if split_by_type and not output_dir:
            self.log.error("--split-by-type requires --output-dir")
            return False

        if output and output_dir:
            self.log.error("Cannot specify both --output and --output-dir")
            return False

        if unmanaged_only and managed_only:
            self.log.error("Cannot specify both --unmanaged-only and --managed-only")
            return False

        # --versions/--exclude-versions/--target-version/--tags/--exclude-tags without
        # --managed-only/--unmanaged-only used to be ignored. They now restrict the export to
        # managed objects that match the filters, so no warning is needed.

        return True

    def _setup_infrastructure(self) -> bool:
        """Create executor, provider, snapshot service, get schema version, target schema, dialect, database URL."""
        config = self.config
        options = self.options
        schema = options.schema
        source = options.source
        source.lower() if source else "live-database"
        log = self.log

        # Use provided executor or create a temporary one
        if not self.executor:
            from core.migration.executor.migration_executor import MigrationExecutor

            dblift_log_temp = DbliftLogger()
            provider_temp = ProviderRegistry.create_provider(config, log=dblift_log_temp)
            self.executor = MigrationExecutor(provider_temp, config, log=dblift_log_temp)

        executor_temp = self.executor

        # Ensure the executor has an active connection
        if hasattr(executor_temp, "provider") and hasattr(
            executor_temp.provider, "_ensure_connection"
        ):
            try:
                executor_temp.provider._ensure_connection()
            except Exception as e:
                logger.debug(f"Could not ensure executor connection: {e}")

        self.state.snapshot_service = cast(
            Optional[SchemaSnapshotService],
            getattr(executor_temp, "snapshot_service", None),
        )

        # Get schema version using state manager
        schema_version = None
        try:
            from core.migration.state.migration_state_manager import MigrationStateManager

            log_candidate = executor_temp.log if hasattr(executor_temp, "log") else None
            if log_candidate is None and log is not None:
                log_candidate = log
            if log_candidate is None:
                log_candidate = DbliftLogger()

            state_manager = MigrationStateManager(
                cast(Log, log_candidate),
                executor_temp.history_manager,
                executor_temp.script_manager,
                executor_temp.rules,
            )
            applied_migrations = executor_temp.history_manager.get_applied_migrations()
            if applied_migrations:
                current_version = state_manager.get_current_version(applied_migrations)
                schema_version = current_version if current_version else None
        except Exception as e:
            logger.debug(f"Schema version not available: {e}")
        self.state.schema_version = schema_version

        # Get schema name
        target_schema = schema or getattr(config.database, "schema", None)
        db_type = str(getattr(config.database, "type", "") or "").lower()
        # B8-BUG-02: SQLite has no schema concept — every user table lives in
        # "main". If the caller passes --db-schema (common when the same config
        # block is reused across dialects), the user-supplied value would be
        # forwarded to sqlite_master filters that return 0 rows and the export
        # would silently report an empty database. Force "main" for SQLite and
        # warn once so the mismatch is visible.
        _quirks_for_schema = ProviderRegistry.get_quirks((db_type or "").lower())
        # File-based dialects (SQLite) have a single fixed schema and ignore
        # user-supplied --db-schema. Identified by the combination of
        # url_optional_when_file_path_given (file-based) AND a default schema name.
        if (
            _quirks_for_schema.url_optional_when_file_path_given
            and _quirks_for_schema.default_schema_name
        ):
            if (
                target_schema
                and target_schema.lower() != _quirks_for_schema.default_schema_name.lower()
            ):
                self.log.warning(
                    f"Dialect '{db_type}' uses a fixed schema; ignoring --db-schema "
                    f"'{target_schema}' and using '{_quirks_for_schema.default_schema_name}'."
                )
            target_schema = _quirks_for_schema.default_schema_name
        elif not target_schema:
            if db_type not in SCHEMA_OPTIONAL_DIALECTS:
                self.log.error("Database schema is required")
                return False
            # CosmosDB ignores the schema argument entirely.
            target_schema = ""
        self.state.target_schema = target_schema

        # Get dialect early (used for error messages and empty file creation)
        self.state.dialect = config.database.type.lower()

        # Use executor's provider if available, otherwise create one
        # B8-BUG-03: if a provider was injected via the constructor it is
        # already stored on self.state — don't overwrite it with a new one.
        if self.state.provider is not None:
            pass
        elif executor_temp and hasattr(executor_temp, "provider"):
            self.state.provider = executor_temp.provider
        else:
            dblift_log = DbliftLogger()
            self.state.provider = ProviderRegistry.create_provider(config, log=dblift_log)

        # Ensure provider connection is established
        # This is needed for _get_managed_objects when managed_only/unmanaged_only is used
        if self.state.provider is None:
            raise RuntimeError("provider is not initialized")
        ensure_provider_connection(self.state.provider)

        # Get database URL for report metadata.
        try:
            database_url = get_provider_display_url(self.state.provider, self.config)
        except Exception as e:
            logger.debug(f"Could not get database URL: {e}")
            database_url = None

        # Mask database URL if we have it
        self.state.database_url = database_url
        if database_url:
            from core.utils.url_masking import mask_database_url

            self.state.database_url_masked = mask_database_url(str(database_url))
            self.log.debug(f"Database URL: {self.state.database_url_masked}")
        else:
            self.state.database_url_masked = None
            self.log.debug("Could not determine database URL for logging")

        return True

    def _print_main_banner(self) -> None:
        """Print the DBLIFT MIGRATION LOG banner. Safe to call before validation or infrastructure."""
        from core.logger.log import ConsoleLog, MultiLog

        log = self.log
        should_print = False
        if isinstance(log, MultiLog):
            for log_item in log.logs:
                if isinstance(log_item, ConsoleLog):
                    should_print = True
                    break
        elif isinstance(log, ConsoleLog):
            should_print = True
        if not should_print:
            return

        from core.migration.commands import base_command as _bc_mod
        from core.migration.commands.base_command import _render_main_header_panel

        if not getattr(_bc_mod, "_console_main_header_printed", False):
            from core.logger.log import LogLevel, TextFormatter

            formatter = TextFormatter()
            main_header = formatter.format_header()
            if main_header:
                # Same sink and level filtering as `_print_header` (ConsoleLog.console_print).
                log.console_print(_render_main_header_panel(main_header), level=LogLevel.INFO)
            _bc_mod._console_main_header_printed = True  # type: ignore[attr-defined]

    def _print_header(self) -> None:
        """Print console header if log is console-based."""
        log = self.log
        if not log:
            return

        from core.logger.log import ConsoleLog, MultiLog

        should_print_header = False
        if isinstance(log, MultiLog):
            for log_item in log.logs:
                if isinstance(log_item, ConsoleLog):
                    should_print_header = True
                    break
        elif isinstance(log, ConsoleLog):
            should_print_header = True

        if not should_print_header:
            return

        options = self.options
        database_name = getattr(self.config.database, "database_name", None) or getattr(
            self.config.database, "database", None
        )
        schema_name = self.state.target_schema
        snapshot_model = options.snapshot_model

        from rich import box
        from rich.panel import Panel

        from core.logger.console import render_panel_to_str
        from core.migration.commands.base_command import _props_text

        lines = []
        if database_name:
            lines.append(f"Database: {database_name}")
        if schema_name:
            lines.append(f"Schema: {schema_name}")
        if snapshot_model:
            lines.append(f"Snapshot Model: {snapshot_model}")
        lines.append(f"Schema Version: {self.state.schema_version or '<none>'}")
        lines.append(f"Database URL: {self.state.database_url_masked or '<not available>'}")
        if self.state.filters:
            lines.append(f"Filtering Options: {' '.join(self.state.filters)}")
        panel = Panel(
            _props_text(*lines), title="DBLIFT COMMAND: EXPORT-SCHEMA", box=box.HEAVY, expand=True
        )
        log.console_print(panel)
        log.file_only_info(render_panel_to_str(panel, width=80))

    def _normalize_object_schema(self, obj_schema: Optional[str]) -> str:
        """Normalize object schema for comparison."""
        return _normalize_schema_for_dialect(obj_schema, self.config.database.type or "")

    def _schema_matches(self, obj: SqlObject, target_schema_normalized_for_filter: str) -> bool:
        """Check if object's schema matches target schema."""
        if not target_schema_normalized_for_filter:
            # If no target schema specified, accept all schemas
            return True
        obj_schema_normalized = self._normalize_object_schema(obj.schema)
        matches = obj_schema_normalized == target_schema_normalized_for_filter
        if not matches:
            self.log.debug(
                f"Filtering out {get_object_type_name(obj)} "
                f"{obj.name} from schema '{obj_schema_normalized}' (target: '{target_schema_normalized_for_filter}')"
            )
        return matches

    def _load_schema_objects(self) -> Tuple[List[SqlObject], Dict[str, List[Any]]]:
        """Orchestrator: load schema objects from snapshot or live introspection."""
        source_lower = (self.options.source or "live-database").lower()
        target_schema: str = cast(str, self.state.target_schema)

        if source_lower in ("database-model", "file-model"):
            schema_payload = self._load_snapshot_payload(source_lower)
            all_objects, typed_lists = self._introspect_snapshot_objects(schema_payload)
        elif source_lower == "live-database":
            schema_payload = None
            schema_data = self._introspect_live_objects(target_schema)
            target_normalized = _normalize_schema_for_dialect(
                target_schema, self.config.database.type or ""
            )
            all_objects, typed_lists = self._build_object_type_index(schema_data, target_normalized)
        else:
            self.log.error(f"Invalid source: {source_lower}")
            raise _ExportAborted(f"Invalid source: {source_lower}")

        target_normalized_log = _normalize_schema_for_dialect(
            target_schema, self.config.database.type or ""
        )
        self.log.debug(
            f"Found {len(all_objects)} objects in schema '{target_schema}' "
            f"(normalized: '{target_normalized_log}')"
        )
        self.state.schema_payload = schema_payload
        return all_objects, typed_lists

    def _load_snapshot_payload(self, source_lower: str) -> SchemaSnapshotPayload:
        """Load a SchemaSnapshotPayload from database or file source."""
        if source_lower == "database-model":
            if not self.state.snapshot_service:
                self.log.error("Snapshot service is unavailable; cannot load from database model")
                raise _ExportAborted(
                    "Snapshot service is unavailable; cannot load from database model"
                )
            self.log.debug("Loading schema from database stored snapshot...")
            snapshot = self.state.snapshot_service.load_latest_snapshot()
            if not snapshot:
                self.log.error(
                    "No snapshot found in database. Use --source=live-database to capture one."
                )
                raise _ExportAborted(
                    "No snapshot found in database. Use --source=live-database to capture one."
                )
            self.log.debug(
                f"Loaded snapshot {snapshot.snapshot_id} captured at {snapshot.captured_at_iso}"
            )
            return snapshot.payload
        else:
            # file-model
            if self.options.snapshot_model is None:
                raise RuntimeError("snapshot_model is not set but file-model path was expected")
            snapshot_path = Path(self.options.snapshot_model)
            self.log.debug(f"Loading schema from file: {snapshot_path}...")
            if not self.state.snapshot_service:
                self.log.error("Snapshot service is unavailable; cannot load from file model")
                raise _ExportAborted("Snapshot service is unavailable; cannot load from file model")
            payload = self.state.snapshot_service.load_snapshot_payload_from_path(snapshot_path)
            self.log.debug(f"Loaded schema from file: {snapshot_path}")
            return payload

    def _introspect_snapshot_objects(
        self, schema_payload: SchemaSnapshotPayload
    ) -> Tuple[List[SqlObject], Dict[str, List[Any]]]:
        """Extract typed object lists from a snapshot payload."""
        typed_lists: Dict[str, List[Any]] = {}
        all_objects: List[SqlObject] = []
        for key in _OBJECT_TYPE_KEYS:
            items = list(getattr(schema_payload, key, None) or [])
            typed_lists[key] = items
            all_objects.extend(cast(List[SqlObject], items))
        return all_objects, typed_lists

    def _introspect_live_objects(self, target_schema: str) -> Dict[str, Any]:
        """Create introspector and run live database introspection."""
        log = self.log
        self.state.introspector = IntrospectorFactory.create(
            self.state.provider, log=log if log else logger
        )
        self.log.debug(f"Will introspect schema '{target_schema}' from live database...")
        if not self.state.introspector:
            self.log.error("Introspector is unavailable")
            raise _ExportAborted("Introspector is unavailable")
        self.log.debug(f"Introspecting schema '{target_schema}' from live database...")
        return self.state.introspector.introspect_schema(
            target_schema,
            include_views=True,
            include_sequences=True,
            include_triggers=True,
            include_procedures=True,
            include_functions=True,
        )

    def _build_object_type_index(
        self, schema_data: Dict[str, Any], target_normalized: str
    ) -> Tuple[List[SqlObject], Dict[str, List[Any]]]:
        """Process introspection data into typed lists with schema filtering."""
        all_objects: List[SqlObject] = []
        typed_lists: Dict[str, List[Any]] = {key: [] for key in _OBJECT_TYPE_KEYS}

        # Simple types: filter by schema match
        table_names = {
            _normalize_identifier(getattr(table, "name", None))
            for table in schema_data.get("tables", [])
        }
        relation_names = set(table_names)
        for key in ("views", "materialized_views"):
            relation_names.update(
                _normalize_identifier(getattr(obj, "name", None))
                for obj in schema_data.get(key, [])
            )
        referenced_sequence_names = _sequence_names_referenced_by_tables(
            schema_data.get("tables", [])
        )
        for key in _SCHEMA_FILTERED_TYPES:
            if key in schema_data:
                for obj in schema_data[key]:
                    if key == "sequences" and _is_table_owned_sequence(
                        obj, table_names, referenced_sequence_names
                    ):
                        continue
                    if (
                        key == "user_defined_types"
                        and _normalize_identifier(getattr(obj, "name", None)) in relation_names
                    ):
                        continue
                    if self._schema_matches(obj, target_normalized):
                        all_objects.append(obj)
                        typed_lists[key].append(obj)

        # Materialized views merge into views list
        if "materialized_views" in schema_data:
            for mv in schema_data["materialized_views"]:
                if self._schema_matches(mv, target_normalized):
                    all_objects.append(mv)
                    typed_lists["views"].append(mv)

        # Indexes: handle both dict format {table: [indexes]} and flat list
        if "indexes" in schema_data:
            indexes_data = schema_data["indexes"]
            items: List[Any] = []
            if isinstance(indexes_data, dict):
                for table_indexes in indexes_data.values():
                    items.extend(table_indexes)
            elif isinstance(indexes_data, list):
                items = indexes_data
            for idx in items:
                if self._schema_matches(idx, target_normalized):
                    all_objects.append(idx)
                    typed_lists["indexes"].append(idx)

        # Extensions: include if no target schema or if schema matches
        if "extensions" in schema_data:
            for ext in schema_data["extensions"]:
                if not target_normalized or self._schema_matches(ext, target_normalized):
                    all_objects.append(ext)
                    typed_lists["extensions"].append(ext)

        # Global objects (no schema filter)
        for key in _GLOBAL_TYPES:
            if key in schema_data:
                for obj in schema_data[key]:
                    all_objects.append(obj)
                    typed_lists[key].append(obj)

        return all_objects, typed_lists

    @staticmethod
    def _object_key(obj: SqlObject) -> Tuple[Any, ...]:
        return (
            getattr(obj.object_type, "value", obj.object_type),
            _normalize_identifier(getattr(obj, "schema", None)),
            _normalize_identifier(getattr(obj, "name", None)),
        )

    def _apply_exclusions_and_filters(
        self, all_objects: List[SqlObject], typed_lists: Dict[str, List[Any]]
    ) -> Tuple[List[SqlObject], Dict[str, List[Any]]]:
        """Exclude internal objects, sync typed lists, apply user filters."""
        config = self.config
        options = self.options
        target_schema = self.state.target_schema
        tables = options.tables
        types = options.types
        unmanaged_only = options.unmanaged_only
        managed_only = options.managed_only
        scripts_dir = options.scripts_dir
        additional_scripts_dirs = options.additional_scripts_dirs
        dir_recursive_map = options.dir_recursive_map
        recursive = options.recursive
        tags = options.tags
        exclude_tags = options.exclude_tags
        versions = options.versions
        exclude_versions = options.exclude_versions
        target_version = options.target_version

        allowed_keys = {self._object_key(obj) for obj in all_objects}

        # Sync typed lists with allowed keys
        filtered_typed_lists: Dict[str, List[Any]] = {}
        for key, lst in typed_lists.items():
            filtered_typed_lists[key] = [
                obj for obj in lst if self._object_key(obj) in allowed_keys
            ]

        # Ensure provider connection is active for filtering
        if (managed_only or unmanaged_only) and self.state.provider is not None:
            try:
                ensure_provider_connection(self.state.provider)
            except Exception as e:
                self.log.error(
                    f"Failed to establish database connection for managed object filtering: {e}"
                )
                raise _ExportAborted(
                    f"Failed to establish database connection for managed object filtering: {e}"
                )

        # Apply filters
        filtered_objects = _filter_objects(
            all_objects,
            tables=tables,
            types=types,
            unmanaged_only=unmanaged_only,
            managed_only=managed_only,
            config=config,
            executor=self.executor,
            scripts_dir=scripts_dir,
            additional_scripts_dirs=additional_scripts_dirs,
            dir_recursive_map=dir_recursive_map,
            recursive=recursive,
            target_schema=target_schema,
            tags=tags,
            exclude_tags=exclude_tags,
            versions=versions,
            exclude_versions=exclude_versions,
            target_version=target_version,
            debug_func=self.log.debug,
        )

        return filtered_objects, filtered_typed_lists

    def _generate_and_write(
        self, filtered_objects: List[SqlObject], typed_lists: Dict[str, List[Any]]
    ) -> bool:
        """Orchestrator: generate SQL scripts and write output files."""
        dialect: str = cast(str, self.state.dialect)
        description = self.options.description

        if not filtered_objects:
            # BUG-02b (ADR-0013 PR-2): empty-but-correct is SUCCESS, not
            # failure. The filter matched nothing — that's a valid outcome
            # of running ``--managed-only`` / ``--tags`` / ``--target-version``
            # against a schema that does not contain matching objects, and
            # the empty file we just wrote is a structurally-correct
            # migration script. Prior to this PR we reported FAILED despite
            # the file being on disk and well-formed.
            self._write_empty_export(dialect, description)
            _log_command_footer(self.log.info, True, self.start_time, self.log)
            return True

        self.log.info(f"Exporting {len(filtered_objects)} objects")
        object_counts = self._log_and_count_objects(filtered_objects)
        _remove_redundant_unique_constraints(filtered_objects)
        self._ensure_schema_payload(typed_lists, dialect, description)
        files = self._generate_object_sql(filtered_objects, dialect)
        return self._write_output_files(
            files, len(filtered_objects), object_counts, dialect, description
        )

    def _write_empty_export(self, dialect: str, description: Optional[str]) -> None:
        """Write an empty export file when no objects match filters."""
        self.log.warn("No objects found matching filter criteria after filtering")
        output = self.options.output
        output_dir = self.options.output_dir
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            header = _generate_migration_header(output_path.name, 0, dialect, description)
            footer = _generate_migration_footer()
            output_path.write_text(
                f"{header}\n-- No objects found matching filter criteria\n{footer}",
                encoding="utf-8",
            )
            self.log.info(f"Created empty export file: {output_path}")
        elif output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            placeholder_file = output_path / "empty_export.sql"
            header = _generate_migration_header(placeholder_file.name, 0, dialect, description)
            footer = _generate_migration_footer()
            placeholder_file.write_text(
                f"{header}\n-- No objects found matching filter criteria\n{footer}",
                encoding="utf-8",
            )
            self.log.info(f"Created empty export file: {placeholder_file}")

    def _log_and_count_objects(self, filtered_objects: List[SqlObject]) -> Dict[str, int]:
        """Log object summary and return counts by type."""
        object_counts: Dict[str, int] = {}
        for obj in filtered_objects:
            obj_type = get_object_type_name(obj)
            obj_type = obj_type.lower()
            object_counts[obj_type] = object_counts.get(obj_type, 0) + 1
        if object_counts:
            self.log.info("Objects to export:")
            for obj_type, count in sorted(object_counts.items()):
                self.log.info(f"  - {obj_type}: {count}")
        return object_counts

    def _ensure_schema_payload(
        self, typed_lists: Dict[str, List[Any]], dialect: str, description: Optional[str]
    ) -> None:
        """Build schema payload from typed lists if not already loaded from snapshot."""
        if self.state.schema_payload:
            return
        metadata: Dict[str, Any] = {
            "dialect": dialect,
            "schema": self.state.target_schema,
            "snapshot": {
                "reason": "export-schema",
                "captured_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        if self.state.schema_version:
            metadata.setdefault("migration", {})["current_version"] = self.state.schema_version
        if description:
            metadata["snapshot"]["description"] = description
        if self.state.filters:
            metadata["snapshot"]["filters"] = self.state.filters
        payload_kwargs: Dict[str, Any] = {
            key: typed_lists.get(key, []) for key in _OBJECT_TYPE_KEYS
        }
        payload_kwargs["metadata"] = metadata
        self.state.schema_payload = SchemaSnapshotPayload(**payload_kwargs)

    def _generate_object_sql(
        self, filtered_objects: List[SqlObject], dialect: str
    ) -> Dict[str, str]:
        """Generate SQL scripts from filtered objects via SqlGeneratorFactory."""
        generator = SqlGeneratorFactory.create(dialect=dialect, use_dependency_ordering=True)
        organization = (
            OrganizationStrategy.BY_TYPE
            if self.options.split_by_type
            else OrganizationStrategy.SINGLE_FILE
        )
        script_options = ScriptOptions(
            organization=organization,
            include_drops=self.options.include_drops,
            include_comments=True,
            format_sql=True,
        )
        schema_dict: Dict[str, List[SqlObject]] = {}
        for obj in filtered_objects:
            obj_type = get_object_type_name(obj)
            obj_type_key = obj_type.lower()
            if obj_type_key not in schema_dict:
                schema_dict[obj_type_key] = []
            schema_dict[obj_type_key].append(obj)
        return generator.generate_schema_script(
            schema_dict, target_dialect=dialect, options=script_options
        )

    def _write_output_files(
        self,
        files: Dict[str, str],
        object_count: int,
        object_counts: Dict[str, int],
        dialect: str,
        description: Optional[str],
    ) -> bool:
        """Write generated SQL to output file(s) and build ExportSchemaResult."""
        options = self.options
        split_by_type = options.split_by_type
        output_dir = options.output_dir

        if split_by_type or output_dir:
            if not output_dir:
                self.log.error("output_dir is required when split_by_type is True")
                _log_command_footer(self.log.info, False, self.start_time, self.log)
                return False
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            exported_files_list: List[str] = []
            for file_name, sql_content in files.items():
                file_path = output_path / file_name
                header_object_count = _object_count_for_output_file(
                    file_name, object_counts, object_count
                )
                header = _generate_migration_header(
                    file_name, header_object_count, dialect, description
                )
                footer = _generate_migration_footer()
                sql_content = _with_schema_preamble(sql_content, dialect, self.state.target_schema)
                file_path.write_text(f"{header}\n{sql_content}\n{footer}", encoding="utf-8")
                exported_files_list.append(str(file_path))
                self.log.info(f"Exported to: {file_path}")
            self.log.info(
                f"Successfully exported {len(exported_files_list)} file(s) to {output_path}"
            )
            output_options = {
                "split_by_type": split_by_type,
                "include_drops": options.include_drops,
                "output_dir": str(output_path),
                "dialect": dialect,
            }
        else:
            output = options.output
            if not output:
                self.log.error("output is required for single file export")
                _log_command_footer(self.log.info, False, self.start_time, self.log)
                return False
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            combined_sql = "\n\n".join(files.values())
            combined_sql = _with_schema_preamble(combined_sql, dialect, self.state.target_schema)
            header = _generate_migration_header(
                output_path.name, object_count, dialect, description
            )
            footer = _generate_migration_footer()
            output_path.write_text(f"{header}\n{combined_sql}\n{footer}", encoding="utf-8")
            self.log.info(f"Exported {object_count} object(s) to: {output_path}")
            exported_files_list = [str(output_path)]
            output_options = {
                "split_by_type": split_by_type,
                "include_drops": options.include_drops,
                "output_file": str(output_path),
                "dialect": dialect,
            }

        # Create result for HTML log
        log = self.log
        if log and hasattr(log, "set_command_completed"):
            from core.logger.results import ExportSchemaResult

            result = ExportSchemaResult(
                success=True,
                output_files=exported_files_list,
                objects_exported=object_counts,
            )
            result.filters_applied = self.state.filters
            result.output_options = output_options
            _populate_export_result_metadata(
                result,
                self.state.provider,
                self.state.schema_version,
                self.state.database_url_masked,
                self.state.database_url,
            )
            log._export_schema_result = result  # type: ignore[union-attr]

        _log_command_footer(self.log.info, True, self.start_time, self.log)
        return True


def export_schema(
    config: Any,
    options: ExportSchemaOptions,
    executor: Any = None,
    log: Any = None,
    provider: Any = None,
) -> bool:
    """Export database schema to migration file(s).

    Args:
        config: DBLift configuration object
        options: Export options (output, filters, source, etc.)
        executor: MigrationExecutor instance (optional, will create one if not provided)
        log: Optional DbliftLogger instance (if None, uses standard logging)
        provider: Optional pre-initialised provider. When supplied, it is
            reused instead of calling ``ProviderRegistry.create_provider`` —
            avoids a second provider initialization from a running DBLiftClient.

    Returns:
        True if successful, False otherwise
    """
    from core.logger.console import console_status

    exporter = SchemaExporter(config, options, executor, log, provider=provider)
    with console_status("Exporting schema..."):
        return exporter.run()


_NEXTVAL_SEQUENCE_PATTERNS = (
    re.compile(r"nextval\s*\(\s*'([^']+)'\s*(?:::regclass)?\s*\)", re.IGNORECASE),
    re.compile(
        r"nextval\s*\(\s*cast\s*\(\s*'([^']+)'\s+as\s+regclass\s*\)\s*\)",
        re.IGNORECASE,
    ),
)


def _sequence_names_referenced_by_tables(tables: List[Any]) -> set[str]:
    referenced = set()
    for table in tables:
        columns = getattr(table, "columns", None) or []
        if not isinstance(columns, (list, tuple)):
            continue
        for column in columns:
            default = getattr(column, "default_value", None)
            if not isinstance(default, str):
                continue
            for pattern in _NEXTVAL_SEQUENCE_PATTERNS:
                for match in pattern.finditer(default):
                    sequence_name = _normalize_identifier(match.group(1).split(".")[-1])
                    if _is_implicit_nextval_sequence_for_column(table, column, sequence_name):
                        continue
                    referenced.add(sequence_name)
    return referenced


def _is_implicit_nextval_sequence_for_column(table: Any, column: Any, sequence_name: str) -> bool:
    table_name = _normalize_identifier(getattr(table, "name", None))
    column_name = _normalize_identifier(getattr(column, "name", None))
    return bool(table_name and column_name and sequence_name == f"{table_name}_{column_name}_seq")


def _object_count_for_output_file(
    file_name: str, object_counts: Dict[str, int], default_count: int
) -> int:
    obj_type = Path(file_name).stem.lower()
    return object_counts.get(obj_type, default_count)


def _with_schema_preamble(sql_content: str, dialect: str, schema: Optional[str]) -> str:
    if (dialect or "").lower() not in {
        "postgresql",  # lint: allow-dialect-string: export replay compatibility
        "postgres",  # lint: allow-dialect-string: export replay compatibility
    }:
        return sql_content
    if not schema:
        return sql_content
    escaped_schema = schema.replace('"', '""')
    return f'SET search_path = "{escaped_schema}";\n\n{sql_content}'


def _is_table_owned_sequence(
    obj: SqlObject, table_names: set[str], referenced_sequence_names: set[str]
) -> bool:
    """Return True for PG serial/identity backing sequences already implied by a table."""
    name = _normalize_identifier(getattr(obj, "name", None))
    if name in referenced_sequence_names:
        return False

    owned_by_table = getattr(obj, "owned_by_table", None)
    owned_by_column = getattr(obj, "owned_by_column", None)
    if (
        isinstance(owned_by_table, str)
        and owned_by_table
        and isinstance(owned_by_column, str)
        and owned_by_column
    ):
        return True

    if not name.endswith("_id_seq"):
        return False
    return name[: -len("_id_seq")] in table_names


# ``ManagedObjectFilter`` class removed in Z-2: it was a thin wrapper
# around ``_filter_objects`` whose only callers were two test files
# (``test_export_schema_command_extended.py`` and
# ``test_export_schema_coverage.py``). The canonical filter logic lives
# in module-level functions in ``_managed_object_filter.py``; the
# wrapper class added indirection without any production caller.


# ---------------------------------------------------------------------------
# Re-exports
#
# Several helpers used to live in this module and have been pulled out into
# focused submodules. They are re-exported here so existing import paths keep
# working — notably ``cli/snapshot_command.py`` imports ``_log_command_footer``
# from this module.
# ---------------------------------------------------------------------------

from core.migration.commands._export_helpers import (  # noqa: F401,E402  re-exports
    _get_quirks_from_config,
    _normalize_identifier,
    _normalize_schema_for_dialect,
    _remove_redundant_unique_constraints,
)
from core.migration.commands._export_metadata import (  # noqa: F401,E402  re-exports
    _generate_migration_footer,
    _generate_migration_header,
    _log_command_footer,
    _populate_export_result_metadata,
)
from core.migration.commands._managed_object_filter import (  # noqa: F401,E402  re-exports
    _exclude_internal_objects,
    _filter_objects,
    _get_managed_objects,
    _is_object_managed,
)
