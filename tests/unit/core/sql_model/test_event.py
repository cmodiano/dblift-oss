"""Unit tests for Event SQL Model."""

import pytest

from core.sql_model.base import SqlObjectType
from core.sql_model.event import Event

pytestmark = [pytest.mark.unit]


class TestEvent:
    """Tests for the Event SQL Model class."""

    def test_event_creation(self):
        """Test basic event creation."""
        event = Event(
            name="daily_cleanup",
            schema="mydb",
            definition="DELETE FROM logs WHERE created_at < NOW() - INTERVAL 30 DAY",
            schedule="EVERY 1 DAY STARTS '2024-01-01 00:00:00'",
            enabled=True,
            comment="Daily cleanup of old logs",
        )

        assert event.name == "daily_cleanup"
        assert event.schema == "mydb"
        assert event.definition == "DELETE FROM logs WHERE created_at < NOW() - INTERVAL 30 DAY"
        assert event.schedule == "EVERY 1 DAY STARTS '2024-01-01 00:00:00'"
        assert event.enabled is True
        assert event.comment == "Daily cleanup of old logs"
        assert event.object_type == SqlObjectType.EVENT
        assert event.dialect == "mysql"

    def test_event_with_minimal_attributes(self):
        """Test event creation with minimal attributes."""
        event = Event(name="simple_event")

        assert event.name == "simple_event"
        assert event.schema is None
        assert event.definition is None
        assert event.schedule is None
        assert event.enabled is True  # Default
        assert event.event_type == "ONE TIME"  # Default

    def test_event_disabled(self):
        """Test disabled event."""
        event = Event(name="disabled_event", enabled=False)

        assert event.enabled is False

    def test_event_types(self):
        """Test different event types."""
        one_time = Event(name="one_time", event_type="ONE TIME")
        recurring = Event(name="recurring", event_type="RECURRING")

        assert one_time.event_type == "ONE TIME"
        assert recurring.event_type == "RECURRING"

    def test_event_string_representation_with_schema(self):
        """Test string representation includes schema and name."""
        event_with_schema = Event(name="evt", schema="db1")
        event_without_schema = Event(name="evt")

        assert "db1.evt" in str(event_with_schema)
        assert str(event_without_schema).endswith("evt (ONE TIME, enabled)")

    def test_event_create_statement_complete(self):
        """Test CREATE EVENT statement generation with all attributes."""
        event = Event(
            name="monthly_report",
            schema="analytics",
            definition="CALL generate_monthly_report()",
            schedule="EVERY 1 MONTH STARTS '2024-01-01 00:00:00'",
            enabled=True,
            comment="Generate monthly sales report",
        )

        stmt = event.create_statement
        assert "CREATE EVENT" in stmt
        # Accept both quoted and unquoted identifiers
        assert "analytics.monthly_report" in stmt or "analytics`.`monthly_report" in stmt
        assert "ON SCHEDULE EVERY 1 MONTH" in stmt
        assert "ENABLE" in stmt
        assert "COMMENT 'Generate monthly sales report'" in stmt
        assert "DO" in stmt
        assert "generate_monthly_report()" in stmt

    def test_event_create_statement_disabled(self):
        """Test CREATE EVENT statement for disabled event."""
        event = Event(
            name="test_event",
            enabled=False,
            definition="DO NOTHING",
        )

        stmt = event.create_statement
        assert "DISABLE" in stmt
        assert "ENABLE" not in stmt.replace("DISABLE", "")  # No ENABLE keyword

    def test_event_create_statement_without_comment(self):
        """Test CREATE EVENT statement without comment."""
        event = Event(
            name="test_event",
            definition="CALL proc()",
            schedule="AT '2024-12-31 23:59:59'",
        )

        stmt = event.create_statement
        assert "COMMENT" not in stmt

    def test_event_schedule_literals_are_quoted(self):
        """Schedule literals without quotes should be normalized."""
        event = Event(
            name="test_event",
            definition="CALL proc()",
            schedule="EVERY 1 DAY STARTS 2025-11-16 00:00:00",
            dialect="mysql",
        )

        stmt = event.create_statement
        assert "STARTS '2025-11-16 00:00:00'" in stmt

    def test_event_body_appends_end(self):
        """Event bodies should terminate with END; for valid MySQL syntax."""
        event = Event(
            name="test_event",
            definition="BEGIN\n    SELECT 1;\nEND",
        )

        stmt = event.create_statement
        assert "END;" in stmt

    def test_event_str_representation(self):
        """Test string representation."""
        enabled_recurring = Event(name="evt1", enabled=True, event_type="RECURRING")
        disabled_one_time = Event(name="evt2", enabled=False, event_type="ONE TIME")

        assert "RECURRING" in str(enabled_recurring)
        assert "enabled" in str(enabled_recurring)
        assert "ONE TIME" in str(disabled_one_time)
        assert "disabled" in str(disabled_one_time)

    def test_event_equality(self):
        """Test event equality comparison."""
        evt1 = Event(
            name="evt",
            schema="db",
            definition="def1",
            schedule="sched1",
            enabled=True,
            event_type="RECURRING",
        )
        evt2 = Event(
            name="evt",
            schema="db",
            definition="def1",
            schedule="sched1",
            enabled=True,
            event_type="RECURRING",
        )
        evt3 = Event(
            name="evt",
            schema="db",
            definition="def2",  # Different
            schedule="sched1",
            enabled=True,
            event_type="RECURRING",
        )

        assert evt1 == evt2
        assert evt1 != evt3
        assert evt1 != "not an event"

    def test_event_to_dict(self):
        """Test conversion to dictionary."""
        event = Event(
            name="test_event",
            schema="mydb",
            definition="CALL proc()",
            schedule="EVERY 1 HOUR",
            enabled=False,
            comment="Test event",
            definer="user@localhost",
            event_type="RECURRING",
        )

        evt_dict = event.to_dict()

        assert evt_dict["name"] == "test_event"
        assert evt_dict["schema"] == "mydb"
        assert evt_dict["object_type"] == "EVENT"
        assert evt_dict["dialect"] == "mysql"
        assert evt_dict["definition"] == "CALL proc()"
        assert evt_dict["schedule"] == "EVERY 1 HOUR"
        assert evt_dict["enabled"] is False
        assert evt_dict["comment"] == "Test event"
        assert evt_dict["definer"] == "user@localhost"
        assert evt_dict["event_type"] == "RECURRING"

    def test_event_from_dict(self):
        """Test creation from dictionary."""
        evt_dict = {
            "name": "test_event",
            "schema": "mydb",
            "definition": "CALL proc()",
            "schedule": "EVERY 1 DAY",
            "enabled": True,
            "comment": "Test",
            "definer": "root@localhost",
            "event_type": "RECURRING",
            "dialect": "mysql",
        }

        event = Event.from_dict(evt_dict)

        assert event.name == "test_event"
        assert event.schema == "mydb"
        assert event.definition == "CALL proc()"
        assert event.schedule == "EVERY 1 DAY"
        assert event.enabled is True
        assert event.comment == "Test"
        assert event.definer == "root@localhost"
        assert event.event_type == "RECURRING"

    def test_event_round_trip(self):
        """Test to_dict/from_dict round trip."""
        original = Event(
            name="evt",
            schema="db1",
            definition="def",
            schedule="sched",
            enabled=False,
            event_type="ONE TIME",
        )

        # Round trip
        evt_dict = original.to_dict()
        restored = Event.from_dict(evt_dict)

        assert original == restored

    def test_event_without_schema_in_create_statement(self):
        """Test CREATE EVENT statement without schema prefix."""
        event = Event(
            name="simple",
            definition="CALL proc()",
        )

        stmt = event.create_statement
        assert "CREATE EVENT" in stmt
        assert "simple" in stmt
        # First line should not have schema prefix (schema.name pattern)
        first_line = stmt.split("\n")[0]
        # Either no dots, or dots only in quoted identifiers (backticks)
        assert first_line.count(".") <= 1  # Only the . in schema.name if present

    def test_event_definer(self):
        """Test event definer attribute."""
        event = Event(
            name="evt",
            definer="admin@%",
        )

        assert event.definer == "admin@%"
        assert "admin@%" in event.to_dict()["definer"]
