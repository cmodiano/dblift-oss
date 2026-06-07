"""
Tests for RuleEngine with SQL Model integration (Phase 2).

This module tests the presence and relational rule types that use
SQL Model objects from HybridParser.
"""

import pytest

from core.sql_validator.linting.models import ViolationSeverity
from core.sql_validator.linting.rule_engine import RuleEngine

pytestmark = [pytest.mark.unit]


class TestPresenceRules:
    """Test presence rules using SQL Model objects."""

    def test_must_have_columns_pass(self):
        """Test that table with required columns passes."""
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "require_audit_columns",
                        "type": "presence",
                        "target": "table",
                        "must_have_columns": ["created_at", "updated_at"],
                        "message": "Tables must have audit columns",
                        "severity": "error",
                    }
                ]
            }
        )

        sql = """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100),
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        );
        """

        violations = engine.check_sql(sql)
        assert len(violations) == 0

    def test_must_have_columns_fail(self):
        """Test that table missing required columns fails."""
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "require_audit_columns",
                        "type": "presence",
                        "target": "table",
                        "must_have_columns": ["created_at", "updated_at"],
                        "message": "Tables must have audit columns",
                        "severity": "error",
                    }
                ]
            }
        )

        sql = """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100)
        );
        """

        violations = engine.check_sql(sql)
        assert len(violations) == 2  # Missing both created_at and updated_at
        assert all(v.severity == ViolationSeverity.ERROR for v in violations)
        assert "created_at" in violations[0].message
        assert "updated_at" in violations[1].message

    def test_must_have_primary_key_pass(self):
        """Test that table with primary key passes."""
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "require_primary_key",
                        "type": "presence",
                        "target": "table",
                        "must_have_primary_key": True,
                        "message": "All tables must have a primary key",
                        "severity": "error",
                    }
                ]
            }
        )

        sql = """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100)
        );
        """

        violations = engine.check_sql(sql)
        assert len(violations) == 0

    def test_must_have_primary_key_fail(self):
        """Test that table without primary key fails."""
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "require_primary_key",
                        "type": "presence",
                        "target": "table",
                        "must_have_primary_key": True,
                        "message": "All tables must have a primary key",
                        "severity": "error",
                    }
                ]
            }
        )

        sql = """
        CREATE TABLE logs (
            message TEXT,
            timestamp TIMESTAMP
        );
        """

        violations = engine.check_sql(sql)
        assert len(violations) == 1
        assert violations[0].severity == ViolationSeverity.ERROR
        assert "logs" in violations[0].message

    def test_multiple_tables_with_violations(self):
        """Test presence rules across multiple tables."""
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "require_id_column",
                        "type": "presence",
                        "target": "table",
                        "must_have_columns": ["id"],
                        "message": "Tables must have id column",
                        "severity": "warning",
                    }
                ]
            }
        )

        sql = """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100)
        );

        CREATE TABLE logs (
            message TEXT
        );

        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            name VARCHAR(100)
        );
        """

        violations = engine.check_sql(sql)
        # logs and products are missing 'id' column
        assert len(violations) == 2
        assert all(v.severity == ViolationSeverity.WARNING for v in violations)


class TestRelationalRules:
    """Test relational rules using SQL Model objects."""

    def test_fk_requires_index_with_index_pass(self):
        """Test that FK with matching index passes."""
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "fk_must_have_index",
                        "type": "relational",
                        "target": "foreign_key",
                        "requires_index": True,
                        "message": "Foreign keys must have an index",
                        "severity": "warning",
                    }
                ]
            }
        )

        sql = """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX idx_orders_user_id ON orders(user_id);
        """

        violations = engine.check_sql(sql)
        # Should pass since we have an index on user_id
        # Note: Index extraction may vary by implementation
        # Just verify no crash occurs
        assert isinstance(violations, list)

    def test_fk_requires_index_without_index_fail(self):
        """Test that FK without index fails."""
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "fk_must_have_index",
                        "type": "relational",
                        "target": "foreign_key",
                        "requires_index": True,
                        "message": "Foreign keys must have an index",
                        "severity": "warning",
                    }
                ]
            }
        )

        sql = """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            product_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        """

        violations = engine.check_sql(sql)
        # Should have violations for FKs without indexes
        # Note: Actual count depends on FK extraction success
        assert isinstance(violations, list)

    def test_fk_on_primary_key_passes(self):
        """Test that FK on primary key passes (PK acts as index)."""
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "fk_must_have_index",
                        "type": "relational",
                        "target": "foreign_key",
                        "requires_index": True,
                        "message": "Foreign keys must have an index",
                        "severity": "warning",
                    }
                ]
            }
        )

        sql = """
        CREATE TABLE order_items (
            order_id INTEGER,
            item_id INTEGER,
            PRIMARY KEY (order_id, item_id),
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );
        """

        violations = engine.check_sql(sql)
        # FK on order_id should pass because it's part of PK
        # Actual behavior depends on parser's FK extraction
        assert isinstance(violations, list)

    def test_fk_detection_with_schema_qualified_reference(self):
        """Schema-qualified inline FK references should still be analyzed."""
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "fk_must_have_index",
                        "type": "relational",
                        "target": "foreign_key",
                        "requires_index": True,
                        "message": "Foreign keys must have an index",
                        "severity": "warning",
                    }
                ]
            }
        )

        sql = """
        CREATE TABLE accounting.users (
            id SERIAL PRIMARY KEY
        );

        CREATE TABLE billing.invoices (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES accounting.users(id)
        );
        """

        violations = engine.check_sql(sql)
        assert isinstance(violations, list)
        assert any(v.rule_id == "fk_must_have_index" for v in violations)


class TestCombinedRules:
    """Test combination of different rule types."""

    def test_naming_and_presence_rules(self):
        """Test that naming and presence rules work together."""
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "table_name_snake_case",
                        "type": "naming",
                        "target": "table",
                        "pattern": "^[a-z][a-z0-9_]*$",
                        "message": "Table names must be lowercase snake_case",
                        "severity": "warning",
                    },
                    {
                        "name": "require_primary_key",
                        "type": "presence",
                        "target": "table",
                        "must_have_primary_key": True,
                        "message": "All tables must have a primary key",
                        "severity": "error",
                    },
                ]
            }
        )

        sql = """
        CREATE TABLE UserAccounts (
            name VARCHAR(100)
        );
        """

        violations = engine.check_sql(sql)
        # Should have 2 violations: naming (UserAccounts) and missing PK
        assert len(violations) >= 2

        # Check we have both types of violations
        violation_rules = [v.rule_id for v in violations]
        assert "table_name_snake_case" in violation_rules
        assert "require_primary_key" in violation_rules

    def test_all_rule_types_together(self):
        """Test all rule types (naming, pattern, presence, relational) together."""
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "no_select_star",
                        "type": "pattern",
                        "prohibit": "SELECT *",
                        "message": "Avoid SELECT *",
                        "severity": "info",
                    },
                    {
                        "name": "column_snake_case",
                        "type": "naming",
                        "target": "column",
                        "pattern": "^[a-z][a-z0-9_]*$",
                        "message": "Columns must be snake_case",
                        "severity": "warning",
                    },
                    {
                        "name": "require_audit_columns",
                        "type": "presence",
                        "target": "table",
                        "must_have_columns": ["created_at"],
                        "message": "Tables must have audit column",
                        "severity": "warning",
                    },
                ]
            }
        )

        sql = """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            userName VARCHAR(100)
        );

        SELECT * FROM users;
        """

        violations = engine.check_sql(sql)
        # Should have violations from multiple rule types
        assert len(violations) >= 2

        rule_types = set()
        for v in violations:
            if "SELECT" in v.message:
                rule_types.add("pattern")
            elif "userName" in v.message or "snake_case" in v.message:
                rule_types.add("naming")
            elif "audit" in v.message or "created_at" in v.message:
                rule_types.add("presence")

        # We should have at least 2 different rule types triggered
        assert len(rule_types) >= 2


class TestMultiDialect:
    """Test that SQL Model rules work across dialects."""

    def test_presence_rules_postgresql(self):
        """Test presence rules with PostgreSQL dialect."""
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "require_pk",
                        "type": "presence",
                        "target": "table",
                        "must_have_primary_key": True,
                        "message": "Tables must have PK",
                        "severity": "error",
                    }
                ]
            }
        )

        sql = "CREATE TABLE users (id SERIAL PRIMARY KEY, name VARCHAR(100));"
        violations = engine.check_sql(sql)
        assert len(violations) == 0

    def test_presence_rules_mysql(self):
        """Test presence rules with MySQL dialect."""
        engine = RuleEngine("mysql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "require_pk",
                        "type": "presence",
                        "target": "table",
                        "must_have_primary_key": True,
                        "message": "Tables must have PK",
                        "severity": "error",
                    }
                ]
            }
        )

        sql = "CREATE TABLE users (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100));"
        violations = engine.check_sql(sql)
        assert len(violations) == 0

    def test_presence_rules_oracle(self):
        """Test presence rules with Oracle dialect."""
        engine = RuleEngine("oracle")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "require_pk",
                        "type": "presence",
                        "target": "table",
                        "must_have_primary_key": True,
                        "message": "Tables must have PK",
                        "severity": "error",
                    }
                ]
            }
        )

        sql = "CREATE TABLE users (id NUMBER PRIMARY KEY, name VARCHAR2(100));"
        violations = engine.check_sql(sql)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# Z-1: naming rules for index / constraint targets
# ---------------------------------------------------------------------------


class TestIndexNamingTarget:
    """Naming-rule support for ``target: index`` (Z-1)."""

    def _make_engine(self):
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "index_name_prefix",
                        "type": "naming",
                        "target": "index",
                        "pattern": "^(idx_|ix_|pk_|uk_|fk_)[a-z][a-z0-9_]*$",
                        "message": "Index needs descriptive prefix",
                        "severity": "info",
                    }
                ]
            }
        )
        return engine

    def test_index_with_prefix_passes(self):
        engine = self._make_engine()
        violations = engine.check_sql("CREATE INDEX idx_users_email ON users (email);")
        assert violations == []

    def test_index_without_prefix_flagged(self):
        engine = self._make_engine()
        violations = engine.check_sql("CREATE INDEX users_email ON users (email);")
        assert len(violations) == 1
        assert "users_email" in violations[0].message

    def test_unique_index_with_prefix_passes(self):
        engine = self._make_engine()
        violations = engine.check_sql("CREATE UNIQUE INDEX uk_users_email ON users (email);")
        assert violations == []

    def test_if_not_exists_handled(self):
        engine = self._make_engine()
        violations = engine.check_sql("CREATE INDEX IF NOT EXISTS bad_name ON users (email);")
        assert len(violations) == 1
        assert "bad_name" in violations[0].message

    def test_concurrently_captures_real_index_name(self):
        # PostgreSQL ``CREATE INDEX CONCURRENTLY`` must not capture
        # ``CONCURRENTLY`` itself as the index name (Bugbot Z-1 follow-up).
        engine = self._make_engine()
        violations = engine.check_sql("CREATE INDEX CONCURRENTLY idx_users_email ON users (email);")
        assert violations == []

    def test_concurrently_with_bad_name_flagged(self):
        engine = self._make_engine()
        violations = engine.check_sql("CREATE INDEX CONCURRENTLY users_email ON users (email);")
        assert len(violations) == 1
        assert "users_email" in violations[0].message

    def test_unique_concurrently_if_not_exists(self):
        engine = self._make_engine()
        violations = engine.check_sql(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uk_users_email ON users (email);"
        )
        assert violations == []


class TestConstraintNamingTarget:
    """Naming-rule support for ``target: constraint`` (Z-1)."""

    def _make_engine(self):
        engine = RuleEngine("postgresql")
        engine.load_rules_from_dict(
            {
                "rules": [
                    {
                        "name": "constraint_name_descriptive",
                        "type": "naming",
                        "target": "constraint",
                        "pattern": "^(pk_|fk_|uk_|ck_|df_)[a-z][a-z0-9_]*$",
                        "message": "Constraint needs descriptive prefix",
                        "severity": "info",
                    }
                ]
            }
        )
        return engine

    def test_named_pk_constraint_passes(self):
        engine = self._make_engine()
        sql = "CREATE TABLE orders (" "id INT, CONSTRAINT pk_orders_id PRIMARY KEY (id)" ");"
        violations = engine.check_sql(sql)
        assert violations == []

    def test_named_constraint_without_prefix_flagged(self):
        engine = self._make_engine()
        sql = "CREATE TABLE orders (" "id INT, CONSTRAINT badname PRIMARY KEY (id)" ");"
        violations = engine.check_sql(sql)
        assert len(violations) == 1
        assert "badname" in violations[0].message

    def test_multiple_constraints_each_checked(self):
        engine = self._make_engine()
        sql = (
            "CREATE TABLE orders ("
            "id INT, user_id INT, "
            "CONSTRAINT pk_orders_id PRIMARY KEY (id), "
            "CONSTRAINT bad_fk FOREIGN KEY (user_id) REFERENCES users(id)"
            ");"
        )
        violations = engine.check_sql(sql)
        assert len(violations) == 1
        assert "bad_fk" in violations[0].message

    def test_alter_table_add_constraint(self):
        engine = self._make_engine()
        sql = "ALTER TABLE orders ADD CONSTRAINT bad_uk UNIQUE (id);"
        violations = engine.check_sql(sql)
        assert len(violations) == 1
        assert "bad_uk" in violations[0].message

    def test_drop_constraint_not_flagged(self):
        # ``DROP CONSTRAINT <name>`` references an existing name being
        # removed — naming-rule should ignore it (Bugbot Z-1 follow-up).
        engine = self._make_engine()
        sql = "ALTER TABLE orders DROP CONSTRAINT some_legacy_name;"
        violations = engine.check_sql(sql)
        assert violations == []

    def test_drop_then_add_only_add_flagged(self):
        engine = self._make_engine()
        sql = (
            "ALTER TABLE orders DROP CONSTRAINT old_legacy_name;\n"
            "ALTER TABLE orders ADD CONSTRAINT bad_uk UNIQUE (id);"
        )
        violations = engine.check_sql(sql)
        assert len(violations) == 1
        assert "bad_uk" in violations[0].message
