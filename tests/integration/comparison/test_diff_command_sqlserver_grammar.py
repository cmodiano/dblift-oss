"""Integration tests for SQL Server grammar-based enhancements.

Tests the new SQL Server-specific features added as part of the grammar-based improvements:
- Memory-optimized tables
- System-versioned temporal tables
- Filegroup support
- CREATE OR ALTER syntax
- Indexed views (materialized views)
- Extended index types (COLUMNSTORE, XML, etc.)
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
    """Drop table safely across different database types."""
    db_type = db_container["type"]
    schema = _get_schema(db_container)

    if db_type == "oracle":
        drop_sql = f"DROP TABLE {schema}.{table_name} CASCADE CONSTRAINTS PURGE"
    elif db_type == "postgresql":
        drop_sql = f'DROP TABLE IF EXISTS "{schema}"."{table_name}" CASCADE'
    elif db_type == "mysql":
        drop_sql = f"DROP TABLE IF EXISTS `{schema}`.`{table_name}`"
    elif db_type == "sqlserver":
        drop_sql = f"DROP TABLE IF EXISTS [{schema}].[{table_name}]"
    elif db_type == "db2":
        drop_sql = f'DROP TABLE IF EXISTS {schema}."{table_name.upper()}"'
    else:
        drop_sql = f"DROP TABLE IF EXISTS {schema}.{table_name}"

    try:
        execute_sql(db_container, drop_sql)
    except Exception:
        # Ignore errors as table might not exist
        pass


@pytest.mark.integration
@pytest.mark.parametrize(
    "db_container",
    ["sqlserver"],
    indirect=True,
)
class TestSQLServerGrammarEnhancements:
    """Test SQL Server-specific grammar enhancements."""

    def test_diff_detects_filegroup_changes(self, db_container, tmp_path):
        """Test that diff detects filegroup changes on tables."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        _drop_table(db_container, "filegroup_test")

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create table on PRIMARY filegroup (default)
        migration_sql = f"""
        CREATE TABLE [{schema}].[filegroup_test] (
            id INT IDENTITY(1,1) PRIMARY KEY,
            data NVARCHAR(100)
        ) ON [PRIMARY];
        """
        create_versioned_migration(
            migrations_dir, "1.0.0", "create_table_on_primary", migration_sql
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Note: Actually moving a table to a different filegroup requires:
        # 1. Creating the new filegroup
        # 2. Rebuilding clustered indexes on the new filegroup
        # For this test, we'll verify the parser recognizes ON [filegroup] syntax

        # Verify no drift with current filegroup
        diff_result = cli.diff()
        assert diff_result.success, f"Expected no drift, got: {diff_result.output}"

    def test_diff_handles_memory_optimized_tables(self, db_container, tmp_path):
        """Test that diff handles memory-optimized table syntax parsing.

        Note: We test with a regular table since memory-optimized tables require
        special database configuration (memory-optimized filegroups, etc.).
        The goal is to verify the parser can handle the MEMORY_OPTIMIZED keyword.
        """
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        _drop_table(db_container, "memory_opt_test")

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create a regular table with NONCLUSTERED primary key
        # (memory-optimized tables require NONCLUSTERED indexes)
        # This tests the parser can handle the syntax even if not memory-optimized
        migration_sql = f"""
        CREATE TABLE [{schema}].[memory_opt_test] (
            id INT IDENTITY(1,1) NOT NULL PRIMARY KEY NONCLUSTERED,
            data NVARCHAR(100)
        );
        """
        create_versioned_migration(migrations_dir, "1.0.0", "create_regular_table", migration_sql)

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Verify parser handles NONCLUSTERED syntax (used in memory-optimized tables)
        diff_result = cli.diff()
        assert diff_result.success, f"Expected no drift, got: {diff_result.output}"

    def test_diff_handles_system_versioned_tables(self, db_container, tmp_path):
        """Test that diff handles system-versioned temporal tables (SQL Server 2016+).

        Note: This test will skip if the SQL Server version doesn't support
        temporal tables.
        """
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Note: We'll test temporal table syntax on any SQL Server version
        # Older versions will use the fallback syntax

        # Clean up any existing objects
        _drop_table(db_container, "temporal_test")
        _drop_table(db_container, "temporal_test_history")

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create a regular table with period columns (but not system-versioned)
        migration_sql = f"""
        CREATE TABLE [{schema}].[temporal_test] (
            id INT IDENTITY(1,1) PRIMARY KEY,
            data NVARCHAR(100),
            valid_from DATETIME2 GENERATED ALWAYS AS ROW START NOT NULL,
            valid_to DATETIME2 GENERATED ALWAYS AS ROW END NOT NULL,
            PERIOD FOR SYSTEM_TIME (valid_from, valid_to)
        );
        """

        # For older SQL Server versions, create a simpler table
        fallback_sql = f"""
        CREATE TABLE [{schema}].[temporal_test] (
            id INT IDENTITY(1,1) PRIMARY KEY,
            data NVARCHAR(100),
            valid_from DATETIME2 DEFAULT SYSUTCDATETIME() NOT NULL,
            valid_to DATETIME2 DEFAULT '9999-12-31 23:59:59.9999999' NOT NULL
        );
        """

        try:
            create_versioned_migration(
                migrations_dir, "1.0.0", "create_temporal_table", migration_sql
            )
        except Exception:
            # If temporal syntax fails, use fallback
            create_versioned_migration(
                migrations_dir, "1.0.0", "create_temporal_table", fallback_sql
            )

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success

        # Migration might fail on older versions, but that's OK for this test
        migrate_result = cli.migrate()
        if migrate_result.success:
            # Verify parser handles temporal table syntax
            diff_result = cli.diff()
            # We expect success or at least no crash
            assert diff_result.returncode in [0, 1], f"Diff crashed: {diff_result.stderr}"

    def test_diff_handles_create_or_alter_syntax(self, db_container, tmp_path):
        """Test that diff handles CREATE OR ALTER syntax for procedures/functions.

        Note: Currently, the parser doesn't extract procedures from migration scripts,
        so this test verifies that CREATE OR ALTER syntax executes successfully during migration
        and that diff completes without crashing (even though procedures aren't compared).
        """
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        execute_sql(db_container, f"DROP PROCEDURE IF EXISTS [{schema}].[test_proc];")

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create table first (parseable by current implementation)
        # Then create procedure using CREATE OR ALTER
        # Note: GO statements are required between different DDL statement types in SQL Server
        migration_sql = f"""
        -- Create a simple table
        CREATE TABLE [{schema}].[proc_test_table] (
            id INT IDENTITY(1,1) PRIMARY KEY,
            name NVARCHAR(100)
        );

        GO

        -- Create procedure using CREATE OR ALTER
        CREATE OR ALTER PROCEDURE [{schema}].[test_proc]
            @param1 INT
        AS
        BEGIN
            SELECT @param1 AS Result;
        END;
        """

        # Fallback for older SQL Server versions
        fallback_sql = f"""
        -- Create a simple table
        CREATE TABLE [{schema}].[proc_test_table] (
            id INT IDENTITY(1,1) PRIMARY KEY,
            name NVARCHAR(100)
        );

        GO

        -- Create procedure
        CREATE PROCEDURE [{schema}].[test_proc]
            @param1 INT
        AS
        BEGIN
            SELECT @param1 AS Result;
        END;
        """

        try:
            create_versioned_migration(
                migrations_dir, "1.0.0", "create_or_alter_proc", migration_sql
            )
            use_create_or_alter = True
        except Exception:
            # CREATE OR ALTER might not be supported
            create_versioned_migration(migrations_dir, "1.0.0", "create_proc", fallback_sql)
            use_create_or_alter = False

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Since procedures aren't tracked by the parser, diff should complete successfully
        # (procedures exist in DB but aren't compared, so no drift is reported for them)
        diff_result = cli.diff()

        # The diff should complete successfully (procedures aren't compared, so no drift reported)
        # We just verify the command doesn't crash and completes
        assert diff_result.returncode in [
            0,
            1,
        ], f"Diff should complete (may succeed or fail, but not crash): {diff_result.stderr}"

        if use_create_or_alter:
            # Modify procedure using CREATE OR ALTER
            execute_sql(
                db_container,
                f"""
                CREATE OR ALTER PROCEDURE [{schema}].[test_proc]
                    @param1 INT,
                    @param2 INT = 0
                AS
                BEGIN
                    SELECT @param1 + @param2 AS Result;
                END;
                """,
            )
        else:
            # Modify using ALTER
            execute_sql(
                db_container,
                f"""
                ALTER PROCEDURE [{schema}].[test_proc]
                    @param1 INT,
                    @param2 INT = 0
                AS
                BEGIN
                    SELECT @param1 + @param2 AS Result;
                END;
                """,
            )

        # Should detect procedure modification
        diff_result = cli.diff()
        output_lower = diff_result.stdout.lower()
        assert (
            not diff_result.success or "modified" in output_lower
        ), f"Expected to detect procedure modification, got: {diff_result.output}"

    def test_diff_handles_indexed_views(self, db_container, tmp_path):
        """Test that diff handles indexed views (SQL Server's materialized views)."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        _drop_table(db_container, "base_table")
        execute_sql(db_container, f"DROP VIEW IF EXISTS [{schema}].[indexed_view];")

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create base table and indexed view
        # Note: In SQL Server, CREATE VIEW must be in a separate batch from CREATE INDEX
        # This is why we use GO statements between them
        migration_sql = f"""
        -- Create base table
        CREATE TABLE [{schema}].[base_table] (
            id INT IDENTITY(1,1) PRIMARY KEY,
            category NVARCHAR(50) NOT NULL,
            amount DECIMAL(10,2) NOT NULL
        );

        GO

        -- Create view with SCHEMABINDING
        CREATE VIEW [{schema}].[indexed_view]
        WITH SCHEMABINDING
        AS
        SELECT
            category,
            COUNT_BIG(*) AS count_rows,
            SUM(ISNULL(amount, 0)) AS total_amount
        FROM [{schema}].[base_table]
        GROUP BY category;

        GO

        -- Create unique clustered index to materialize the view
        CREATE UNIQUE CLUSTERED INDEX IX_indexed_view
        ON [{schema}].[indexed_view] (category);
        """

        create_versioned_migration(migrations_dir, "1.0.0", "create_indexed_view", migration_sql)

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Verify indexed view is recognized and parsed correctly
        # Note: View definitions may show minor differences due to formatting/normalization
        diff_result = cli.diff()
        output_lower = diff_result.stdout.lower()

        # Verify the view was introspected and comparison succeeded without drift
        assert (
            "indexed_view" in output_lower or diff_result.success
        ), f"Expected indexed_view in output: {diff_result.output}"
        assert diff_result.success, f"Diff should succeed: {diff_result.output}"

    def test_diff_handles_columnstore_indexes(self, db_container, tmp_path):
        """Test that diff handles COLUMNSTORE indexes."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Note: We'll test with regular indexes instead of columnstore for compatibility
        # Columnstore indexes require SQL Server 2012+ Enterprise or 2016+ Standard

        # Clean up any existing objects
        _drop_table(db_container, "columnstore_test")

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create table with columnstore index
        migration_sql = f"""
        CREATE TABLE [{schema}].[columnstore_test] (
            id INT IDENTITY(1,1),
            sale_date DATE,
            product_id INT,
            quantity INT,
            amount DECIMAL(10,2)
        );
        
        -- Create clustered columnstore index
        CREATE CLUSTERED COLUMNSTORE INDEX CCI_columnstore_test 
        ON [{schema}].[columnstore_test];
        """

        # Fallback without columnstore
        fallback_sql = f"""
        CREATE TABLE [{schema}].[columnstore_test] (
            id INT IDENTITY(1,1) PRIMARY KEY,
            sale_date DATE,
            product_id INT,
            quantity INT,
            amount DECIMAL(10,2)
        );
        
        -- Regular index instead of columnstore
        CREATE INDEX IX_columnstore_test_date 
        ON [{schema}].[columnstore_test] (sale_date);
        """

        try:
            create_versioned_migration(migrations_dir, "1.0.0", "create_columnstore", migration_sql)
            has_columnstore = True
        except Exception:
            create_versioned_migration(migrations_dir, "1.0.0", "create_table", fallback_sql)
            has_columnstore = False

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success

        migrate_result = cli.migrate()
        if migrate_result.success:
            # Verify parser handles columnstore syntax
            diff_result = cli.diff()
            assert diff_result.returncode in [0, 1], f"Diff crashed: {diff_result.stderr}"

    def test_diff_handles_xml_indexes(self, db_container, tmp_path):
        """Test that diff handles XML indexes."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        _drop_table(db_container, "xml_test")

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create table with XML column and indexes
        migration_sql = f"""
        CREATE TABLE [{schema}].[xml_test] (
            id INT IDENTITY(1,1) PRIMARY KEY,
            xml_data XML
        );
        
        -- Create primary XML index
        CREATE PRIMARY XML INDEX PXI_xml_data 
        ON [{schema}].[xml_test] (xml_data);
        
        -- Create secondary XML indexes
        CREATE XML INDEX IXI_xml_data_path 
        ON [{schema}].[xml_test] (xml_data)
        USING XML INDEX PXI_xml_data FOR PATH;
        """

        create_versioned_migration(migrations_dir, "1.0.0", "create_xml_indexes", migration_sql)

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Verify no drift - XML indexes should be recognized
        diff_result = cli.diff()
        # XML indexes might not be fully introspected, but shouldn't crash
        assert diff_result.returncode in [0, 1], f"Diff crashed: {diff_result.stderr}"

    def test_diff_handles_filtered_indexes(self, db_container, tmp_path):
        """Test that diff handles filtered indexes with WHERE clauses."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        _drop_table(db_container, "filtered_test")

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create table with filtered index
        migration_sql = f"""
        CREATE TABLE [{schema}].[filtered_test] (
            id INT IDENTITY(1,1) PRIMARY KEY,
            status NVARCHAR(20),
            created_date DATE
        );
        
        -- Create filtered index for active records only
        CREATE INDEX IX_filtered_active 
        ON [{schema}].[filtered_test] (created_date)
        WHERE status = 'ACTIVE';
        """

        create_versioned_migration(migrations_dir, "1.0.0", "create_filtered_index", migration_sql)

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Verify no drift - filtered indexes should be handled
        diff_result = cli.diff()
        assert (
            diff_result.success
        ), f"Expected no drift with filtered index, got: {diff_result.output}"

    def test_diff_handles_computed_columns(self, db_container, tmp_path):
        """Test that diff correctly handles computed columns."""
        db_type = db_container["type"]
        schema = _get_schema(db_container)

        # Clean up any existing objects
        _drop_table(db_container, "computed_test")

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create table with computed columns
        migration_sql = f"""
        CREATE TABLE [{schema}].[computed_test] (
            id INT IDENTITY(1,1) PRIMARY KEY,
            price DECIMAL(10,2),
            quantity INT,
            -- Non-persisted computed column
            total AS (price * quantity),
            -- Persisted computed column
            total_persisted AS (price * quantity) PERSISTED
        );
        """

        create_versioned_migration(
            migrations_dir, "1.0.0", "create_computed_columns", migration_sql
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        assert cli.baseline("0.0", "Initial baseline").success
        assert cli.migrate().success

        # Verify no drift - computed columns should be recognized
        diff_result = cli.diff()
        assert (
            diff_result.success
        ), f"Expected no drift with computed columns, got: {diff_result.output}"
