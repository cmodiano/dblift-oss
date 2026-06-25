"""Tests for the Tier-3 ``Table.dialect_options`` plugin-isolation scaffold."""

import pytest

from core.sql_model.table import Table

pytestmark = [pytest.mark.unit]


class TestDialectOptionsScaffold:
    def test_defaults_to_empty_dict(self):
        t = Table(name="t")
        assert t.dialect_options == {}

    def test_set_then_get(self):
        t = Table(name="t")
        t.set_dialect_option("snowflake", "cluster_by", ["created_at"])
        assert t.get_dialect_option("snowflake", "cluster_by") == ["created_at"]

    def test_get_returns_default_when_missing(self):
        t = Table(name="t")
        assert t.get_dialect_option("snowflake", "cluster_by") is None
        assert t.get_dialect_option("snowflake", "cluster_by", default=[]) == []

    def test_set_creates_namespace(self):
        t = Table(name="t")
        t.set_dialect_option("bigquery", "partition_by", "DATE(created_at)")
        assert t.dialect_options == {"bigquery": {"partition_by": "DATE(created_at)"}}

    def test_set_none_records_explicit_null(self):
        t = Table(name="t")
        t.set_dialect_option("ns", "k", None)
        assert "k" in t.dialect_options["ns"]
        assert t.get_dialect_option("ns", "k", default="fallback") is None

    def test_namespaces_isolated(self):
        t = Table(name="t")
        t.set_dialect_option("snowflake", "cluster_by", ["a"])
        t.set_dialect_option("bigquery", "cluster_by", ["b"])
        assert t.get_dialect_option("snowflake", "cluster_by") == ["a"]
        assert t.get_dialect_option("bigquery", "cluster_by") == ["b"]

    def test_round_trip_via_dict(self):
        t = Table(name="t", dialect="snowflake")
        t.set_dialect_option("snowflake", "cluster_by", ["created_at"])
        t.set_dialect_option("snowflake", "data_retention_days", 30)

        restored = Table.from_dict(t.to_dict())

        assert restored.get_dialect_option("snowflake", "cluster_by") == ["created_at"]
        assert restored.get_dialect_option("snowflake", "data_retention_days") == 30

    def test_equality_considers_dialect_options(self):
        a = Table(name="t", dialect="snowflake")
        b = Table(name="t", dialect="snowflake")
        assert a == b

        a.set_dialect_option("snowflake", "cluster_by", ["x"])
        assert a != b

        b.set_dialect_option("snowflake", "cluster_by", ["x"])
        assert a == b
