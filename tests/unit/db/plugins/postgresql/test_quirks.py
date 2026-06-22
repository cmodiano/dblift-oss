"""Tests for PostgreSQL dialect quirks."""

from unittest.mock import MagicMock

import pytest

from core.sql_model.table import Table
from core.sql_model.user_defined_type import UserDefinedType
from db.plugins.postgresql.quirks import PostgresqlQuirks


@pytest.mark.unit
def test_filter_user_defined_types_excludes_relation_row_types():
    query_executor = MagicMock()
    query_executor.execute_query.return_value = [{"relname": "mv_parent_probe"}]
    extractor = MagicMock()
    extractor.provider.query_executor = query_executor
    extractor.connection = object()

    relation_type = UserDefinedType(
        name="mv_parent_probe",
        type_category="C",
        dialect="postgresql",
    )
    explicit_type = UserDefinedType(
        name="address_type",
        type_category="C",
        dialect="postgresql",
    )

    result = PostgresqlQuirks().filter_user_defined_types(
        extractor,
        "TEST_SCHEMA",
        [relation_type, explicit_type],
        lambda schema, include_views=False: [Table(name="parent_probe", schema=schema)],
    )

    assert result == [explicit_type]
    query_executor.execute_query.assert_called_once()
