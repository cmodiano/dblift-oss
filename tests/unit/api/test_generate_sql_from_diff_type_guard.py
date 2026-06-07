"""BUG-06 regression: generate_sql_from_diff rejects non-SchemaDiff inputs.

Before the fix, passing a raw dict (e.g. a snapshot JSON) to ``diff=`` crashed
with ``AttributeError: 'dict' object has no attribute 'modified_tables'`` deep
inside diff_sql_generator.generate_from_diff. The type guard now rejects this
up front with an actionable error message.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.client import DBLiftClient


def _make_client() -> DBLiftClient:
    client = DBLiftClient.__new__(DBLiftClient)
    client.events = MagicMock()
    client.dialect = "postgresql"
    return client


@pytest.mark.unit
class TestGenerateSqlFromDiffTypeGuard:
    def test_dict_input_rejected_with_actionable_error(self):
        client = _make_client()
        snapshot_like = {"tables": [], "views": []}

        result = client.generate_sql_from_diff(diff=snapshot_like)

        assert result.success is False
        assert result.error_message is not None
        assert "SchemaDiff" in result.error_message
        assert "dict" in result.error_message
        assert "ObjectComparator" in result.error_message or "diff_result" in result.error_message

    def test_none_input_still_rejected(self):
        client = _make_client()

        result = client.generate_sql_from_diff()

        assert result.success is False
        assert "No schema diff provided" in (result.error_message or "")

    def test_list_input_rejected(self):
        client = _make_client()

        result = client.generate_sql_from_diff(diff=["not", "a", "diff"])

        assert result.success is False
        assert "SchemaDiff" in (result.error_message or "")
        assert "list" in (result.error_message or "")
