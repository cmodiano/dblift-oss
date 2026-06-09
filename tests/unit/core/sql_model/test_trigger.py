"""Tests for the Trigger SQL model."""

import pytest

from core.sql_model.trigger import Trigger

pytestmark = [pytest.mark.unit]


def test_oracle_trigger_body_is_wrapped_and_terminated():
    trigger = Trigger(
        name="TRG_CUSTOMERS_AUDIT",
        table_name="CUSTOMERS",
        schema="DBLIFT_TEST",
        timing="AFTER",
        events=["UPDATE"],
        orientation="ROW",
        dialect="oracle",
        definition="INSERT INTO audit_log(customer_id) VALUES (:NEW.customer_id)",
    )

    sql = trigger.create_statement

    assert "CREATE TRIGGER" in sql
    assert "BEGIN" in sql
    assert "END;" in sql
    assert sql.strip().endswith("/")


def test_mysql_trigger_definer_is_quoted():
    trigger = Trigger(
        name="trg_users_updated_at",
        table_name="users",
        schema="store_app_metadata",
        timing="BEFORE",
        events=["UPDATE"],
        orientation="ROW",
        dialect="mysql",
        definer="root@%",
        definition="SET NEW.updated_at = CURRENT_TIMESTAMP",
    )

    sql = trigger.create_statement
    assert "DEFINER = `root`@`%`" in sql


def test_trigger_with_execution_order():
    """Test trigger with execution_order property."""
    trigger = Trigger(
        name="trg_users_audit",
        table_name="users",
        timing="AFTER",
        events=["INSERT", "UPDATE"],
        execution_order=1,
        dialect="postgresql",
    )

    assert trigger.execution_order == 1


def test_trigger_execution_order_serialization():
    """Test trigger execution_order in to_dict and from_dict."""
    trigger = Trigger(
        name="trg_users_audit",
        table_name="users",
        timing="AFTER",
        events=["INSERT"],
        execution_order=2,
        dialect="postgresql",
    )
    data = trigger.to_dict()

    assert data.get("execution_order") == 2

    restored = Trigger.from_dict(data)
    assert restored.execution_order == 2
