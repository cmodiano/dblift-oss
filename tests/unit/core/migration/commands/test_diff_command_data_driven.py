"""Unit tests for the data-driven snapshot-diff helper (story 12-20).

Originally tested the in-class ``DiffCommand._diff_using_snapshot`` method;
post-PR #301 the comparator wiring moved to the module-level
``run_snapshot_diff`` helper in ``_diff_snapshot.py``. These tests were
retargeted in PR-test-hygiene to call the new helper directly.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from core.comparison.diff_models import SchemaDiff
from core.logger.results import DiffResult
from core.migration.commands._diff_object_specs import _OBJECT_TYPE_SPECS
from core.migration.commands._diff_snapshot import run_snapshot_diff
from core.migration.commands.diff_command import DiffCommand

# ---------------------------------------------------------------------------
# Structural tests (AC#6 — config table validation)
# ---------------------------------------------------------------------------


def test_object_type_specs_has_16_entries():
    """_OBJECT_TYPE_SPECS contains exactly 16 entries (one per object type)."""
    assert len(_OBJECT_TYPE_SPECS) == 16


def test_all_payload_attrs_are_unique():
    """No duplicate payload_attr across the 14 specs."""
    attrs = [s.payload_attr for s in _OBJECT_TYPE_SPECS]
    assert len(attrs) == len(set(attrs))


def test_dialect_flag_for_non_dialect_methods():
    """foreign_data_wrappers, foreign_servers, database_links, linked_servers have needs_dialect=False; all others True."""
    no_dialect = {"foreign_data_wrappers", "foreign_servers", "database_links", "linked_servers"}
    for spec in _OBJECT_TYPE_SPECS:
        if spec.payload_attr in no_dialect:
            assert not spec.needs_dialect, f"{spec.payload_attr} should have needs_dialect=False"
        else:
            assert spec.needs_dialect, f"{spec.payload_attr} should have needs_dialect=True"


def test_key_func_mapping_coherent():
    """indexes/triggers use index_key; extensions/fdws/foreign_servers/linked_servers use object_name_key; others use table_key."""
    index_key_types = {"indexes", "triggers"}
    object_name_key_types = {
        "extensions",
        "foreign_data_wrappers",
        "foreign_servers",
        "linked_servers",
    }
    for spec in _OBJECT_TYPE_SPECS:
        if spec.payload_attr in index_key_types:
            assert spec.key_func_name == "index_key", f"{spec.payload_attr} should use index_key"
        elif spec.payload_attr in object_name_key_types:
            assert (
                spec.key_func_name == "object_name_key"
            ), f"{spec.payload_attr} should use object_name_key"
        else:
            assert spec.key_func_name == "table_key", f"{spec.payload_attr} should use table_key"


def test_all_diff_attr_triplets_are_unique():
    """Each (missing_attr, extra_attr, modified_attr) triplet is unique across all specs."""
    triplets = [(s.missing_attr, s.extra_attr, s.modified_attr) for s in _OBJECT_TYPE_SPECS]
    assert len(triplets) == len(set(triplets))


# ---------------------------------------------------------------------------
# Behavioural tests (AC#6 — loop execution)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_dependencies():
    """Create mock dependencies for DiffCommand."""
    config = Mock()
    config.database.type = "postgresql"
    config.database.schema = "public"

    return {
        "config": config,
        "log": Mock(),
        "provider": Mock(),
        "script_manager": Mock(),
        "history_manager": Mock(),
        "validator": Mock(),
        "execution_engine": Mock(),
        "migration_helpers": Mock(),
        "state_manager": Mock(),
        "migration_ui": Mock(),
        "migration_rules": Mock(),
        "snapshot_service": Mock(),
    }


def _make_diff_command(deps):
    return DiffCommand(
        config=deps["config"],
        log=deps["log"],
        provider=deps["provider"],
        script_manager=deps["script_manager"],
        history_manager=deps["history_manager"],
        validator=deps["validator"],
        execution_engine=deps["execution_engine"],
        migration_helpers=deps["migration_helpers"],
        state_manager=deps["state_manager"],
        migration_ui=deps["migration_ui"],
        migration_rules=deps["migration_rules"],
        snapshot_service=deps["snapshot_service"],
    )


def _invoke_run_snapshot_diff(cmd, result, payload, metadata, ignore_unmanaged):
    """Call run_snapshot_diff with dependencies sourced from the DiffCommand,
    matching the wiring the orchestrator does at runtime.
    """
    return run_snapshot_diff(
        result=result,
        snapshot_payload=payload,
        snapshot_metadata=metadata,
        ignore_unmanaged=ignore_unmanaged,
        snapshot_service=cmd.snapshot_service,
        provider=cmd.provider,
        config=cmd.config,
        log=cmd.log,
    )


def _make_payload_with_common_objects():
    """Create snapshot/live payloads with one common object per type so compare_fn is called."""
    snapshot_payload = MagicMock()
    live_payload = MagicMock()

    for spec in _OBJECT_TYPE_SPECS:
        obj = MagicMock()
        obj.name = "test_obj"
        obj.schema = "public"
        obj.table_name = "test_table"
        setattr(snapshot_payload, spec.payload_attr, [obj])

        obj2 = MagicMock()
        obj2.name = "test_obj"
        obj2.schema = "public"
        obj2.table_name = "test_table"
        setattr(live_payload, spec.payload_attr, [obj2])

    snapshot_payload.tables = []
    live_payload.tables = []

    return snapshot_payload, live_payload


def _setup_comparator_mock():
    """Create a comparator mock that returns a real SchemaDiff from compare_schemas."""
    comparator = MagicMock()
    schema_diff = SchemaDiff(object_name="public", schema_name="public")
    comparator.compare_schemas.return_value = schema_diff
    for spec in _OBJECT_TYPE_SPECS:
        diff_result = MagicMock()
        diff_result.has_diffs = False
        getattr(comparator, spec.compare_method).return_value = diff_result
    return comparator


def test_diff_loop_calls_all_16_compare_methods(mock_dependencies):
    """The data-driven loop calls each of the 14 compare_* methods exactly once."""
    cmd = _make_diff_command(mock_dependencies)
    snapshot_payload, live_payload = _make_payload_with_common_objects()

    mock_dependencies["snapshot_service"].build_live_payload.return_value = live_payload

    comparator = _setup_comparator_mock()
    result = DiffResult()

    with patch("core.migration.commands._diff_snapshot.ObjectComparator", return_value=comparator):
        with patch("core.migration.commands._diff_snapshot.DataTypeNormalizer"):
            diff_result = _invoke_run_snapshot_diff(cmd, result, snapshot_payload, {}, False)

    assert diff_result is not None, "_diff_using_snapshot returned None unexpectedly"
    called_methods = {name for name, _, _ in comparator.method_calls}
    for spec in _OBJECT_TYPE_SPECS:
        assert (
            spec.compare_method in called_methods
        ), f"{spec.compare_method} was not called by the data-driven loop"


def test_views_uses_table_key():
    """Views are indexed by schema.name (table_key)."""
    spec = next(s for s in _OBJECT_TYPE_SPECS if s.payload_attr == "views")
    assert spec.key_func_name == "table_key"


def test_indexes_uses_index_key():
    """Indexes are indexed by schema.table.name (index_key)."""
    spec = next(s for s in _OBJECT_TYPE_SPECS if s.payload_attr == "indexes")
    assert spec.key_func_name == "index_key"


def test_no_dialect_for_foreign_data_wrappers(mock_dependencies):
    """compare_foreign_data_wrappers is called without dialect parameter."""
    cmd = _make_diff_command(mock_dependencies)
    snapshot_payload, live_payload = _make_payload_with_common_objects()

    mock_dependencies["snapshot_service"].build_live_payload.return_value = live_payload

    comparator = _setup_comparator_mock()
    result = DiffResult()

    with patch("core.migration.commands._diff_snapshot.ObjectComparator", return_value=comparator):
        with patch("core.migration.commands._diff_snapshot.DataTypeNormalizer"):
            diff_result = _invoke_run_snapshot_diff(cmd, result, snapshot_payload, {}, False)

    assert diff_result is not None, "_diff_using_snapshot returned None unexpectedly"
    # compare_foreign_data_wrappers should have been called with 2 args (e, a) — no dialect
    fdw_calls = comparator.compare_foreign_data_wrappers.call_args_list
    assert len(fdw_calls) > 0, "compare_foreign_data_wrappers was never called — test is vacuous"
    for call_obj in fdw_calls:
        args, kwargs = call_obj
        assert (
            len(args) == 2
        ), f"compare_foreign_data_wrappers called with {len(args)} args, expected 2 (no dialect)"


def test_schema_diff_attributes_set_for_each_type(mock_dependencies):
    """setattr is called on all 14 x 3 attributes of schema_diff."""
    cmd = _make_diff_command(mock_dependencies)

    snapshot_payload = MagicMock()
    live_payload = MagicMock()
    for spec in _OBJECT_TYPE_SPECS:
        setattr(snapshot_payload, spec.payload_attr, [])
        setattr(live_payload, spec.payload_attr, [])
    snapshot_payload.tables = []
    live_payload.tables = []

    mock_dependencies["snapshot_service"].build_live_payload.return_value = live_payload

    comparator = _setup_comparator_mock()
    result = DiffResult()

    with patch("core.migration.commands._diff_snapshot.ObjectComparator", return_value=comparator):
        with patch("core.migration.commands._diff_snapshot.DataTypeNormalizer"):
            _invoke_run_snapshot_diff(cmd, result, snapshot_payload, {}, False)

    schema_diff = result.schema_diff
    for spec in _OBJECT_TYPE_SPECS:
        assert (
            getattr(schema_diff, spec.missing_attr, None) == []
        ), f"schema_diff.{spec.missing_attr} should be [] (empty list set by loop)"
        assert (
            getattr(schema_diff, spec.extra_attr, None) == []
        ), f"schema_diff.{spec.extra_attr} should be [] (empty list set by loop)"
        assert (
            getattr(schema_diff, spec.modified_attr, None) == []
        ), f"schema_diff.{spec.modified_attr} should be [] (empty list set by loop)"


def test_existing_regression_no_service(mock_dependencies):
    """_diff_using_snapshot returns None when snapshot_service is None."""
    mock_dependencies["snapshot_service"] = None
    cmd = _make_diff_command(mock_dependencies)

    result = DiffResult()
    assert _invoke_run_snapshot_diff(cmd, result, None, {}, False) is None
