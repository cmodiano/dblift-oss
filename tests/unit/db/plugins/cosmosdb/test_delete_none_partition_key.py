"""BUG-05 regression: CosmosDB DELETE must use ``NONE_PARTITION_KEY``.

When a document lacks the ``_partitionKey`` field (typical for
``dblift_schema_history`` R__ entries in a partition-keyless container),
the previous code passed ``partition_key=doc_id`` as a fallback. Cosmos
returned 404 because ``doc_id`` is not a valid partition value for a
partitionless container. Repair silently left duplicate history rows
behind.

The fix routes the sentinel through ``db.plugins.cosmosdb.cosmosdb._sdk``
(``NONE_PARTITION_KEY``), which re-exports
``azure.cosmos.partition_key.NonePartitionKeyValue``.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from db.plugins.cosmosdb.cosmosdb.query_executor import CosmosDbQueryExecutor


@pytest.fixture
def cosmos_stub(monkeypatch):
    """Stub the dblift SDK wrapper so tests run without azure-cosmos."""
    sentinel = "__NONE_PK_SENTINEL__"
    sdk_mod = types.ModuleType("db.plugins.cosmosdb.cosmosdb._sdk")
    sdk_mod.NONE_PARTITION_KEY = sentinel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "db.plugins.cosmosdb.cosmosdb._sdk", sdk_mod)
    return types.SimpleNamespace(NonePartitionKeyValue=sentinel)


@pytest.mark.unit
class TestCosmosDbDeleteNonePartitionKey:
    def _executor(self) -> CosmosDbQueryExecutor:
        exec_ = CosmosDbQueryExecutor.__new__(CosmosDbQueryExecutor)
        exec_.connection_manager = MagicMock()
        exec_.log = MagicMock()
        return exec_

    def test_delete_uses_none_sentinel_when_partition_key_missing(self, cosmos_stub):
        exec_ = self._executor()
        container = MagicMock()
        # Document has no ``_partitionKey`` field.
        container.query_items.return_value = iter([{"id": "R__abc", "_partitionKey": None}])
        exec_.connection_manager.get_container_client.return_value = container

        deleted = exec_._execute_delete("DELETE FROM dblift_schema_history WHERE id = 'R__abc'")

        assert deleted == 1
        container.delete_item.assert_called_once_with(
            item="R__abc", partition_key=cosmos_stub.NonePartitionKeyValue
        )

    def test_delete_reads_container_props_for_partition_key_field(self, cosmos_stub):
        """DELETE must read container properties to find the real partition key field."""
        exec_ = self._executor()
        container = MagicMock()
        container.read.return_value = {"partitionKey": {"paths": ["/tenant_id"]}}
        # Document has the actual partition key field, NOT _partitionKey
        container.query_items.return_value = iter([{"id": "doc1", "tenant_id": "tenant-42"}])
        exec_.connection_manager.get_container_client.return_value = container

        deleted = exec_._execute_delete("DELETE FROM users WHERE id = 'doc1'")

        assert deleted == 1
        container.delete_item.assert_called_once_with(item="doc1", partition_key="tenant-42")

    def test_delete_history_container_uses_version_as_partition_key(self, cosmos_stub):
        """Repair-path: history container has /version PK; delete must use c.version value."""
        exec_ = self._executor()
        container = MagicMock()
        container.read.return_value = {"partitionKey": {"paths": ["/version"]}}
        container.query_items.return_value = iter(
            [{"id": "V3__create_products_container.py", "version": "3"}]
        )
        exec_.connection_manager.get_container_client.return_value = container

        deleted = exec_._execute_delete(
            "DELETE FROM dblift_schema_history WHERE script = 'V3__create_products_container.py'"
        )

        assert deleted == 1
        container.delete_item.assert_called_once_with(
            item="V3__create_products_container.py", partition_key="3"
        )

    def test_delete_does_not_fall_back_to_doc_id(self, cosmos_stub):
        """Regression guard: doc_id must never be used as partition_key."""
        exec_ = self._executor()
        container = MagicMock()
        container.query_items.return_value = iter([{"id": "R__xyz"}])
        exec_.connection_manager.get_container_client.return_value = container

        exec_._execute_delete("DELETE FROM h WHERE id = 'R__xyz'")

        call = container.delete_item.call_args
        assert call.kwargs["partition_key"] != "R__xyz"
        assert call.kwargs["partition_key"] == cosmos_stub.NonePartitionKeyValue
