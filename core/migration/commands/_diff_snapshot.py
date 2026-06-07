"""Snapshot-driven schema diffing.

Extracted from ``diff_command.py`` (PR-G5). The ``run_snapshot_diff`` function
wires the snapshot payload + live introspection through the
``ObjectComparator`` for every object type declared in ``_OBJECT_TYPE_SPECS``.
"""

from typing import Any, Dict, List, Optional

from core.comparison.comparator import ObjectComparator
from core.comparison.type_normalizer import DataTypeNormalizer
from core.logger import Log
from core.logger.results import DiffResult
from core.migration.commands._diff_object_specs import _OBJECT_TYPE_SPECS
from core.migration.snapshots import SchemaSnapshotService
from core.validation.accuracy_validator import AccuracyValidator
from db.base_provider import BaseProvider
from db.provider_capabilities import ensure_provider_connection


def run_snapshot_diff(
    *,
    result: DiffResult,
    snapshot_payload: Any,
    snapshot_metadata: Dict[str, Any],
    ignore_unmanaged: bool,
    snapshot_service: Optional[SchemaSnapshotService],
    provider: Optional[BaseProvider],
    config: Any,
    log: Log,
) -> Optional[DiffResult]:
    """Compare database schema using stored snapshot data.

    Returns ``None`` if the snapshot service or payload is unavailable or
    if a step of the comparison fails — mirroring the prior in-class method's
    contract.
    """
    if not snapshot_service or snapshot_payload is None:
        return None

    try:
        try:
            ensure_provider_connection(provider)
        except Exception as e:
            log.warning(f"Failed to establish database connection: {e}")
            return None

        live_payload = snapshot_service.build_live_payload()

        try:
            ensure_provider_connection(provider)
        except Exception as e:
            log.warning(f"Failed to establish database connection: {e}")
            return None

    except Exception as exc:
        log.warning(f"Unable to introspect live database for snapshot diff: {exc}")
        return None

    default_schema = getattr(config.database, "schema", "") or ""

    # Non-blocking accuracy check: warn if live introspection diverges from snapshot
    try:
        captured_objects = {
            "tables": snapshot_payload.tables,
            "indexes": snapshot_payload.indexes,
        }
        live_objects_for_accuracy: dict[str, list[Any]] = {
            "tables": live_payload.tables,
            "indexes": live_payload.indexes,
        }
        # AccuracyValidator is part of core.validation; called here for the
        # diff-snapshot accuracy report.
        accuracy_result = AccuracyValidator().validate_all(  # type: ignore[no-untyped-call]
            captured_objects,
            live_objects_for_accuracy,
            default_schema,
        )
        if accuracy_result.has_issues():
            log.warning(
                f"Snapshot accuracy check detected differences between snapshot and "
                f"live database ({accuracy_result.get_error_count()} error(s), "
                f"{accuracy_result.get_warning_count()} warning(s)). "
                "Diff results may reflect schema drift."
            )
    except Exception as acc_exc:
        log.warning(f"Could not run snapshot accuracy check: {acc_exc}")

    normalizer = DataTypeNormalizer()
    comparator = ObjectComparator(normalizer, log=log)

    from db.provider_registry import ProviderRegistry

    dialect = getattr(config.database, "type", "").lower()
    _quirks = ProviderRegistry.get_quirks(dialect)

    def normalize_identifier(identifier: Optional[str]) -> str:
        if identifier is None:
            return ""
        cleaned = str(identifier).strip()
        if _quirks.uppercase_identifiers:
            return cleaned.upper()
        return cleaned.lower()

    def schema_for(obj: Any, fallback: str = "") -> str:
        schema_value = getattr(obj, "schema", None)
        if schema_value is not None:
            schema_value = str(schema_value)
        return normalize_identifier(schema_value or fallback)

    def object_name(obj: Any, attr: str = "name") -> str:
        value = getattr(obj, attr, None)
        if value:
            return str(value)
        for candidate in [
            "object_name",
            "index_name",
            "trigger_name",
            "sequence_name",
            "procedure_name",
            "function_name",
        ]:
            candidate_value = getattr(obj, candidate, None)
            if candidate_value:
                return str(candidate_value)
        return ""

    def table_key(obj: Any) -> str:
        obj_name = getattr(obj, "name", None)
        if obj_name is not None:
            obj_name = str(obj_name)
        return f"{schema_for(obj, default_schema)}.{normalize_identifier(obj_name)}"

    def index_key(obj: Any) -> str:
        table_name = getattr(obj, "table_name", None) or getattr(obj, "table", None)
        if table_name is not None:
            table_name = str(table_name)

        obj_name = getattr(obj, "name", None)
        if obj_name is not None:
            obj_name = str(obj_name)

        return (
            f"{schema_for(obj, default_schema)}."
            f"{normalize_identifier(table_name)}."
            f"{normalize_identifier(obj_name)}"
        )

    def build_map(objects: List[Any], key_func: Any) -> Dict[str, Any]:
        mapping: Dict[str, Any] = {}
        for obj in objects or []:
            key = key_func(obj)
            if key:
                mapping[key] = obj
        return mapping

    schema_diff = comparator.compare_schemas(
        expected_tables=snapshot_payload.tables,
        actual_tables=live_payload.tables,
        dialect=dialect,
        schema_name=default_schema,
    )

    result.expected_payload = snapshot_payload

    def compare_maps(expected_map: Any, actual_map: Any, compare_fn: Any) -> Any:
        missing_keys = set(expected_map.keys()) - set(actual_map.keys())
        extra_keys = set(actual_map.keys()) - set(expected_map.keys())
        intersection = set(expected_map.keys()) & set(actual_map.keys())

        missing = [object_name(expected_map[key]) for key in missing_keys]
        extra = [object_name(actual_map[key]) for key in extra_keys]
        missing = [name for name in missing if name]
        extra = [name for name in extra if name]
        modified = []
        for key in intersection:
            diff = compare_fn(expected_map[key], actual_map[key])
            if diff and getattr(diff, "has_diffs", True):
                modified.append(diff)
        return missing, extra, modified

    _key_funcs = {
        "table_key": table_key,
        "index_key": index_key,
        "object_name_key": lambda obj: object_name(obj),
    }

    for spec in _OBJECT_TYPE_SPECS:
        key_fn = _key_funcs[spec.key_func_name]
        expected_map = build_map(getattr(snapshot_payload, spec.payload_attr, None) or [], key_fn)
        actual_map = build_map(getattr(live_payload, spec.payload_attr, None) or [], key_fn)
        compare_fn = getattr(comparator, spec.compare_method)
        if spec.needs_dialect:

            def bound_compare(e: Any, a: Any, fn: Any = compare_fn) -> Any:
                """Adapt a dialect-aware compare fn into the 2-arg shape expected by compare_maps."""
                return fn(e, a, dialect)

        else:
            bound_compare = compare_fn
        missing, extra, modified = compare_maps(expected_map, actual_map, bound_compare)
        setattr(schema_diff, spec.missing_attr, missing)
        setattr(schema_diff, spec.extra_attr, extra)
        setattr(schema_diff, spec.modified_attr, modified)

    if not ignore_unmanaged:
        result.set_unmanaged_objects(
            tables=schema_diff.extra_tables,
            views=schema_diff.extra_views,
            procedures=schema_diff.extra_procedures,
            functions=schema_diff.extra_functions,
            triggers=schema_diff.extra_triggers,
        )
    else:
        result.set_unmanaged_objects()
        schema_diff.extra_tables = []
        schema_diff.extra_views = []
        schema_diff.extra_indexes = []
        schema_diff.extra_sequences = []
        schema_diff.extra_triggers = []
        schema_diff.extra_procedures = []
        schema_diff.extra_functions = []
        schema_diff.extra_packages = []
        schema_diff.extra_synonyms = []
        schema_diff.extra_user_defined_types = []
        schema_diff.extra_extensions = []
        schema_diff.extra_events = []
        schema_diff.extra_foreign_data_wrappers = []
        schema_diff.extra_foreign_servers = []
        schema_diff.extra_database_links = []
        schema_diff.extra_linked_servers = []
        schema_diff.extra_modules = []

    schema_diff._calculate_diffs()
    result.set_schema_diff(schema_diff)
    result.target_schema = default_schema

    if snapshot_metadata:
        result.cli_options.setdefault("snapshot", snapshot_metadata)

    return result
