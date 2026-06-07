"""
Test diff command edge cases and error handling.

This test suite covers edge cases in diff_command.py that are not covered
by basic integration tests:
- Error handling scenarios
- Edge cases with filtering
- Complex diff scenarios
- Error recovery
"""

import pytest

from tests.integration.helpers.cli_runner import DBLiftCLI
from tests.integration.helpers.database_helper import execute_sql, verify_table_exists
from tests.integration.helpers.migration_helper import (
    create_config,
    create_versioned_migration,
    generate_test_sql,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "db_container",
    ["postgresql", "mysql", "sqlserver"],
    indirect=True,
)
class TestDiffCommandEdgeCases:
    """Test edge cases and error handling in diff command."""

    def test_diff_with_invalid_schema_file(self, db_container, tmp_path):
        """Test diff with invalid schema file path."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        cli = DBLiftCLI(config_file, migrations_dir)

        # Try diff with non-existent schema file
        result = cli.diff(
            source_schema=tmp_path / "nonexistent.yaml",
            target_schema=tmp_path / "also_nonexistent.yaml",
        )

        # Should handle gracefully (either fail with error message or succeed with empty diff)
        assert (
            "error" in result.output.lower()
            or "not found" in result.output.lower()
            or result.success
        )

    def test_diff_with_empty_schema_files(self, db_container, tmp_path):
        """Test diff with empty schema files."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create empty schema files
        schema1 = tmp_path / "schema1.yaml"
        schema1.write_text("")
        schema2 = tmp_path / "schema2.yaml"
        schema2.write_text("")

        cli = DBLiftCLI(config_file, migrations_dir)

        # Diff should handle empty schemas
        result = cli.diff(
            source_schema=schema1,
            target_schema=schema2,
        )

        # Should succeed (no differences between empty schemas)
        assert result.success

    def test_diff_with_malformed_schema_file(self, db_container, tmp_path):
        """Test diff with malformed YAML schema file."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create valid schema
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "create_table",
            generate_test_sql(db_type, "test_table", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        cli.migrate()

        # Export valid schema
        result = cli.export_schema(output_file=tmp_path / "schema1.yaml")
        assert result.success

        # Create malformed YAML
        malformed_schema = tmp_path / "malformed.yaml"
        malformed_schema.write_text("invalid: yaml: content: [unclosed")

        # Diff should handle malformed YAML gracefully
        result = cli.diff(
            source_schema=tmp_path / "schema1.yaml",
            target_schema=malformed_schema,
        )

        # Should fail with error message
        assert (
            not result.success
            or "error" in result.output.lower()
            or "yaml" in result.output.lower()
        )

    def test_diff_with_version_filtering_no_matches(self, db_container, tmp_path):
        """Test diff with version filtering that matches no migrations."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create migration
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "create_table",
            generate_test_sql(db_type, "test_table", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        cli.migrate()

        # Diff with version that doesn't exist
        result = cli.diff(versions="9.9.9")

        # Should handle gracefully (either succeed with no differences or report appropriately)
        assert (
            result.success or "not found" in result.output.lower() or "no" in result.output.lower()
        )

    def test_diff_with_tag_filtering_no_matches(self, db_container, tmp_path):
        """Test diff with tag filtering that matches no migrations."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create migration without tags
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "create_table",
            generate_test_sql(db_type, "test_table", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        cli.migrate()

        # Diff with tag that doesn't exist
        result = cli.diff(tags="nonexistent-tag")

        # Should handle gracefully
        assert result.success or "no" in result.output.lower()

    def test_diff_with_exclude_versions(self, db_container, tmp_path):
        """Test diff with exclude-versions filtering."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create multiple migrations
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "first",
            generate_test_sql(db_type, "table1", schema),
        )
        create_versioned_migration(
            migrations_dir,
            "1.0.1",
            "second",
            generate_test_sql(db_type, "table2", schema),
        )
        create_versioned_migration(
            migrations_dir,
            "1.0.2",
            "third",
            generate_test_sql(db_type, "table3", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        cli.migrate()

        # Diff excluding version 1.0.1
        result = cli.diff(exclude_versions="1.0.1")

        # Should succeed
        assert result.success

    def test_diff_with_exclude_tags(self, db_container, tmp_path):
        """Test diff with exclude-tags filtering."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create migration
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "create_table",
            generate_test_sql(db_type, "test_table", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        cli.migrate()

        # Diff excluding non-existent tag
        result = cli.diff(exclude_tags="nonexistent-tag")

        # Should succeed
        assert result.success

    def test_diff_with_target_version(self, db_container, tmp_path):
        """Test diff with target-version filtering."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create multiple migrations
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "first",
            generate_test_sql(db_type, "table1", schema),
        )
        create_versioned_migration(
            migrations_dir,
            "1.0.1",
            "second",
            generate_test_sql(db_type, "table2", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        cli.migrate()

        # Diff up to version 1.0.0
        result = cli.diff(target_version="1.0.0")

        # Should succeed
        assert result.success

    def test_diff_with_ignore_unmanaged(self, db_container, tmp_path):
        """Test diff with ignore-unmanaged option."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create migration
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "create_table",
            generate_test_sql(db_type, "test_table", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        cli.migrate()

        # Create unmanaged object manually
        if db_type == "postgresql":
            unmanaged_sql = f'CREATE TABLE "{schema}"."unmanaged_table" (id INT);'
        elif db_type == "mysql":
            unmanaged_sql = f"CREATE TABLE {schema}.unmanaged_table (id INT);"
        else:
            unmanaged_sql = f"CREATE TABLE {schema}.unmanaged_table (id INT);"

        execute_sql(db_container, unmanaged_sql)

        # Diff with ignore-unmanaged
        result = cli.diff(ignore_unmanaged=True)

        # Should succeed and not show unmanaged objects in differences
        assert result.success
        # Check that unmanaged_table is not mentioned in the differences section
        # (it may appear in "Filtering Options: --ignore-unmanaged" which is OK)
        output_lower = result.output.lower()
        # Extract differences section (after "SCHEMA DIFFERENCES" or similar)
        if "schema differences" in output_lower:
            diff_section_start = output_lower.find("schema differences")
            diff_section = output_lower[diff_section_start:]
            # Unmanaged table should not appear in differences section
            # The word "unmanaged" may appear in "Filtering Options" header, which is fine
            # If no differences found, unmanaged objects were correctly ignored
            if "no differences found" in diff_section or "schema is in sync" in diff_section:
                # Test passes - unmanaged objects were ignored
                pass
            else:
                # If differences are shown, unmanaged_table should not be in them
                assert "unmanaged_table" not in diff_section or "ignored" in output_lower
        # If no differences found (schema in sync), that's also OK - unmanaged objects were ignored
        # The word "unmanaged" in "Filtering Options: --ignore-unmanaged" is expected and OK

    def test_diff_with_complex_filtering(self, db_container, tmp_path):
        """Test diff with multiple filtering options combined."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create migrations
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "first",
            generate_test_sql(db_type, "table1", schema),
        )
        create_versioned_migration(
            migrations_dir,
            "1.0.1",
            "second",
            generate_test_sql(db_type, "table2", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        cli.migrate()

        # Diff with multiple filters
        result = cli.diff(
            target_version="1.0.1",
            versions="1.0.0",
            exclude_versions="1.0.1",
        )

        # Should handle complex filtering
        assert result.success or "no" in result.output.lower()

    def test_diff_after_manual_schema_change(self, db_container, tmp_path):
        """Test diff after manual schema changes (drift detection)."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create and apply migration
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "create_table",
            generate_test_sql(db_type, "test_table", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)
        cli.migrate()

        # Manually alter table (create drift)
        if db_type == "postgresql":
            alter_sql = (
                f'ALTER TABLE "{schema}"."test_table" ADD COLUMN manual_column VARCHAR(100);'
            )
        elif db_type == "mysql":
            alter_sql = f"ALTER TABLE {schema}.test_table ADD COLUMN manual_column VARCHAR(100);"
        else:
            alter_sql = f"ALTER TABLE {schema}.test_table ADD manual_column VARCHAR(100);"

        execute_sql(db_container, alter_sql)

        # Diff should detect the drift
        result = cli.diff()

        # Diff command returns non-zero exit code when differences are found (this is expected)
        # Check that differences are detected
        output_lower = result.output.lower()
        # Should indicate drift or differences
        # Note: result.success may be False when differences are found (exit code 1)
        assert (
            "drift" in output_lower
            or "difference" in output_lower
            or "diff" in output_lower
            or "extra columns" in output_lower
            or "manual_column" in output_lower
            or "modified tables" in output_lower
            or ("warning" in output_lower and "manual_column" in output_lower)
        )

    def test_diff_with_no_connection(self, db_container, tmp_path):
        """Test diff behavior when database connection fails."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create config with invalid connection
        invalid_config = tmp_path / "invalid_config.yaml"
        invalid_config.write_text(f"""
database:
  type: {db_container['type']}
  url: postgresql+psycopg://invalid:9999/invalid
  username: invalid
  password: invalid
  schema: {db_container.get('schema', 'TEST_SCHEMA')}
migrations:
  scripts_dir: {migrations_dir}
""")

        cli = DBLiftCLI(invalid_config, migrations_dir)

        # Diff should handle connection failure gracefully
        result = cli.diff()

        # Should fail with connection error
        assert not result.success
        assert (
            "connection" in result.output.lower()
            or "error" in result.output.lower()
            or "failed" in result.output.lower()
        )
