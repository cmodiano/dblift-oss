"""Object-type comparator specs used by ``_diff_using_snapshot``.

Extracted from ``diff_command.py`` (PR-G5). The constant ``_OBJECT_TYPE_SPECS``
drives the per-object-type comparator wiring loop — keeping it in its own
module makes the dispatcher table reviewable as a list of (input, comparator,
output) tuples without scrolling through the surrounding orchestration.
"""

from typing import List, NamedTuple


class _ObjectTypeSpec(NamedTuple):
    payload_attr: str
    key_func_name: str
    compare_method: str
    needs_dialect: bool
    missing_attr: str
    extra_attr: str
    modified_attr: str


_OBJECT_TYPE_SPECS: List[_ObjectTypeSpec] = [
    _ObjectTypeSpec(
        "views",
        "table_key",
        "compare_views",
        True,
        "missing_views",
        "extra_views",
        "modified_views",
    ),
    _ObjectTypeSpec(
        "indexes",
        "index_key",
        "compare_indexes",
        True,
        "missing_indexes",
        "extra_indexes",
        "modified_indexes",
    ),
    _ObjectTypeSpec(
        "sequences",
        "table_key",
        "compare_sequences",
        True,
        "missing_sequences",
        "extra_sequences",
        "modified_sequences",
    ),
    _ObjectTypeSpec(
        "triggers",
        "index_key",
        "compare_triggers",
        True,
        "missing_triggers",
        "extra_triggers",
        "modified_triggers",
    ),
    _ObjectTypeSpec(
        "events",
        "table_key",
        "compare_events",
        True,
        "missing_events",
        "extra_events",
        "modified_events",
    ),
    _ObjectTypeSpec(
        "procedures",
        "table_key",
        "compare_procedures",
        True,
        "missing_procedures",
        "extra_procedures",
        "modified_procedures",
    ),
    _ObjectTypeSpec(
        "functions",
        "table_key",
        "compare_functions",
        True,
        "missing_functions",
        "extra_functions",
        "modified_functions",
    ),
    _ObjectTypeSpec(
        "packages",
        "table_key",
        "compare_packages",
        True,
        "missing_packages",
        "extra_packages",
        "modified_packages",
    ),
    _ObjectTypeSpec(
        "synonyms",
        "table_key",
        "compare_synonyms",
        True,
        "missing_synonyms",
        "extra_synonyms",
        "modified_synonyms",
    ),
    _ObjectTypeSpec(
        "user_defined_types",
        "table_key",
        "compare_user_defined_types",
        True,
        "missing_user_defined_types",
        "extra_user_defined_types",
        "modified_user_defined_types",
    ),
    _ObjectTypeSpec(
        "extensions",
        "object_name_key",
        "compare_extensions",
        True,
        "missing_extensions",
        "extra_extensions",
        "modified_extensions",
    ),
    _ObjectTypeSpec(
        "foreign_data_wrappers",
        "object_name_key",
        "compare_foreign_data_wrappers",
        False,
        "missing_foreign_data_wrappers",
        "extra_foreign_data_wrappers",
        "modified_foreign_data_wrappers",
    ),
    _ObjectTypeSpec(
        "foreign_servers",
        "object_name_key",
        "compare_foreign_servers",
        False,
        "missing_foreign_servers",
        "extra_foreign_servers",
        "modified_foreign_servers",
    ),
    _ObjectTypeSpec(
        "database_links",
        "table_key",
        "compare_database_links",
        False,
        "missing_database_links",
        "extra_database_links",
        "modified_database_links",
    ),
    _ObjectTypeSpec(
        "linked_servers",
        "object_name_key",
        "compare_linked_servers",
        False,
        "missing_linked_servers",
        "extra_linked_servers",
        "modified_linked_servers",
    ),
    _ObjectTypeSpec(
        "modules",
        "table_key",
        "compare_modules",
        True,
        "missing_modules",
        "extra_modules",
        "modified_modules",
    ),
]
