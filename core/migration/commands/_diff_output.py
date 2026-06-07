"""Diff output rendering: header / footer / per-object-type tree loggers.

Extracted from ``diff_command.py`` (PR-G5). Every function here is a pure
formatter — it consumes a ``Log`` instance plus a ``schema_diff`` / ``result``
payload and emits ``rich`` panels/trees. No mutation of ``self`` state, so
extraction is a mechanical move from staticmethods on ``DiffCommand`` to
module-level functions.
"""

from typing import Any, Callable, List

from rich import box
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree

from core.logger import Log
from core.logger.console import render_panel_to_str, render_tree_to_str
from core.logger.results import DiffResult


def log_diff_header(log: Log, result: DiffResult) -> None:
    """Log the diff summary header block."""

    if result.total_differences == 0:
        panel = Panel(
            "✓ No differences found - schema is in sync",
            title="SCHEMA DIFFERENCES",
            box=box.HEAVY,
            border_style="bold green",
            expand=True,
        )
    else:
        panel = Panel(
            "Differences detected — see sections below",
            title="SCHEMA DIFFERENCES FOUND",
            box=box.HEAVY,
            border_style="bold red",
            expand=True,
        )
    log.console_print(panel)
    log.file_only_info(render_panel_to_str(panel, width=80))


def log_diff_footer(log: Log, result: DiffResult) -> None:
    """Log the diff summary footer/status block."""

    if result.total_differences == 0:
        status = "SUCCESS"
    elif result.error_count > 0:
        status = "FAILED"
    elif result.warning_count > 0:
        status = "WARNING"
    else:
        status = "SUCCESS"

    _STATUS_STYLE = {"SUCCESS": "bold green", "WARNING": "yellow", "FAILED": "bold red"}
    border_style = _STATUS_STYLE[status]

    body = Text()
    body.append(f"Total differences: {result.total_differences}\n")
    if result.error_count > 0:
        body.append(f"  Errors: {result.error_count}\n")
    if result.warning_count > 0:
        body.append(f"  Warnings: {result.warning_count}\n")
    if result.info_count > 0:
        body.append(f"  Info: {result.info_count}\n")
    body.append("Status: ")
    body.append(status, style=border_style)

    panel = Panel(body, title="SUMMARY", box=box.HEAVY, border_style=border_style, expand=True)
    log.info("")
    log.console_print(panel)
    log.file_only_info(render_panel_to_str(panel, width=80))


def log_table_diffs(log: Log, schema_diff: Any) -> None:
    """Log tables section (missing, extra, modified with column/constraint/index details)."""
    if schema_diff.missing_tables:
        tree = Tree(f"Missing Tables ({len(schema_diff.missing_tables)})")
        for table_name in sorted(schema_diff.missing_tables):
            tree.add(table_name)
        log.info("")
        log.info(render_tree_to_str(tree))

    if schema_diff.extra_tables:
        tree = Tree(f"Extra Tables ({len(schema_diff.extra_tables)})")
        for table_name in sorted(schema_diff.extra_tables):
            tree.add(table_name)
        log.info("")
        log.info(render_tree_to_str(tree))

    if schema_diff.modified_tables:
        root = Tree(f"Modified Tables ({len(schema_diff.modified_tables)})")
        for table_diff in schema_diff.modified_tables:
            table_node = root.add(
                f"Table '{table_diff.table_name}' [{table_diff.severity.value.upper()}]"
            )

            if table_diff.missing_columns:
                sub = table_node.add(f"Missing columns ({len(table_diff.missing_columns)})")
                for col in sorted(table_diff.missing_columns):
                    sub.add(col)

            if table_diff.extra_columns:
                sub = table_node.add(f"Extra columns ({len(table_diff.extra_columns)})")
                for col in sorted(table_diff.extra_columns):
                    sub.add(col)

            if table_diff.modified_columns:
                sub = table_node.add(f"Modified columns ({len(table_diff.modified_columns)})")
                for col_diff in table_diff.modified_columns:
                    col_node = sub.add(
                        f"Column '{col_diff.column_name}' [{col_diff.severity.value.upper()}]"
                    )
                    if col_diff.data_type_diff:
                        col_node.add(
                            f"data_type: {col_diff.data_type_diff[0]} → {col_diff.data_type_diff[1]}"
                        )
                    if col_diff.nullable_diff:
                        col_node.add(
                            f"nullable: {col_diff.nullable_diff[0]} → {col_diff.nullable_diff[1]}"
                        )
                    if col_diff.default_diff:
                        expected_default = col_diff.default_diff[0] or "NULL"
                        actual_default = col_diff.default_diff[1] or "NULL"
                        col_node.add(f"default: {expected_default} → {actual_default}")
                    if col_diff.identity_diff:
                        col_node.add(
                            f"identity: {col_diff.identity_diff[0]} → {col_diff.identity_diff[1]}"
                        )
                    if col_diff.computed_diff:
                        col_node.add(
                            f"computed: {col_diff.computed_diff[0]} → {col_diff.computed_diff[1]}"
                        )

            if table_diff.missing_constraints:
                sub = table_node.add(f"Missing constraints ({len(table_diff.missing_constraints)})")
                for constraint in sorted(table_diff.missing_constraints):
                    sub.add(constraint)

            if table_diff.extra_constraints:
                sub = table_node.add(f"Extra constraints ({len(table_diff.extra_constraints)})")
                for constraint in sorted(table_diff.extra_constraints):
                    sub.add(constraint)

            if table_diff.modified_constraints:
                sub = table_node.add(
                    f"Modified constraints ({len(table_diff.modified_constraints)})"
                )
                for constraint_diff in table_diff.modified_constraints:
                    c_node = sub.add(
                        f"Constraint '{constraint_diff.constraint_name}' "
                        f"({constraint_diff.constraint_type}) "
                        f"[{constraint_diff.severity.value.upper()}]"
                    )
                    if constraint_diff.columns_diff:
                        c_node.add(
                            f"columns: {constraint_diff.columns_diff[0]} → {constraint_diff.columns_diff[1]}"
                        )
                    if constraint_diff.references_diff:
                        c_node.add(
                            f"references: {constraint_diff.references_diff[0]} → {constraint_diff.references_diff[1]}"
                        )
                    if constraint_diff.check_clause_diff:
                        c_node.add("check_clause: differs")

            if table_diff.missing_indexes:
                sub = table_node.add(f"Missing indexes ({len(table_diff.missing_indexes)})")
                for index in sorted(table_diff.missing_indexes):
                    sub.add(index)

            if table_diff.extra_indexes:
                sub = table_node.add(f"Extra indexes ({len(table_diff.extra_indexes)})")
                for index in sorted(table_diff.extra_indexes):
                    sub.add(index)

            property_changes = []
            if table_diff.temporary_changed:
                property_changes.append("temporary")
            if table_diff.filegroup_changed:
                property_changes.append("filegroup")
            if table_diff.memory_optimized_changed:
                property_changes.append("memory-optimized")
            if table_diff.system_versioned_changed:
                property_changes.append("system-versioned")
            if table_diff.history_table_changed:
                property_changes.append("history_table")
            if table_diff.partition_method_changed:
                property_changes.append("partition_method")
            if table_diff.partition_columns_changed:
                property_changes.append("partition_columns")
            if table_diff.compress_changed:
                property_changes.append("compress")
            if table_diff.compress_type_changed:
                property_changes.append("compress_type")
            if table_diff.logged_changed:
                property_changes.append("logged")
            if table_diff.organize_by_changed:
                property_changes.append("organize_by")

            if property_changes:
                table_node.add(f"Property changes: {', '.join(property_changes)}")
        log.info("")
        log.info(render_tree_to_str(root))


def _log_simple_listing(log: Log, label: str, items: Any) -> None:
    """Emit a flat Tree (header + N children) for simple missing/extra lists."""
    if not items:
        return
    tree = Tree(f"{label} ({len(items)})")
    for name in sorted(items):
        tree.add(str(name))
    log.info("")
    log.info(render_tree_to_str(tree))


def log_view_diffs(log: Log, schema_diff: Any) -> None:
    """Log views section (missing, extra, modified)."""
    _log_simple_listing(log, "Missing Views", getattr(schema_diff, "missing_views", None))
    _log_simple_listing(log, "Extra Views", getattr(schema_diff, "extra_views", None))

    if hasattr(schema_diff, "modified_views") and schema_diff.modified_views:
        root = Tree(f"Modified Views ({len(schema_diff.modified_views)})")
        for view_diff in schema_diff.modified_views:
            node = root.add(f"View '{view_diff.view_name}' [{view_diff.severity.value.upper()}]")
            if view_diff.definition_changed:
                node.add("definition: changed")
            if view_diff.materialized_changed:
                node.add("materialized: changed")
        log.info("")
        log.info(render_tree_to_str(root))


def log_index_diffs(log: Log, schema_diff: Any) -> None:
    """Log indexes section (missing, extra, modified)."""
    _log_simple_listing(log, "Missing Indexes", getattr(schema_diff, "missing_indexes", None))
    _log_simple_listing(log, "Extra Indexes", getattr(schema_diff, "extra_indexes", None))

    if hasattr(schema_diff, "modified_indexes") and schema_diff.modified_indexes:
        root = Tree(f"Modified Indexes ({len(schema_diff.modified_indexes)})")
        for index_diff in schema_diff.modified_indexes:
            node = root.add(
                f"Index '{index_diff.index_name}' [{index_diff.severity.value.upper()}]"
            )
            if getattr(index_diff, "columns_diff", None):
                node.add(f"columns: {index_diff.columns_diff[0]} → {index_diff.columns_diff[1]}")
            if getattr(index_diff, "unique_diff", None):
                node.add(f"unique: {index_diff.unique_diff[0]} → {index_diff.unique_diff[1]}")
        log.info("")
        log.info(render_tree_to_str(root))


def log_sequence_diffs(log: Log, schema_diff: Any) -> None:
    """Log sequences section (missing, extra only — modified not logged)."""
    _log_simple_listing(log, "Missing Sequences", getattr(schema_diff, "missing_sequences", None))
    _log_simple_listing(log, "Extra Sequences", getattr(schema_diff, "extra_sequences", None))


def log_trigger_diffs(log: Log, schema_diff: Any) -> None:
    """Log triggers section (missing, extra, modified)."""
    _log_simple_listing(log, "Missing Triggers", getattr(schema_diff, "missing_triggers", None))
    _log_simple_listing(log, "Extra Triggers", getattr(schema_diff, "extra_triggers", None))

    if hasattr(schema_diff, "modified_triggers") and schema_diff.modified_triggers:
        root = Tree(f"Modified Triggers ({len(schema_diff.modified_triggers)})")
        for trigger_diff in schema_diff.modified_triggers:
            node = root.add(
                f"Trigger '{trigger_diff.trigger_name}' [{trigger_diff.severity.value.upper()}]"
            )
            if getattr(trigger_diff, "timing_changed", None):
                expected, actual = trigger_diff.timing_changed
                node.add(f"timing: {expected} → {actual}")
            if getattr(trigger_diff, "event_changed", None):
                expected, actual = trigger_diff.event_changed
                node.add(f"event: {expected} → {actual}")
            if getattr(trigger_diff, "definer_changed", None):
                expected, actual = trigger_diff.definer_changed
                node.add(f"definer: {expected} → {actual}")
            if getattr(trigger_diff, "definition_changed", None):
                node.add("definition: changed")
            if getattr(trigger_diff, "enabled_changed", None):
                expected, actual = trigger_diff.enabled_changed
                node.add(f"enabled: {expected} → {actual}")
        log.info("")
        log.info(render_tree_to_str(root))


def log_procedure_diffs(log: Log, schema_diff: Any) -> None:
    """Log procedures section (missing, extra, modified)."""
    _log_simple_listing(log, "Missing Procedures", getattr(schema_diff, "missing_procedures", None))
    _log_simple_listing(log, "Extra Procedures", getattr(schema_diff, "extra_procedures", None))

    if hasattr(schema_diff, "modified_procedures") and schema_diff.modified_procedures:
        root = Tree(f"Modified Procedures ({len(schema_diff.modified_procedures)})")
        for proc_diff in schema_diff.modified_procedures:
            node = root.add(
                f"Procedure '{proc_diff.procedure_name}' [{proc_diff.severity.value.upper()}]"
            )
            if proc_diff.parameters_changed:
                node.add("parameters: changed")
            if proc_diff.definition_changed:
                node.add("definition: changed")
        log.info("")
        log.info(render_tree_to_str(root))


def log_function_diffs(log: Log, schema_diff: Any) -> None:
    """Log functions section (missing, extra, modified)."""
    _log_simple_listing(log, "Missing Functions", getattr(schema_diff, "missing_functions", None))
    _log_simple_listing(log, "Extra Functions", getattr(schema_diff, "extra_functions", None))

    if hasattr(schema_diff, "modified_functions") and schema_diff.modified_functions:
        root = Tree(f"Modified Functions ({len(schema_diff.modified_functions)})")
        for func_diff in schema_diff.modified_functions:
            node = root.add(
                f"Function '{func_diff.function_name}' [{func_diff.severity.value.upper()}]"
            )
            if func_diff.definition_changed:
                node.add("definition: changed")
            if func_diff.parameters_changed:
                expected_params = func_diff.expected_parameters or []
                actual_params = func_diff.actual_parameters or []
                node.add(
                    f"parameters: {expected_params if expected_params else '[]'} → "
                    f"{actual_params if actual_params else '[]'}"
                )
            if func_diff.return_type_changed:
                expected_ret, actual_ret = func_diff.return_type_changed
                node.add(f"return type: {expected_ret} → {actual_ret}")
        log.info("")
        log.info(render_tree_to_str(root))


def log_synonym_diffs(log: Log, schema_diff: Any) -> None:
    """Log synonyms section (missing, extra, modified)."""
    _log_simple_listing(log, "Missing Synonyms", getattr(schema_diff, "missing_synonyms", None))
    _log_simple_listing(log, "Extra Synonyms", getattr(schema_diff, "extra_synonyms", None))

    if hasattr(schema_diff, "modified_synonyms") and schema_diff.modified_synonyms:
        root = Tree(f"Modified Synonyms ({len(schema_diff.modified_synonyms)})")
        for syn_diff in schema_diff.modified_synonyms:
            node = root.add(
                f"Synonym '{syn_diff.synonym_name}' [{syn_diff.severity.value.upper()}]"
            )
            if syn_diff.target_changed:
                expected_target, actual_target = syn_diff.target_changed
                node.add(f"target: {expected_target} → {actual_target}")
            if syn_diff.target_schema_changed:
                expected_schema, actual_schema = syn_diff.target_schema_changed
                node.add(f"target schema: {expected_schema} → {actual_schema}")
            if syn_diff.target_database_changed:
                expected_db, actual_db = syn_diff.target_database_changed
                node.add(f"target database: {expected_db} → {actual_db}")
            if syn_diff.db_link_changed:
                expected_link, actual_link = syn_diff.db_link_changed
                node.add(f"db link: {expected_link} → {actual_link}")
        log.info("")
        log.info(render_tree_to_str(root))


def log_package_diffs(log: Log, schema_diff: Any) -> None:
    """Log packages section (missing, extra, modified)."""
    _log_simple_listing(log, "Missing Packages", getattr(schema_diff, "missing_packages", None))
    _log_simple_listing(log, "Extra Packages", getattr(schema_diff, "extra_packages", None))

    if hasattr(schema_diff, "modified_packages") and schema_diff.modified_packages:
        root = Tree(f"Modified Packages ({len(schema_diff.modified_packages)})")
        for pkg_diff in schema_diff.modified_packages:
            node = root.add(
                f"Package '{pkg_diff.package_name}' [{pkg_diff.severity.value.upper()}]"
            )
            if pkg_diff.spec_changed:
                node.add("specification: changed")
            if pkg_diff.body_changed:
                node.add("body: changed")
        log.info("")
        log.info(render_tree_to_str(root))


def log_user_defined_type_diffs(log: Log, schema_diff: Any) -> None:
    """Log user-defined types section (missing, extra, modified)."""
    _log_simple_listing(
        log,
        "Missing User-Defined Types",
        getattr(schema_diff, "missing_user_defined_types", None),
    )
    _log_simple_listing(
        log,
        "Extra User-Defined Types",
        getattr(schema_diff, "extra_user_defined_types", None),
    )

    if (
        hasattr(schema_diff, "modified_user_defined_types")
        and schema_diff.modified_user_defined_types
    ):
        root = Tree(f"Modified User-Defined Types ({len(schema_diff.modified_user_defined_types)})")
        for udt_diff in schema_diff.modified_user_defined_types:
            root.add(
                f"User-Defined Type '{udt_diff.type_name}' [{udt_diff.severity.value.upper()}]"
            )
        log.info("")
        log.info(render_tree_to_str(root))


def log_extension_diffs(log: Log, schema_diff: Any) -> None:
    """Log extensions section (missing, extra, modified)."""
    _log_simple_listing(log, "Missing Extensions", getattr(schema_diff, "missing_extensions", None))
    _log_simple_listing(log, "Extra Extensions", getattr(schema_diff, "extra_extensions", None))

    if hasattr(schema_diff, "modified_extensions") and schema_diff.modified_extensions:
        root = Tree(f"Modified Extensions ({len(schema_diff.modified_extensions)})")
        for ext_diff in schema_diff.modified_extensions:
            details = []
            if ext_diff.version_changed:
                details.append(
                    f"version {ext_diff.version_changed[0]} → {ext_diff.version_changed[1]}"
                )
            if ext_diff.schema_changed:
                details.append(
                    f"schema {ext_diff.schema_changed[0]} → {ext_diff.schema_changed[1]}"
                )
            detail_str = f" ({'; '.join(details)})" if details else ""
            root.add(
                f"Extension '{ext_diff.extension_name}' [{ext_diff.severity.value.upper()}]{detail_str}"
            )
        log.info("")
        log.info(render_tree_to_str(root))


def log_foreign_data_wrapper_diffs(log: Log, schema_diff: Any) -> None:
    """Log foreign data wrappers section (missing, extra, modified)."""
    _log_simple_listing(
        log,
        "Missing Foreign Data Wrappers",
        getattr(schema_diff, "missing_foreign_data_wrappers", None),
    )
    _log_simple_listing(
        log,
        "Extra Foreign Data Wrappers",
        getattr(schema_diff, "extra_foreign_data_wrappers", None),
    )

    if (
        hasattr(schema_diff, "modified_foreign_data_wrappers")
        and schema_diff.modified_foreign_data_wrappers
    ):
        root = Tree(
            f"Modified Foreign Data Wrappers ({len(schema_diff.modified_foreign_data_wrappers)})"
        )
        for fdw_diff in schema_diff.modified_foreign_data_wrappers:
            root.add(
                f"Foreign Data Wrapper '{fdw_diff.fdw_name}' [{fdw_diff.severity.value.upper()}]"
            )
        log.info("")
        log.info(render_tree_to_str(root))


def log_foreign_server_diffs(log: Log, schema_diff: Any) -> None:
    """Log foreign servers section (missing, extra, modified)."""
    _log_simple_listing(
        log,
        "Missing Foreign Servers",
        getattr(schema_diff, "missing_foreign_servers", None),
    )
    _log_simple_listing(
        log, "Extra Foreign Servers", getattr(schema_diff, "extra_foreign_servers", None)
    )

    if hasattr(schema_diff, "modified_foreign_servers") and schema_diff.modified_foreign_servers:
        root = Tree(f"Modified Foreign Servers ({len(schema_diff.modified_foreign_servers)})")
        for server_diff in schema_diff.modified_foreign_servers:
            root.add(
                f"Foreign Server '{server_diff.server_name}' [{server_diff.severity.value.upper()}]"
            )
        log.info("")
        log.info(render_tree_to_str(root))


def log_event_diffs(log: Log, schema_diff: Any) -> None:
    """Log events section (missing, extra, modified)."""
    _log_simple_listing(log, "Missing Events", getattr(schema_diff, "missing_events", None))
    _log_simple_listing(log, "Extra Events", getattr(schema_diff, "extra_events", None))

    if hasattr(schema_diff, "modified_events") and schema_diff.modified_events:
        root = Tree(f"Modified Events ({len(schema_diff.modified_events)})")
        for event_diff in schema_diff.modified_events:
            root.add(f"Event '{event_diff.event_name}' [{event_diff.severity.value.upper()}]")
        log.info("")
        log.info(render_tree_to_str(root))


DIFF_OBJECT_TYPE_LOGGERS: List[Callable[[Log, Any], None]] = [
    log_table_diffs,
    log_view_diffs,
    log_index_diffs,
    log_sequence_diffs,
    log_trigger_diffs,
    log_procedure_diffs,
    log_function_diffs,
    log_synonym_diffs,
    log_package_diffs,
    log_user_defined_type_diffs,
    log_extension_diffs,
    log_foreign_data_wrapper_diffs,
    log_foreign_server_diffs,
    log_event_diffs,
]
