"""Integration tests for export-schema command.

Tests the export-schema command with real database connections and schema introspection.
"""

import subprocess

import pytest

from tests.integration.helpers.cli_runner import DBLiftCLI
from tests.integration.helpers.migration_helper import (
    create_config,
    create_versioned_migration,
    generate_test_sql,
)


def _replay_export_sql(db_container, sql_file):
    db_type = db_container["type"]
    sql_text = sql_file.read_text()

    if db_type == "postgresql":
        return subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "dblift_postgres",
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "postgres",
                "-d",
                db_container["database"],
                "-f",
                "/dev/stdin",
            ],
            input=sql_text,
            text=True,
            capture_output=True,
            check=False,
        )

    if db_type == "mysql":
        return subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "dblift_mysql",
                "mysql",
                "-uroot",
                "-proot",
                db_container["database"],
            ],
            input=sql_text,
            text=True,
            capture_output=True,
            check=False,
        )

    if db_type == "sqlserver":
        return subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "dblift_sqlserver",
                "/opt/mssql-tools18/bin/sqlcmd",
                "-b",
                "-C",
                "-S",
                "localhost",
                "-U",
                "sa",
                "-P",
                "YourStrong@Passw0rd",
                "-d",
                db_container["database"],
            ],
            input=":ON ERROR EXIT\n" + sql_text,
            text=True,
            capture_output=True,
            check=False,
        )

    if db_type == "oracle":
        return subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "dblift_oracle",
                "sqlplus",
                "-S",
                f"{db_container['username']}/{db_container['password']}@XEPDB1",
            ],
            input="WHENEVER SQLERROR EXIT SQL.SQLCODE\n" + sql_text + "\nEXIT\n",
            text=True,
            capture_output=True,
            check=False,
        )

    if db_type == "sqlite":
        return subprocess.run(
            ["sqlite3", db_container["path"]],
            input=sql_text,
            text=True,
            capture_output=True,
            check=False,
        )

    raise AssertionError(f"No SQL replay client configured for {db_type}")


def _export_replay_fixture_sql(db_type, schema):
    if db_type == "postgresql":
        return f"""
            CREATE TABLE "{schema}"."parent_probe" (
                id SERIAL PRIMARY KEY,
                note TEXT
            );

            CREATE VIEW "{schema}"."v_parent_probe" AS
            SELECT id, note FROM "{schema}"."parent_probe";

            CREATE OR REPLACE FUNCTION "{schema}".trg_probe_note()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$ BEGIN NEW.note := COALESCE(NEW.note, 'triggered'); RETURN NEW; END; $$;

            CREATE OR REPLACE PROCEDURE "{schema}".p_parent_probe_insert(p_note TEXT)
            LANGUAGE plpgsql
            AS $$ BEGIN INSERT INTO "{schema}"."parent_probe"(note) VALUES (p_note); END; $$;

            CREATE TRIGGER tr_child_probe_note
            BEFORE INSERT ON "{schema}"."parent_probe"
            FOR EACH ROW EXECUTE FUNCTION "{schema}".trg_probe_note();

            CREATE MATERIALIZED VIEW "{schema}"."mv_parent_probe" AS
            SELECT COUNT(*) AS cnt FROM "{schema}"."parent_probe";
        """

    if db_type == "mysql":
        return f"""
            CREATE TABLE `{schema}`.`parent_probe` (
                id INT NOT NULL PRIMARY KEY,
                parent_id INT,
                note TEXT
            );

            CREATE INDEX idx_child_probe_parent ON `{schema}`.`parent_probe` (parent_id);
            CREATE FULLTEXT INDEX ft_child_probe_note ON `{schema}`.`parent_probe` (note);

            CREATE VIEW `{schema}`.`v_parent_probe` AS
            SELECT id, note FROM `{schema}`.`parent_probe`;

            CREATE TRIGGER `{schema}`.`tr_parent_probe_note`
            BEFORE INSERT ON `{schema}`.`parent_probe`
            FOR EACH ROW
            SET NEW.note = COALESCE(NEW.note, 'triggered');

            DELIMITER $$
            CREATE PROCEDURE `{schema}`.`p_parent_probe_insert`(IN p_id INT, IN p_note TEXT)
            BEGIN
                INSERT INTO `{schema}`.`parent_probe` (id, note) VALUES (p_id, p_note);
            END$$
            DELIMITER ;
        """

    if db_type == "sqlserver":
        return f"""
            SET NUMERIC_ROUNDABORT OFF;
            SET ANSI_PADDING ON;
            SET ANSI_WARNINGS ON;
            SET CONCAT_NULL_YIELDS_NULL ON;
            SET ARITHABORT ON;
            SET QUOTED_IDENTIFIER ON;
            SET ANSI_NULLS ON;
            GO

            CREATE TABLE [{schema}].[sales_fact] (
                id INT NOT NULL PRIMARY KEY,
                customer_id INT NOT NULL,
                amount INT NOT NULL
            );
            GO

            CREATE VIEW [{schema}].[v_sales_plain]
            AS
            SELECT id, customer_id, amount
            FROM [{schema}].[sales_fact];
            GO

            CREATE VIEW [{schema}].[v_sales_total]
            WITH SCHEMABINDING
            AS
            SELECT
                customer_id,
                COUNT_BIG(*) AS row_count,
                SUM(ISNULL(amount, 0)) AS total_amount
            FROM [{schema}].[sales_fact]
            GROUP BY customer_id;
            GO

            CREATE UNIQUE CLUSTERED INDEX ix_v_sales_total
            ON [{schema}].[v_sales_total](customer_id);
            GO

            CREATE PROCEDURE [{schema}].[p_insert_sale]
                @id INT,
                @customer_id INT,
                @amount INT
            AS
            BEGIN
                INSERT INTO [{schema}].[sales_fact] (id, customer_id, amount)
                VALUES (@id, @customer_id, @amount);
            END;
            GO
        """

    if db_type == "oracle":
        return f"""
            CREATE TABLE "{schema}"."PARENT_PROBE" (
                id NUMBER NOT NULL PRIMARY KEY,
                note VARCHAR2(100)
            ) TABLESPACE USERS PCTFREE 10;

            CREATE OR REPLACE VIEW "{schema}"."V_PARENT_PROBE" AS
            SELECT id, note FROM "{schema}"."PARENT_PROBE";

            CREATE MATERIALIZED VIEW "{schema}"."MV_PARENT_PROBE" AS
            SELECT COUNT(*) AS cnt FROM "{schema}"."PARENT_PROBE";

            CREATE OR REPLACE PROCEDURE "{schema}"."P_TOUCH_NOTE" (p_id IN NUMBER) AS
            BEGIN
                UPDATE "{schema}"."PARENT_PROBE" SET note = 'procedure' WHERE id = p_id;
            END;
            /

            CREATE OR REPLACE PACKAGE "{schema}"."PKG_PARENT_PROBE" AS
                PROCEDURE TOUCH_NOTE(p_id IN NUMBER);
            END PKG_PARENT_PROBE;
            /

            CREATE OR REPLACE PACKAGE BODY "{schema}"."PKG_PARENT_PROBE" AS
                PROCEDURE TOUCH_NOTE(p_id IN NUMBER) AS
                BEGIN
                    UPDATE "{schema}"."PARENT_PROBE" SET note = 'package' WHERE id = p_id;
                END TOUCH_NOTE;
            END PKG_PARENT_PROBE;
            /
        """

    if db_type == "sqlite":
        return """
            CREATE TABLE parent_probe (
                id INTEGER PRIMARY KEY,
                note TEXT
            );
            CREATE VIRTUAL TABLE fts_probe USING fts5(note);
            CREATE INDEX idx_parent_probe_note ON parent_probe(note);
            CREATE VIEW v_parent_probe AS SELECT id, note FROM parent_probe;
            CREATE TRIGGER tr_parent_probe_note
            AFTER INSERT ON parent_probe
            WHEN NEW.note IS NULL
            BEGIN
                UPDATE parent_probe SET note = 'triggered' WHERE id = NEW.id;
            END;
        """

    raise AssertionError(f"No export replay fixture configured for {db_type}")


def _assert_export_replay_fixture_coverage(db_type, sql_text):
    upper = sql_text.upper()
    assert "CREATE TABLE" in upper

    if db_type == "postgresql":
        assert "V_PARENT_PROBE" in upper
        assert "CREATE OR REPLACE FUNCTION" in upper
        assert "CREATE OR REPLACE PROCEDURE" in upper
        assert "CREATE TRIGGER" in upper
        assert "CREATE MATERIALIZED VIEW" in upper
    elif db_type == "mysql":
        assert "V_PARENT_PROBE" in upper
        assert "P_PARENT_PROBE_INSERT" in upper
        assert " PROCEDURE " in upper
        assert "TR_PARENT_PROBE_NOTE" in upper
        assert " TRIGGER " in upper
        assert "FULLTEXT" in upper
    elif db_type == "sqlserver":
        assert "V_SALES_PLAIN" in upper
        assert "CREATE PROCEDURE" in upper
        assert "WITH SCHEMABINDING" in upper
        assert "CREATE UNIQUE CLUSTERED INDEX" in upper
    elif db_type == "oracle":
        assert "V_PARENT_PROBE" in upper
        assert "P_TOUCH_NOTE" in upper
        assert " PROCEDURE " in upper
        assert "PKG_PARENT_PROBE" in upper
        assert " PACKAGE" in upper
        assert "CREATE MATERIALIZED VIEW" in upper
    elif db_type == "sqlite":
        assert "V_PARENT_PROBE" in upper
        assert "CREATE TRIGGER" in upper
        assert "CREATE VIRTUAL TABLE" in upper


@pytest.mark.integration
@pytest.mark.parametrize(
    "db_container",
    ["postgresql", "mysql", "sqlserver", "oracle", "db2"],
    indirect=True,
)
class TestExportSchemaCommand:
    """Integration tests for export-schema command."""

    def test_export_schema_generated_sql_replays(self, db_container, tmp_path):
        """Exported SQL should replay through each backend's native client."""
        if db_container["type"] == "db2":
            pytest.skip("DB2 is not part of the release replay protocol")

        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)
        db_type = db_container["type"]
        schema = db_container.get("schema", "PUBLIC")

        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "export_replay",
            _export_replay_fixture_sql(db_type, schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        migrate_result = cli.migrate()
        assert migrate_result.success, f"Migration failed: {migrate_result.stderr}"

        no_drops_file = tmp_path / "export_replay_no_drops.sql"
        no_drops_export = cli.export_schema(
            output_file=no_drops_file,
            source="live-database",
        )
        assert no_drops_export.success, f"Export failed: {no_drops_export.stderr}"
        _assert_export_replay_fixture_coverage(db_type, no_drops_file.read_text())

        with_drops_file = tmp_path / "export_replay_with_drops.sql"
        with_drops_export = cli.export_schema(
            output_file=with_drops_file,
            source="live-database",
            include_drops=True,
        )
        assert with_drops_export.success, f"Export failed: {with_drops_export.stderr}"

        clean_result = cli.clean()
        assert clean_result.success, f"Clean failed before replay: {clean_result.stderr}"

        no_drops_replay = _replay_export_sql(db_container, no_drops_file)
        assert no_drops_replay.returncode == 0, no_drops_replay.stdout + no_drops_replay.stderr

        with_drops_replay = _replay_export_sql(db_container, with_drops_file)
        assert with_drops_replay.returncode == 0, (
            with_drops_replay.stdout + with_drops_replay.stderr
        )

    def test_export_schema_basic(self, db_container, tmp_path):
        """Test basic schema export to single file."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "PUBLIC")

        # Create a migration that creates tables
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "initial",
            generate_test_sql(db_type, "users", schema),
        )

        # Apply migration first
        cli = DBLiftCLI(config_file, migrations_dir)
        migrate_result = cli.migrate()
        assert migrate_result.success, f"Migration failed: {migrate_result.stderr}"

        # Export schema
        output_file = tmp_path / "exported_schema.sql"
        result = cli._run_command(
            "export-schema",
            output=str(output_file),
        )

        assert result.success, f"Export failed: {result.stderr}"
        assert output_file.exists(), "Output file was not created"

        # Verify content
        content = output_file.read_text()
        assert "CREATE TABLE" in content.upper() or "CREATE TABLE" in content
        assert "users" in content.lower() or "USERS" in content

    def test_export_schema_with_types_filter(self, db_container, tmp_path):
        """Test exporting only specific object types."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "PUBLIC")

        # Create migrations
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "initial",
            generate_test_sql(db_type, "users", schema),
        )

        # Apply migration
        cli = DBLiftCLI(config_file, migrations_dir)
        migrate_result = cli.migrate()
        assert migrate_result.success

        # Export only tables
        output_file = tmp_path / "tables_only.sql"
        result = cli._run_command(
            "export-schema",
            types="tables",
            output=str(output_file),
        )

        # Debug: print output if test fails
        if not result.success or not output_file.exists():
            print(f"Command stdout: {result.stdout}")
            print(f"Command stderr: {result.stderr}")
            print(f"Command: {' '.join(result.command)}")
            print(f"Return code: {result.returncode}")

        assert result.success, f"Command failed: {result.stderr}"
        assert (
            output_file.exists()
        ), f"Output file not created. Stdout: {result.stdout}, Stderr: {result.stderr}"

    def test_export_schema_split_by_type(self, db_container, tmp_path):
        """Test exporting with split-by-type option."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "PUBLIC")

        # Create migrations
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "initial",
            generate_test_sql(db_type, "users", schema),
        )

        # Apply migration
        cli = DBLiftCLI(config_file, migrations_dir)
        migrate_result = cli.migrate()
        assert migrate_result.success

        # Export split by type
        output_dir = tmp_path / "exported"
        output_dir.mkdir()

        result = cli._run_command(
            "export-schema",
            split_by_type=True,
            output_dir=str(output_dir),
        )

        assert result.success
        # Should create files like table.sql, view.sql, etc.
        files = list(output_dir.glob("*.sql"))
        assert len(files) > 0

    def test_export_schema_with_description(self, db_container, tmp_path):
        """Test exporting with custom description."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "PUBLIC")

        # Create and apply migration
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "initial",
            generate_test_sql(db_type, "users", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        cli.migrate()

        # Export with description
        output_file = tmp_path / "exported.sql"
        result = cli._run_command(
            "export-schema",
            output=str(output_file),
            description="Test schema export",
        )

        assert result.success
        content = output_file.read_text()
        assert "Test schema export" in content

    def test_export_schema_managed_only(self, db_container, tmp_path):
        """Test exporting only managed objects."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "PUBLIC")

        # Create and apply migration
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "initial",
            generate_test_sql(db_type, "users", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        migrate_result = cli.migrate()
        assert migrate_result.success

        # Export managed objects only
        output_file = tmp_path / "managed.sql"
        result = cli._run_command(
            "export-schema",
            managed_only=True,
            output=str(output_file),
        )

        assert result.success
        if output_file.exists():
            content = output_file.read_text()
            # Should contain the managed table
            assert "users" in content.lower() or "USERS" in content

    def test_export_schema_include_drops(self, db_container, tmp_path):
        """Test exporting with DROP statements included."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "PUBLIC")

        # Create and apply migration
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "initial",
            generate_test_sql(db_type, "users", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        cli.migrate()

        # Export with drops
        output_file = tmp_path / "with_drops.sql"
        result = cli._run_command(
            "export-schema",
            include_drops=True,
            output=str(output_file),
        )

        assert result.success
        content = output_file.read_text()
        # Should contain DROP statements
        assert "DROP" in content.upper()

    def test_export_schema_validation_errors(self, db_container, tmp_path):
        """Test validation errors."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        cli = DBLiftCLI(config_file, migrations_dir)

        # Test missing output
        result = cli._run_command("export-schema")
        assert not result.success or "required" in result.stderr.lower()

        # Test conflicting options
        output_file = tmp_path / "output.sql"
        result = cli._run_command(
            "export-schema",
            output=str(output_file),
            output_dir=str(tmp_path / "dir"),
        )
        assert not result.success or "both" in result.stderr.lower()

        # Test both managed flags
        result = cli._run_command(
            "export-schema",
            output=str(output_file),
            managed_only=True,
            unmanaged_only=True,
        )
        assert not result.success or "both" in result.stderr.lower()

    def test_export_schema_database_model_source(self, db_container, tmp_path):
        """Test export-schema with database-model source."""
        config_file = create_config(tmp_path, db_container)
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()

        db_type = db_container["type"]
        schema = db_container.get("schema", "PUBLIC")

        # Create and apply migration (this creates a snapshot)
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "initial",
            generate_test_sql(db_type, "users", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        migrate_result = cli.migrate()
        assert migrate_result.success

        # Export schema from database model
        output_file = tmp_path / "exported_from_model.sql"
        result = cli._run_command(
            "export-schema",
            output=str(output_file),
            source="database-model",
        )

        assert result.success, f"Export failed: {result.stderr}"
        assert output_file.exists(), "Output file was not created"

        # Verify content
        content = output_file.read_text()
        assert "CREATE TABLE" in content.upper() or "CREATE TABLE" in content

    def test_export_schema_file_model_source(self, db_container, tmp_path):
        """Test export-schema with file-model source."""
        config_file = create_config(tmp_path, db_container)
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()

        db_type = db_container["type"]
        schema = db_container.get("schema", "PUBLIC")

        # Create and apply migration
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "initial",
            generate_test_sql(db_type, "users", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        migrate_result = cli.migrate()
        assert migrate_result.success

        # First, export a snapshot to file
        snapshot_file = tmp_path / "snapshot.json"
        snapshot_result = cli._run_command(
            "snapshot",
            output=str(snapshot_file),
            source="database-stored",
        )
        assert snapshot_result.success, "Snapshot export failed"
        assert snapshot_file.exists(), "Snapshot file was not created"

        # Now export schema from the snapshot file
        output_file = tmp_path / "exported_from_file.sql"
        result = cli._run_command(
            "export-schema",
            output=str(output_file),
            source="file-model",
            snapshot_model=str(snapshot_file),
        )

        assert result.success, f"Export failed: {result.stderr}"
        assert output_file.exists(), "Output file was not created"

        # Verify content
        content = output_file.read_text()
        assert "CREATE TABLE" in content.upper() or "CREATE TABLE" in content

    def test_export_schema_file_model_missing_file(self, db_container, tmp_path):
        """Test export-schema with file-model source when file doesn't exist."""
        config_file = create_config(tmp_path, db_container)
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()

        cli = DBLiftCLI(config_file, migrations_dir)

        # Try to export from non-existent file
        output_file = tmp_path / "exported.sql"
        result = cli._run_command(
            "export-schema",
            output=str(output_file),
            source="file-model",
            snapshot_model=str(tmp_path / "nonexistent.json"),
        )

        assert (
            not result.success
            or "not found" in result.stderr.lower()
            or "file" in result.stderr.lower()
        )

    def test_export_schema_file_model_missing_snapshot_model(self, db_container, tmp_path):
        """Test export-schema with file-model source without snapshot-model."""
        config_file = create_config(tmp_path, db_container)
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()

        cli = DBLiftCLI(config_file, migrations_dir)

        # Try to export without snapshot-model
        output_file = tmp_path / "exported.sql"
        result = cli._run_command(
            "export-schema",
            output=str(output_file),
            source="file-model",
        )

        assert (
            not result.success
            or "snapshot-model is required" in result.stderr.lower()
            or "required" in result.stderr.lower()
        )


@pytest.mark.integration
def test_export_schema_generated_sql_replays_sqlite(tmp_path):
    """Exported SQLite SQL should replay through sqlite3."""
    db_path = tmp_path / "export_replay.sqlite"
    db_config = {"type": "sqlite", "path": str(db_path), "schema": "main"}
    migrations_dir = tmp_path / "sqlite_migrations"
    migrations_dir.mkdir()
    config_file = create_config(tmp_path, db_config, migrations_dir=migrations_dir)

    create_versioned_migration(
        migrations_dir,
        "1.0.0",
        "export_replay_sqlite",
        _export_replay_fixture_sql("sqlite", "main"),
    )

    cli = DBLiftCLI(config_file, migrations_dir)
    migrate_result = cli.migrate()
    assert migrate_result.success, f"Migration failed: {migrate_result.stderr}"

    no_drops_file = tmp_path / "sqlite_export_replay_no_drops.sql"
    no_drops_export = cli.export_schema(
        output_file=no_drops_file,
        source="live-database",
    )
    assert no_drops_export.success, f"Export failed: {no_drops_export.stderr}"
    _assert_export_replay_fixture_coverage("sqlite", no_drops_file.read_text())

    with_drops_file = tmp_path / "sqlite_export_replay_with_drops.sql"
    with_drops_export = cli.export_schema(
        output_file=with_drops_file,
        source="live-database",
        include_drops=True,
    )
    assert with_drops_export.success, f"Export failed: {with_drops_export.stderr}"

    db_path.unlink()

    no_drops_replay = _replay_export_sql(db_config, no_drops_file)
    assert no_drops_replay.returncode == 0, no_drops_replay.stdout + no_drops_replay.stderr

    with_drops_replay = _replay_export_sql(db_config, with_drops_file)
    assert with_drops_replay.returncode == 0, with_drops_replay.stdout + with_drops_replay.stderr


@pytest.mark.integration
@pytest.mark.parametrize(
    "db_container",
    ["sqlserver"],
    indirect=True,
)
class TestSQLServerExportSchemaIndexedViews:
    """SQL Server-specific export-schema regressions for indexed views."""

    def test_export_schema_indexed_view_is_replayable_batch_sql(self, db_container, tmp_path):
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)
        schema = db_container.get("schema", "TEST_SCHEMA")

        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "indexed_view",
            f"""
            SET ANSI_NULLS ON;
            SET QUOTED_IDENTIFIER ON;
            SET ANSI_PADDING ON;
            SET ANSI_WARNINGS ON;
            SET CONCAT_NULL_YIELDS_NULL ON;
            SET ARITHABORT ON;
            SET NUMERIC_ROUNDABORT OFF;
            GO

            CREATE TABLE {schema}.orders_export_indexed_view (
                order_id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                user_id INT NOT NULL,
                amount DECIMAL(10, 2) NOT NULL
            );
            GO

            CREATE VIEW {schema}.order_summary_export_indexed_view
            WITH SCHEMABINDING
            AS
            SELECT
                user_id,
                COUNT_BIG(*) AS cnt
            FROM {schema}.orders_export_indexed_view
            GROUP BY user_id;
            GO

            CREATE UNIQUE CLUSTERED INDEX idx_order_summary_export_indexed_view
            ON {schema}.order_summary_export_indexed_view (user_id);
            GO
            """,
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        migrate_result = cli.migrate()
        assert migrate_result.success, f"Migration failed: {migrate_result.stderr}"

        output_file = tmp_path / "sqlserver_indexed_view_export.sql"
        result = cli._run_command(
            "export-schema",
            output=str(output_file),
            source="live-database",
        )

        assert result.success, f"Export failed: {result.stderr}"
        content = output_file.read_text()
        upper = content.upper()

        assert "WITH SCHEMABINDING" in upper
        assert "CREATE UNIQUE CLUSTERED INDEX" in upper
        assert upper.count("CREATE UNIQUE CLUSTERED INDEX") == 1
        assert upper.count("CREATE VIEW") == 1

        view_index = upper.index("CREATE VIEW")
        clustered_index = upper.index("CREATE UNIQUE CLUSTERED INDEX")
        between_view_and_index = upper[view_index:clustered_index]
        assert "GO" in between_view_and_index
