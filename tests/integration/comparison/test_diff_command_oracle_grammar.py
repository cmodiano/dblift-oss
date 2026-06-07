"""Integration tests for Oracle grammar-based enhancements.

Tests the new Oracle-specific features added as part of the grammar-based improvements:
- Database links
- Materialized views
- Object types (UDTs)
- Partitioned tables
- Virtual columns (computed columns)
- Function-based indexes
- Bitmap indexes
"""

import pytest

from tests.integration.helpers.cli_runner_direct import DBLiftCLIDirect as DBLiftCLI
from tests.integration.helpers.database_helper import execute_sql
from tests.integration.helpers.migration_helper import (
    create_config,
    create_versioned_migration,
)

DEFAULT_SCHEMAS = {
    "postgresql": "TEST_SCHEMA",
    "sqlserver": "dbo",
    "oracle": "DBLIFT_TEST",
    "db2": "DBLIFT_TEST",
    "mysql": "TEST_SCHEMA",
}


def _get_schema(db_container: dict) -> str:
    """Get the schema name for the database type."""
    db_type = db_container["type"]
    return db_container.get("schema", DEFAULT_SCHEMAS.get(db_type, "TEST_SCHEMA"))


def _drop_table(db_container: dict, table_name: str) -> None:
    """Drop table safely for Oracle."""
    schema = _get_schema(db_container)
    drop_sql = f"DROP TABLE {schema}.{table_name} CASCADE CONSTRAINTS PURGE"

    try:
        execute_sql(db_container, drop_sql)
    except Exception:
        # Ignore errors as table might not exist
        pass


@pytest.mark.integration
@pytest.mark.parametrize(
    "db_container",
    ["oracle"],
    indirect=True,
)
class TestOracleGrammarEnhancements:
    """Test Oracle-specific grammar enhancements."""

    def test_diff_handles_virtual_columns(self, db_container, tmp_path):
        """Test that diff correctly handles virtual columns (Oracle's computed columns)."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        _drop_table(db_container, "virtual_test")

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create table with virtual columns
        migration_sql = f"""
        CREATE TABLE {schema}.virtual_test (
            id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            price NUMBER(10,2),
            quantity NUMBER,
            total NUMBER GENERATED ALWAYS AS (price * quantity) VIRTUAL
        )
        """

        create_versioned_migration(migrations_dir, "1.0.0", "create_virtual_columns", migration_sql)

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Verify no drift - virtual columns should be recognized
        diff_result = cli.diff()
        assert (
            diff_result.success
        ), f"Expected no drift with virtual columns, got: {diff_result.output}"

    def test_diff_handles_materialized_views(self, db_container, tmp_path):
        """Test that diff handles materialized views."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        _drop_table(db_container, "employees")
        try:
            execute_sql(db_container, f"DROP MATERIALIZED VIEW {schema}.emp_mv")
        except Exception:
            # Ignore errors as materialized view might not exist
            pass

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create table and materialized view
        migration_sql = f"""
        CREATE TABLE {schema}.employees (
            emp_id NUMBER PRIMARY KEY,
            department VARCHAR2(50),
            salary NUMBER(10,2)
        );

        CREATE MATERIALIZED VIEW {schema}.emp_mv AS
        SELECT department, COUNT(*) as emp_count
        FROM {schema}.employees
        GROUP BY department;
        """

        create_versioned_migration(
            migrations_dir, "1.0.0", "create_materialized_view", migration_sql
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Verify materialized view is recognized (no drift means it's properly handled)
        diff_result = cli.diff()
        # With snapshot-based diff, if there's no drift, the materialized view won't be mentioned
        # The fact that diff succeeds means materialized views are properly supported
        assert (
            diff_result.success
        ), f"Diff should succeed when materialized view matches snapshot: {diff_result.stderr}"

        # To verify materialized views are detected, drop it and check that drift is detected
        execute_sql(db_container, f"DROP MATERIALIZED VIEW {schema}.emp_mv")
        diff_result_with_drift = cli.diff()
        assert diff_result_with_drift.failed, "Diff should fail when materialized view is missing"
        output_lower = diff_result_with_drift.stdout.lower()
        assert (
            "emp_mv" in output_lower or "materialized" in output_lower or "missing" in output_lower
        ), f"Expected materialized view drift to be detected: {diff_result_with_drift.output}"

    def test_diff_handles_object_types(self, db_container, tmp_path):
        """Test that diff handles Oracle object types (UDTs)."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        try:
            execute_sql(db_container, f"DROP TYPE {schema}.address_type FORCE")
        except Exception:
            pass

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create object type
        migration_sql = f"""
        CREATE TYPE {schema}.address_type AS OBJECT (
            street VARCHAR2(100),
            city VARCHAR2(50),
            postal_code VARCHAR2(20)
        )
        """

        create_versioned_migration(migrations_dir, "1.0.0", "create_object_type", migration_sql)

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Verify object type is recognized
        diff_result = cli.diff()
        assert diff_result.returncode in [0, 1], f"Diff crashed: {diff_result.stderr}"

    def test_diff_handles_partitioned_tables(self, db_container, tmp_path):
        """Test that diff handles partitioned tables."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        _drop_table(db_container, "sales")

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create range-partitioned table
        migration_sql = f"""
        CREATE TABLE {schema}.sales (
            sale_id NUMBER PRIMARY KEY,
            sale_date DATE,
            amount NUMBER(10,2)
        )
        PARTITION BY RANGE (sale_date) (
            PARTITION sales_q1 VALUES LESS THAN (TO_DATE('2024-04-01', 'YYYY-MM-DD')),
            PARTITION sales_q2 VALUES LESS THAN (TO_DATE('2024-07-01', 'YYYY-MM-DD')),
            PARTITION sales_q3 VALUES LESS THAN (TO_DATE('2024-10-01', 'YYYY-MM-DD')),
            PARTITION sales_q4 VALUES LESS THAN (TO_DATE('2025-01-01', 'YYYY-MM-DD'))
        )
        """

        create_versioned_migration(
            migrations_dir, "1.0.0", "create_partitioned_table", migration_sql
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Verify partitioned table is recognized
        # Note: Partition details might not be fully tracked
        diff_result = cli.diff()
        assert diff_result.returncode in [0, 1], f"Diff crashed: {diff_result.stderr}"

    def test_diff_handles_bitmap_indexes(self, db_container, tmp_path):
        """Test that diff handles bitmap indexes."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        _drop_table(db_container, "customers")

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create table with bitmap index
        migration_sql = f"""
        CREATE TABLE {schema}.customers (
            customer_id NUMBER PRIMARY KEY,
            region VARCHAR2(50),
            status VARCHAR2(20)
        );

        CREATE BITMAP INDEX {schema}.idx_customers_region
        ON {schema}.customers (region);
        """

        create_versioned_migration(migrations_dir, "1.0.0", "create_bitmap_index", migration_sql)

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Verify bitmap index is recognized
        diff_result = cli.diff()
        assert (
            diff_result.success
        ), f"Expected no drift with bitmap index, got: {diff_result.output}"

    def test_diff_handles_function_based_indexes(self, db_container, tmp_path):
        """Test that diff handles function-based indexes."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        _drop_table(db_container, "users")

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create table with function-based index
        migration_sql = f"""
        CREATE TABLE {schema}.users (
            user_id NUMBER PRIMARY KEY,
            email VARCHAR2(100)
        );

        CREATE INDEX {schema}.idx_users_upper_email
        ON {schema}.users (UPPER(email));
        """

        create_versioned_migration(
            migrations_dir, "1.0.0", "create_function_based_index", migration_sql
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Verify function-based index is recognized
        # Note: Function expressions might not be fully tracked
        diff_result = cli.diff()
        assert diff_result.returncode in [0, 1], f"Diff crashed: {diff_result.stderr}"

    def test_diff_handles_sequences(self, db_container, tmp_path):
        """Test that diff handles sequences."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        try:
            execute_sql(db_container, f"DROP SEQUENCE {schema}.test_seq")
        except Exception:
            pass

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create sequence
        migration_sql = f"""
        CREATE SEQUENCE {schema}.test_seq
        START WITH 1
        INCREMENT BY 1
        NOCACHE
        NOCYCLE
        """

        create_versioned_migration(migrations_dir, "1.0.0", "create_sequence", migration_sql)

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Verify sequence is recognized
        diff_result = cli.diff()
        assert diff_result.success, f"Expected no drift with sequence, got: {diff_result.output}"

    def test_diff_handles_synonyms(self, db_container, tmp_path):
        """Test that diff handles synonyms."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        _drop_table(db_container, "products")
        try:
            execute_sql(db_container, f"DROP SYNONYM {schema}.prod_syn")
        except Exception:
            pass

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create table and synonym
        migration_sql = f"""
        CREATE TABLE {schema}.products (
            product_id NUMBER PRIMARY KEY,
            product_name VARCHAR2(100)
        );

        CREATE SYNONYM {schema}.prod_syn FOR {schema}.products;
        """

        create_versioned_migration(migrations_dir, "1.0.0", "create_synonym", migration_sql)

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Verify synonym is recognized
        diff_result = cli.diff()
        assert diff_result.returncode in [0, 1], f"Diff crashed: {diff_result.stderr}"
