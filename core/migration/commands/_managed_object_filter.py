"""Managed-object filtering helpers extracted from ``export_schema_command``.

The public ``export-schema`` command needs to decide, for each schema
object pulled out of the live database, whether to include it in the
generated migration. That decision involves four cooperating helpers:

- ``_filter_objects``: top-level driver applied by ``SchemaExporter``.
  Drops dblift-internal objects, narrows by ``--tables`` /
  ``--types``, and routes through ``--managed-only`` /
  ``--unmanaged-only`` / version + tag filters.
- ``_exclude_internal_objects``: drops the dblift schema-history
  table, vendor-managed dependencies, identity sequences, etc.
- ``_get_managed_objects``: parses the migration scripts that match
  the active filter set and returns the union of objects they
  define / mutate.
- ``_is_object_managed``: predicate matching a single live object
  against the parsed managed set.

All four lived inline in ``export_schema_command.py`` (1960 → 1719 →
extraction here). Pulled out so the orchestrator file can stay focused
on the ``SchemaExporter`` pipeline and so this filtering logic can be
unit-tested in isolation. ``export_schema_command`` re-exports the
four names — the tests that ``mock.patch`` them, and any caller doing
``from core.migration.commands.export_schema_command import _filter_objects``,
keep working.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, cast

from core.logger import DbliftLogger, Log
from core.migration.commands._export_helpers import (
    _get_quirks_from_config,
    _normalize_identifier,
    _normalize_schema_for_dialect,
)
from core.migration.migration import Migration
from core.sql_model.base import (
    ConstraintType,
    SqlObject,
    SqlObjectType,
    get_object_type_name,
)
from core.sql_parser.hybrid_parser import HybridParser

logger = logging.getLogger(__name__)


def _filter_objects(
    objects: List[SqlObject],
    tables: Optional[str] = None,
    types: Optional[str] = None,
    unmanaged_only: bool = False,
    managed_only: bool = False,
    config: Any = None,
    executor: Any = None,
    scripts_dir: Optional[Path] = None,
    additional_scripts_dirs: Optional[List[Path]] = None,
    dir_recursive_map: Optional[Dict[Path, bool]] = None,
    recursive: bool = True,
    target_schema: Optional[str] = None,
    tags: Optional[str] = None,
    exclude_tags: Optional[str] = None,
    versions: Optional[str] = None,
    exclude_versions: Optional[str] = None,
    target_version: Optional[str] = None,
    debug_func: Any = None,
) -> List[SqlObject]:
    """Filter objects based on criteria.

    Args:
        objects: List of objects to filter
        tables: Comma-separated table names (filters tables and related objects)
        types: Comma-separated object types
        unmanaged_only: Only include objects not in applied migrations
        managed_only: Only include objects defined in applied migrations
        config: Configuration (for checking applied migrations)
        executor: MigrationExecutor instance (for accessing script_manager and state_manager)
        scripts_dir: Migration scripts directory (for parsing applied migrations)
        additional_scripts_dirs: Optional list of additional directories to search
        dir_recursive_map: Optional mapping of directory paths to their recursive settings
        recursive: Whether to search subdirectories recursively (default: True)
        target_schema: Target schema name
        tags: Comma-separated list of tags to filter migrations
        exclude_tags: Comma-separated list of tags to exclude from migrations
        versions: Comma-separated list of versions to filter migrations
        exclude_versions: Comma-separated list of versions to exclude from migrations
        target_version: Only consider migrations up to this version
        debug_func: Optional debug logging function

    Returns:
        Filtered list of objects
    """
    filtered = _exclude_internal_objects(objects, config=config, target_schema=target_schema)

    # Filter by table names
    if tables:
        table_names = {t.strip().upper() for t in tables.split(",")}
        table_objects = [
            obj
            for obj in filtered
            if (
                (hasattr(obj, "name") and obj.name.upper() in table_names)
                or (hasattr(obj, "table_name") and obj.table_name.upper() in table_names)
            )
        ]
        filtered = table_objects

    # Filter by object types
    if types:
        type_set = {t.strip().lower() for t in types.split(",")}
        # Normalize plural forms to singular (e.g., "tables" -> "table", "views" -> "view")
        type_mapping = {
            "tables": "table",
            "views": "view",
            "indexes": "index",
            "sequences": "sequence",
            "procedures": "procedure",
            "functions": "function",
            "triggers": "trigger",
            "constraints": "constraint",
            "schemas": "schema",
            "databases": "database",
            "types": "type",
            "roles": "role",
            "users": "user",
            "materialized_views": "materialized_view",
            "packages": "package",
            "package_bodies": "package_body",
            "synonyms": "synonym",
            "events": "event",
            "partitions": "partition",
            "database_links": "database_link",
        }
        normalized_type_set = {type_mapping.get(t, t) for t in type_set}
        filtered = [
            obj for obj in filtered if get_object_type_name(obj).lower() in normalized_type_set
        ]

    # Filter managed/unmanaged objects. Version/tag filters also trigger this path so that
    # `--target-version`/`--tags`/`--versions` restrict the export to the matching managed subset
    # even when neither `--managed-only` nor `--unmanaged-only` is specified.
    filters_used = bool(target_version or versions or exclude_versions or tags or exclude_tags)
    if (unmanaged_only or managed_only or filters_used) and config and scripts_dir and executor:
        managed_objects = _get_managed_objects(
            config,
            executor,
            scripts_dir,
            additional_scripts_dirs=additional_scripts_dirs,
            dir_recursive_map=dir_recursive_map,
            recursive=recursive,
            tags=tags,
            exclude_tags=exclude_tags,
            versions=versions,
            exclude_versions=exclude_versions,
            target_version=target_version,
            debug_func=debug_func,
        )
        if managed_objects is None:
            if unmanaged_only or managed_only:
                logger.warning(
                    f"--{'unmanaged-only' if unmanaged_only else 'managed-only'} requires migration history access"
                )
            else:
                logger.warning(
                    "Version/tag filters require migration history access; filters ignored"
                )
        else:
            # Get dialect for schema normalization in _is_object_managed
            dialect = (
                config.database.type.lower()
                if getattr(getattr(config, "database", None), "type", None)
                else None
            )
            initial_count = len(filtered)
            if managed_only:
                # Only include objects that are managed
                filtered = [
                    obj
                    for obj in filtered
                    if _is_object_managed(
                        obj, managed_objects, dialect=dialect, debug_func=debug_func
                    )
                ]
                if debug_func:
                    debug_func(
                        f"Filtered {initial_count} objects to {len(filtered)} managed objects"
                    )
            elif unmanaged_only:
                # Only include objects that are NOT managed
                filtered = [
                    obj
                    for obj in filtered
                    if not _is_object_managed(
                        obj, managed_objects, dialect=dialect, debug_func=debug_func
                    )
                ]
                if debug_func:
                    debug_func(
                        f"Filtered {initial_count} objects to {len(filtered)} unmanaged objects"
                    )
            elif filters_used:
                # Intersect live schema with the filtered managed set so version/tag filters apply.
                filtered = [
                    obj
                    for obj in filtered
                    if _is_object_managed(
                        obj, managed_objects, dialect=dialect, debug_func=debug_func
                    )
                ]
                if debug_func:
                    debug_func(
                        f"Filtered {initial_count} objects to {len(filtered)} via version/tag filters"
                    )
    elif (unmanaged_only or managed_only) and not scripts_dir:
        logger.warning(
            f"--{'unmanaged-only' if unmanaged_only else 'managed-only'} requires migration scripts directory"
        )

    return filtered


def _exclude_internal_objects(
    objects: List[SqlObject], config: Any = None, target_schema: Optional[str] = None
) -> List[SqlObject]:
    """Remove DBLift internal objects and provider-managed dependencies."""

    if not objects:
        return []

    # Determine configured schema and history table name.
    # NOTE: when ``target_schema`` is empty we deliberately leave
    # ``schema_normalized`` empty for SQL dialects so the ``is_internal`` fast
    # path matches internal objects in any schema. CosmosDB-style nosql
    # dialects don't have user-named schemas, so falling back to the
    # default schema there is safe and was the historical behavior.
    schema_normalized = _normalize_identifier(target_schema)
    quirks = _get_quirks_from_config(config) if config else None
    if (
        not schema_normalized
        and quirks
        and quirks.default_schema_name
        and getattr(quirks, "is_nosql", False)
    ):
        schema_normalized = quirks.default_schema_name

    default_schema_norm = ""
    if quirks and quirks.default_schema_name:
        default_schema_norm = _normalize_identifier(quirks.default_schema_name)

    history_table_name = None
    snapshot_table_name = None

    if config is not None:
        # Get history_table, but only if it's actually set (not a Mock)
        # Check if config has the attribute and it's a real value
        if hasattr(config, "history_table"):
            hist_val = getattr(config, "history_table")
            if isinstance(hist_val, str):
                history_table_name = hist_val
        if not history_table_name and hasattr(config, "database"):
            if hasattr(config.database, "history_table"):
                db_history_table = getattr(config.database, "history_table")
                # Only use if it's a real value (string), not a Mock
                if isinstance(db_history_table, str):
                    history_table_name = db_history_table
        # Same for snapshot_table
        if hasattr(config, "snapshot_table"):
            snap_val = getattr(config, "snapshot_table")
            if isinstance(snap_val, str):
                snapshot_table_name = snap_val
        if not snapshot_table_name and hasattr(config, "database"):
            if hasattr(config.database, "snapshot_table"):
                db_snapshot_table = getattr(config.database, "snapshot_table")
                # Only use if it's a real value (string), not a Mock
                if isinstance(db_snapshot_table, str):
                    snapshot_table_name = db_snapshot_table

    history_table_normalized = _normalize_identifier(history_table_name) or "dblift_schema_history"
    snapshot_table_normalized = (
        _normalize_identifier(snapshot_table_name) or "dblift_schema_snapshots"
    )

    # Known internal base names (include plural form used by some providers)
    internal_base_names = {
        history_table_normalized,
        "dblift_migration_lock",
        "dblift_migration_locks",
        snapshot_table_normalized,
    }
    internal_base_names = {name for name in internal_base_names if name}

    internal_qualified_names = {
        f"{schema_normalized}.{name}" for name in internal_base_names if schema_normalized and name
    }

    # Gather metadata needed to filter provider-managed dependencies
    table_names: Set[Tuple[str, str]] = set()
    view_names: Set[Tuple[str, str]] = set()
    pk_unique_index_names: Set[Tuple[str, str]] = set()
    identity_sequence_names: Set[Tuple[str, str]] = set()

    seq_regex = re.compile(
        r"nextval\(\s*(?:'|\")(?:(?P<schema>[^\s'\".]+)\.)?(?P<name>[^\s'\"()]+)",
        re.IGNORECASE,
    )

    def is_implicit_serial_sequence(
        table_name: Optional[str], column_name: Optional[str], sequence_name: Optional[str]
    ) -> bool:
        if not table_name or not sequence_name:
            return False
        if column_name:
            return sequence_name == f"{table_name}_{column_name}_seq"
        return sequence_name == f"{table_name}_id_seq"

    for obj in objects:
        obj_schema = _normalize_identifier(getattr(obj, "schema", None))
        if not obj_schema and default_schema_norm:
            obj_schema = default_schema_norm
        obj_name = _normalize_identifier(getattr(obj, "name", None))

        obj_type = getattr(obj, "object_type", None)
        if isinstance(obj_type, str):
            try:
                obj_type = SqlObjectType[obj_type.upper()]
            except KeyError:
                obj_type = None

        if obj_type == SqlObjectType.TABLE:
            if obj_name:
                table_names.add((obj_schema, obj_name))

            for column in getattr(obj, "columns", []) or []:
                default_value = getattr(column, "default_value", None) or ""
                if not default_value:
                    continue
                match = seq_regex.search(default_value)
                if not match:
                    continue
                seq_schema = _normalize_identifier(match.group("schema")) or obj_schema
                seq_name = _normalize_identifier(match.group("name"))
                raw_column_name = getattr(column, "name", None)
                column_name = (
                    _normalize_identifier(raw_column_name)
                    if isinstance(raw_column_name, str)
                    else ""
                )
                if is_implicit_serial_sequence(obj_name, column_name, seq_name):
                    identity_sequence_names.add((seq_schema, seq_name))

            for constraint in getattr(obj, "constraints", []) or []:
                constraint_type = getattr(constraint, "constraint_type", None)
                if isinstance(constraint_type, str):
                    try:
                        constraint_type = ConstraintType[constraint_type.upper().replace(" ", "_")]
                    except KeyError:
                        constraint_type = None
                if constraint_type in (ConstraintType.PRIMARY_KEY, ConstraintType.UNIQUE):
                    constraint_name = _normalize_identifier(getattr(constraint, "name", None))
                    if constraint_name:
                        pk_unique_index_names.add((obj_schema, constraint_name))

        elif obj_type == SqlObjectType.VIEW:
            if obj_name:
                view_names.add((obj_schema, obj_name))

    def is_internal(obj: SqlObject) -> bool:
        obj_name = _normalize_identifier(getattr(obj, "name", None))
        obj_schema_raw = getattr(obj, "schema", None)
        obj_schema = _normalize_identifier(obj_schema_raw)
        if not obj_schema and config:
            quirks = _get_quirks_from_config(config)
            if quirks and quirks.default_schema_name and getattr(quirks, "is_nosql", False):
                obj_schema = quirks.default_schema_name
        qualified = f"{obj_schema}.{obj_name}" if obj_schema else obj_name

        # Filter if name matches internal base names and:
        # - No target schema specified, OR
        # - Table schema matches target schema, OR
        # - Table has no schema (empty) and we're filtering for a specific schema
        if obj_name in internal_base_names:
            if not schema_normalized:
                # No target schema - filter any matching name
                return True
            elif obj_schema == schema_normalized:
                # Schema matches - filter
                return True
            elif not obj_schema and schema_normalized:
                # Table has no schema but target schema is specified
                # Still filter if name matches (table is in default/target schema)
                return True

        if qualified in internal_qualified_names:
            return True

        obj_type: Optional[SqlObjectType]
        raw_obj_type = obj.object_type
        if isinstance(raw_obj_type, str):
            try:
                obj_type = SqlObjectType[raw_obj_type.upper()]
            except KeyError:
                obj_type = None
        elif isinstance(raw_obj_type, SqlObjectType):
            obj_type = raw_obj_type
        else:
            obj_type = None

        if obj_type == SqlObjectType.INDEX:
            table_name = _normalize_identifier(getattr(obj, "table_name", None))
            table_schema_raw = getattr(obj, "table_schema", None) or getattr(obj, "schema", None)
            table_schema = _normalize_identifier(table_schema_raw)
            # For CosmosDB (nosql), normalize None/empty schema to default for comparison
            if not table_schema and config:
                quirks = _get_quirks_from_config(config)
                if quirks and quirks.default_schema_name and getattr(quirks, "is_nosql", False):
                    table_schema = quirks.default_schema_name
            table_qualified = f"{table_schema}.{table_name}" if table_schema else table_name

            # Filter if table name matches internal base names and:
            # - No target schema specified, OR
            # - Table schema matches target schema, OR
            # - Table has no schema (empty) and we're filtering for a specific schema
            if table_name in internal_base_names:
                if not schema_normalized:
                    # No target schema - filter any matching name
                    return True
                elif table_schema == schema_normalized:
                    # Schema matches - filter
                    return True
                elif not table_schema and schema_normalized:
                    # Table has no schema but target schema is specified
                    # Still filter if name matches (table is in default/target schema)
                    return True

            if table_qualified in internal_qualified_names:
                return True

            # Check if index name starts with any internal base name prefix
            # Only do this if obj_name is a string (not a Mock)
            if isinstance(obj_name, str):
                if any(
                    obj_name.startswith(prefix)
                    for prefix in internal_base_names
                    if isinstance(prefix, str)
                ):
                    return True

            # Skip indexes implied by primary key / unique constraints
            index_key = (obj_schema, obj_name)
            if index_key in pk_unique_index_names or ("", obj_name) in pk_unique_index_names:
                return True

        if obj_type == SqlObjectType.SEQUENCE:
            seq_key = (obj_schema, obj_name)
            if seq_key in identity_sequence_names or ("", obj_name) in identity_sequence_names:
                return True
            if any(obj_name.startswith(prefix) for prefix in internal_base_names):
                return True

        if obj_type == SqlObjectType.TRIGGER:
            trigger_table = _normalize_identifier(getattr(obj, "table_name", None))
            trigger_schema = _normalize_identifier(getattr(obj, "table_schema", None))
            if not trigger_schema and default_schema_norm:
                trigger_schema = default_schema_norm
            trigger_qualified = (
                f"{trigger_schema}.{trigger_table}" if trigger_schema else trigger_table
            )

            if trigger_table in internal_base_names and (
                not schema_normalized or trigger_schema == schema_normalized
            ):
                return True

            if trigger_qualified in internal_qualified_names:
                return True

        if obj_type == SqlObjectType.CONSTRAINT:
            parent_table = _normalize_identifier(
                getattr(obj, "table_name", None) or getattr(obj, "table", None)
            )
            parent_schema = _normalize_identifier(getattr(obj, "table_schema", None))
            if not parent_schema and default_schema_norm:
                parent_schema = default_schema_norm
            parent_qualified = f"{parent_schema}.{parent_table}" if parent_schema else parent_table

            if parent_table in internal_base_names and (
                not schema_normalized or parent_schema == schema_normalized
            ):
                return True

            if parent_qualified in internal_qualified_names:
                return True

        if obj_type == SqlObjectType.TYPE:
            type_key = (obj_schema, obj_name)
            if type_key in view_names or type_key in table_names or ("", obj_name) in view_names:
                return True

        return False

    return [obj for obj in objects if not is_internal(obj)]


def _get_managed_objects(
    config: Any,
    executor: Any,
    scripts_dir: Path,
    additional_scripts_dirs: Optional[List[Path]] = None,
    dir_recursive_map: Optional[Dict[Path, bool]] = None,
    recursive: bool = True,
    tags: Optional[str] = None,
    exclude_tags: Optional[str] = None,
    versions: Optional[str] = None,
    exclude_versions: Optional[str] = None,
    target_version: Optional[str] = None,
    debug_func: Any = None,
) -> Optional[Set[Tuple[Any, ...]]]:
    """Get set of managed objects from applied migrations.

    Uses the executor's script_manager and state_manager to properly load and match migration files.

    Args:
        config: DBLift configuration
        executor: MigrationExecutor instance (provides script_manager and state_manager)
        scripts_dir: Migration scripts directory
        additional_scripts_dirs: Optional list of additional directories to search
        dir_recursive_map: Optional mapping of directory paths to their recursive settings
        recursive: Whether to search subdirectories recursively (default: True)
        tags: Comma-separated list of tags to filter migrations
        exclude_tags: Comma-separated list of tags to exclude from migrations
        versions: Comma-separated list of versions to filter migrations
        exclude_versions: Comma-separated list of versions to exclude from migrations
        target_version: Only consider migrations up to this version
        debug_func: Optional debug logging function

    Returns:
        Set of (schema, name, type) tuples for managed objects, or None if unable to determine
    """
    # Use debug_func if provided, otherwise fall back to logger.debug
    dbg = debug_func if debug_func else logger.debug

    try:
        # Use executor's state_manager to get applied migrations
        from core.migration.state.migration_state_manager import MigrationStateManager

        log_candidate = executor.log if hasattr(executor, "log") else None
        if log_candidate is None:
            log_candidate = DbliftLogger()

        state_manager = MigrationStateManager(
            cast(Log, log_candidate),
            executor.history_manager,
            executor.script_manager,
            executor.rules,
        )

        # Get applied migrations from history manager
        applied_migrations = executor.history_manager.get_applied_migrations()

        if not applied_migrations:
            dbg("No applied migrations found")
            return set()

        # Apply filters to applied migrations using state_manager
        # Normalize filter lists
        def normalize_filter(filter_str: Optional[str]) -> Optional[List[str]]:
            """Split a comma-separated filter string into a trimmed list, or None when empty."""
            if not filter_str:
                return None
            return [f.strip() for f in filter_str.split(",") if f.strip()]

        tags_list = normalize_filter(tags)
        exclude_tags_list = normalize_filter(exclude_tags)
        versions_list = normalize_filter(versions)
        exclude_versions_list = normalize_filter(exclude_versions)

        # Use state_manager's filter method for consistency
        if (
            tags_list
            or exclude_tags_list
            or versions_list
            or exclude_versions_list
            or target_version
        ):
            applied_migrations = state_manager.apply_filters_to_migrations(
                applied_migrations,
                target_version=target_version,
                tags=tags_list,
                exclude_tags=exclude_tags_list,
                versions=versions_list,
                exclude_versions=exclude_versions_list,
            )
            dbg(f"Filtered applied migrations: {len(applied_migrations)} migrations remaining")

        if not applied_migrations:
            dbg("No migrations remaining after filtering")
            return set()

        # Use script_manager to load all migration scripts from directories
        # This properly handles multiple directories, recursion, and file matching
        script_manager = executor.script_manager

        # Build list of directories to search
        dirs_to_search = [scripts_dir]
        if additional_scripts_dirs:
            dirs_to_search.extend(additional_scripts_dirs)

        # Build recursive map for all directories
        recursive_map: Dict[Path, bool] = {}
        if dir_recursive_map:
            recursive_map.update(dir_recursive_map)
        # Set default recursive setting for directories not in the map
        for dir_path in dirs_to_search:
            if dir_path not in recursive_map:
                recursive_map[dir_path] = recursive

        # Load all migration scripts using script_manager
        # This handles multiple directories, recursion, and proper file matching
        all_loaded_migrations = script_manager.load_migration_scripts(
            scripts_dir,
            recursive=recursive,
            additional_dirs=additional_scripts_dirs,
            dir_recursive_map=dir_recursive_map,
        )

        # Create a mapping of version -> Migration object for quick lookup
        version_to_migration: Dict[str, Migration] = {}
        for migration_type, migrations in all_loaded_migrations.items():
            for migration in migrations:
                if migration.version:
                    # Handle both exact version match and normalized versions
                    version_to_migration[migration.version] = migration
                    # Also store normalized version (dots vs underscores)
                    version_normalized = migration.version.replace(".", "_")
                    if version_normalized != migration.version:
                        version_to_migration[version_normalized] = migration

        # Parse applied migration files to extract objects
        parser = HybridParser(dialect=config.database.type.lower())
        managed_set: Set[Tuple[Any, ...]] = set()
        # Use config schema, but normalize empty to "" for matching
        # For PostgreSQL, empty schema means "public" schema
        target_schema = config.database.schema or ""
        # Normalize target_schema for comparison
        target_schema_normalized = _normalize_schema_for_dialect(
            target_schema, config.database.type or ""
        )

        dbg(
            f"Filtering managed objects by target schema: '{target_schema}' (normalized: '{target_schema_normalized}')"
        )

        for applied_migration in applied_migrations:
            version = applied_migration.version
            if not version:
                continue

            # Find the corresponding migration file using script_manager's loaded migrations
            migration_file = None
            migration_obj = version_to_migration.get(version)
            if not migration_obj:
                # Try normalized version (dots vs underscores)
                version_normalized = version.replace(".", "_")
                migration_obj = version_to_migration.get(version_normalized)

            if migration_obj and migration_obj.path:
                migration_file = migration_obj.path
            elif migration_obj and hasattr(migration_obj, "script_path"):
                migration_file = migration_obj.script_path

            if not migration_file or not migration_file.exists():
                # Surfaced as a warning (BUG-02 diagnostic): previously logged at
                # debug level and silently skipped. When --scripts points at the
                # wrong directory, every applied migration falls into this branch
                # and managed_set ends up empty — the user sees
                # "empty managed result" with zero signal as to why.
                logger.warning(
                    f"managed-only: migration file not found for version {version} "
                    f"(loaded {len(version_to_migration)} migrations from the scripts "
                    f"directory). The script will not contribute to the managed set."
                )
                continue

            dbg(f"Found migration file for version {version}: {migration_file.name}")

            # Parse the migration file
            try:
                # Use migration object's content if available, otherwise read from file
                if migration_obj and migration_obj.content:
                    sql_content = migration_obj.content
                else:
                    from core.migration.encoding import read_migration_text

                    sql_content = read_migration_text(
                        migration_file,
                        configured_encoding=getattr(migration_obj, "script_encoding", "utf-8"),
                        detect_encoding=getattr(migration_obj, "detect_encoding", False),
                    )

                # Extract objects using extract_objects() method (simplified approach)
                # This provides basic object information (name, schema, type) which is sufficient
                # for determining managed objects. Detailed metadata extraction is no longer needed.
                objects = parser.extract_objects(sql_content, default_schema=target_schema)

                if objects:
                    # Extract objects, filtering by target_schema
                    # Helper function to check if object schema matches target schema
                    def schema_matches(obj_schema_normalized: str) -> bool:
                        """Check if normalized object schema matches target schema."""
                        if not target_schema_normalized:
                            # If no target schema specified, accept all schemas
                            return True
                        return obj_schema_normalized == target_schema_normalized

                    # Process all extracted objects
                    object_counts = {
                        "TABLE": 0,
                        "VIEW": 0,
                        "FUNCTION": 0,
                        "TRIGGER": 0,
                        "PROCEDURE": 0,
                        "INDEX": 0,
                        "SEQUENCE": 0,
                    }

                    for obj in objects:
                        # Map object types (handle MATERIALIZED_VIEW as VIEW)
                        obj_type = get_object_type_name(obj)
                        obj_type = obj_type.upper()
                        if obj_type == "MATERIALIZED_VIEW":
                            obj_type = "VIEW"

                        # Fallback to target_schema if object has no schema
                        schema_input = (
                            obj.schema if (obj.schema and obj.schema.strip()) else target_schema
                        )
                        normalized_schema = _normalize_schema_for_dialect(
                            schema_input, config.database.type or ""
                        )
                        if schema_matches(normalized_schema):
                            key = (normalized_schema, obj.name.upper(), obj_type)
                            managed_set.add(key)
                            dbg(
                                f"Added managed {obj_type.lower()}: {key} (from migration {version})"
                            )

                            # Track counts
                            if obj_type in object_counts:
                                object_counts[obj_type] += 1
                        else:
                            dbg(
                                f"Skipped {obj_type.lower()} {obj.name} in schema '{normalized_schema}' (not target schema '{target_schema_normalized}')"
                            )

                    # Log what was found in this migration
                    dbg(
                        f"Migration {version} parsed: "
                        f"tables={object_counts['TABLE']}, "
                        f"views={object_counts['VIEW']}, "
                        f"functions={object_counts['FUNCTION']}, "
                        f"triggers={object_counts['TRIGGER']}, "
                        f"procedures={object_counts['PROCEDURE']}, "
                        f"indexes={object_counts['INDEX']}, "
                        f"sequences={object_counts['SEQUENCE']}"
                    )

            except Exception as e:
                # BUG-02 diagnostic: previously logged at debug level and silently
                # skipped. Per-migration parse failures that silently drop the
                # whole script from the managed set are the most likely cause of
                # "--managed-only produces empty result" reports.
                logger.warning(
                    f"managed-only: failed to parse migration {version}; "
                    f"its objects will be absent from the managed set "
                    f"(error: {e})"
                )
                continue

        # Count how many applied migrations actually contributed to the managed
        # set. If every applied migration was silently skipped (no script on
        # disk, parse failure), the managed set will be empty even though the
        # history has entries — almost always a --scripts misconfiguration.
        if applied_migrations and not managed_set:
            logger.warning(
                f"managed-only: {len(applied_migrations)} applied migration(s) "
                f"produced zero managed objects. Verify that --scripts points at "
                f"the directory containing the migration files referenced by the "
                f"history table, and that the migrations parse cleanly."
            )

        dbg(f"Found {len(managed_set)} managed objects from {len(applied_migrations)} migrations")
        if managed_set:
            dbg(f"Managed objects sample: {list(managed_set)[:5]}")
        # The empty-managed-set + non-empty-history case already warned
        # above with a more specific message pointing at --scripts; no
        # duplicate warning here.
        return managed_set

    except Exception as e:
        # BUG-02 diagnostic: previously logged at debug level and silently
        # returned None — the caller then treated --managed-only as "requires
        # migration history access" instead of "something broke while trying
        # to read it". Promote to warning so the failure surfaces by default.
        logger.warning(
            f"managed-only: failed to read managed objects "
            f"(returning None, caller will skip the filter): {e}"
        )
        return None


def _is_object_managed(
    obj: SqlObject,
    managed_set: Set[Tuple[Any, ...]],
    dialect: Optional[str] = None,
    debug_func: Any = None,
) -> bool:
    """Check if an object is managed (exists in managed_set).

    Args:
        obj: SQL object to check
        managed_set: Set of (schema, name, type) tuples
        dialect: Optional database dialect for schema normalization
        debug_func: Optional debug logging function

    Returns:
        True if object is managed
    """
    # Use debug_func if provided, otherwise fall back to logger.debug
    dbg = debug_func if debug_func else logger.debug

    obj_type = get_object_type_name(obj)
    # Ensure obj_type is uppercase for consistent matching. This is a
    # schema object type (TABLE/INDEX/...), not a MigrationType.
    obj_type = (
        obj_type.upper()
        if isinstance(obj_type, str)
        else str(obj_type).upper()  # lint: allow-enum-str  schema-object fallback
    )

    # Handle materialized views
    if obj_type == "MATERIALIZED_VIEW":
        obj_type = "VIEW"

    # Normalize schema for matching
    obj_schema = _normalize_schema_for_dialect(obj.schema, dialect or "")

    key = (obj_schema, obj.name.upper(), obj_type)
    is_managed = key in managed_set

    # Enhanced debug logging
    if not is_managed:
        dbg(
            f"Object not in managed set: {key} "
            f"(obj.schema={obj.schema}, normalized={obj_schema}, "
            f"obj_type={obj.object_type}, obj_type.value={obj_type}, "
            f"obj.name={obj.name})"
        )
        # Log a sample of what's in managed_set for debugging
        if managed_set:
            sample_keys = list(managed_set)[:5]
            dbg(f"Sample managed_set keys: {sample_keys}")
    else:
        dbg(f"Object found in managed set: {key}")

    return is_managed
