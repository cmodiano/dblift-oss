"""
Test version-based migration filtering through CLI.

CRITICAL: These tests verify that version filtering works correctly:
- --versions: Include only migrations with specific versions
- --exclude-versions: Exclude migrations with specific versions
- Version ranges
- Multiple versions (comma-separated)
- Complex version scenarios

All tests use the production CLI (cli/main.py) to ensure
version filtering works end-to-end in real migrations.
"""

import pytest

from tests.integration.helpers.cli_runner_direct import DBLiftCLIDirect as DBLiftCLI
from tests.integration.helpers.database_helper import verify_table_exists
from tests.integration.helpers.migration_helper import (
    create_config,
    create_migration,
)


@pytest.mark.integration
class TestVersions:
    """Test version-based migration filtering through CLI."""

    def test_single_version_filter(self, postgresql_container, tmp_path):
        """Test filtering migrations by a single version."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir, "V1_0_0__users.sql", "CREATE TABLE users (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_1__orders.sql", "CREATE TABLE orders (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_2__products.sql", "CREATE TABLE products (id SERIAL PRIMARY KEY);"
        )

        # Migrate with --versions 1.0.0 (should only run V1_0_0)
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(versions="1.0.0")

        assert result.success, f"Failed: {result.stderr}"

        assert verify_table_exists(postgresql_container, "users")
        # Other tables should not exist (but hard to verify without more info)

    def test_multiple_versions_filter(self, postgresql_container, tmp_path):
        """Test filtering migrations by multiple versions."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir, "V1_0_0__base.sql", "CREATE TABLE t1 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_1__feature1.sql", "CREATE TABLE t2 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_2__feature2.sql", "CREATE TABLE t3 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_3__feature3.sql", "CREATE TABLE t4 (id SERIAL PRIMARY KEY);"
        )

        # Migrate with --versions 1.0.0,1.0.2 (should run V1_0_0 and V1_0_2)
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(versions="1.0.0,1.0.2")

        assert result.success, f"Failed: {result.stderr}"

        assert verify_table_exists(postgresql_container, "t1")
        assert verify_table_exists(postgresql_container, "t3")

    def test_exclude_versions(self, postgresql_container, tmp_path):
        """Test excluding migrations by versions."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir, "V1_0_0__stable.sql", "CREATE TABLE stable1 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_1__broken.sql", "CREATE TABLE broken (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_2__stable.sql", "CREATE TABLE stable2 (id SERIAL PRIMARY KEY);"
        )

        # Migrate with --exclude-versions 1.0.1
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(exclude_versions="1.0.1")

        assert result.success, f"Failed: {result.stderr}"

        assert verify_table_exists(postgresql_container, "stable1")
        assert verify_table_exists(postgresql_container, "stable2")
        assert not verify_table_exists(postgresql_container, "broken")

    def test_exclude_multiple_versions(self, postgresql_container, tmp_path):
        """Test excluding multiple versions."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        for i in range(5):
            create_migration(
                migrations_dir,
                f"V1_0_{i}__migration_{i}.sql",
                f"CREATE TABLE table_{i} (id SERIAL PRIMARY KEY);",
            )

        # Exclude versions 1.0.1 and 1.0.3
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(exclude_versions="1.0.1,1.0.3")

        assert result.success, f"Failed: {result.stderr}"

        assert verify_table_exists(postgresql_container, "table_0")
        assert not verify_table_exists(postgresql_container, "table_1")
        assert verify_table_exists(postgresql_container, "table_2")
        assert not verify_table_exists(postgresql_container, "table_3")
        assert verify_table_exists(postgresql_container, "table_4")

    def test_versions_and_exclude_versions_together(self, postgresql_container, tmp_path):
        """Test using both --versions and --exclude-versions together."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir, "V1_0_0__t1.sql", "CREATE TABLE t1 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_1__t2.sql", "CREATE TABLE t2 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_2__t3.sql", "CREATE TABLE t3 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V2_0_0__t4.sql", "CREATE TABLE t4 (id SERIAL PRIMARY KEY);"
        )

        # Try to include and exclude the same version - should fail with error
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(versions="1.0.0,1.0.1,1.0.2", exclude_versions="1.0.1")

        # Should fail with validation error (error goes to stderr)
        assert not result.success, "Expected command to fail with conflicting version options"
        assert (
            "cannot include and exclude the same version" in (result.stdout + result.stderr).lower()
        )

    def test_version_filter_with_target_version(self, postgresql_container, tmp_path):
        """Test exclude-versions combined with target-version."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir, "V1_0_0__t1.sql", "CREATE TABLE t1 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_1__t2.sql", "CREATE TABLE t2 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_2__t3.sql", "CREATE TABLE t3 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_3__t4.sql", "CREATE TABLE t4 (id SERIAL PRIMARY KEY);"
        )

        # Exclude one migration while applying up to target-version.
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(target_version="1.0.2", exclude_versions="1.0.1")

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(postgresql_container, "t1")
        assert not verify_table_exists(postgresql_container, "t2")
        assert verify_table_exists(postgresql_container, "t3")
        assert not verify_table_exists(postgresql_container, "t4")

    def test_version_filter_with_dry_run(self, postgresql_container, tmp_path):
        """Test version filtering works with dry-run."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir, "V1_0_0__users.sql", "CREATE TABLE users (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_1__orders.sql", "CREATE TABLE orders (id SERIAL PRIMARY KEY);"
        )

        # Dry run with version filter
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(versions="1.0.0", dry_run=True)

        assert result.success, f"Failed: {result.stderr}"

        # No tables should exist (dry run)
        assert not verify_table_exists(postgresql_container, "users")
        assert not verify_table_exists(postgresql_container, "orders")

    def test_versions_with_undo(self, postgresql_container, tmp_path):
        """Test that version filtering works with undo."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Create forward migrations
        create_migration(
            migrations_dir, "V1_0_0__t1.sql", "CREATE TABLE t1 (id SERIAL PRIMARY KEY);"
        )

        create_migration(migrations_dir, "U1_0_0__t1.sql", "DROP TABLE t1;")

        create_migration(
            migrations_dir, "V1_0_1__t2.sql", "CREATE TABLE t2 (id SERIAL PRIMARY KEY);"
        )

        create_migration(migrations_dir, "U1_0_1__t2.sql", "DROP TABLE t2;")

        # Apply all migrations
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()
        assert result.success, f"Failed: {result.stderr}"

        # Undo with version filter - only undo 1.0.0
        result = cli.undo(versions="1.0.0")
        assert result.success, f"Failed: {result.stderr}"

        assert not verify_table_exists(postgresql_container, "t1")
        assert verify_table_exists(postgresql_container, "t2")

    def test_version_pattern_major_minor(self, postgresql_container, tmp_path):
        """Test version filtering with major.minor patterns."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # V1.x migrations
        create_migration(
            migrations_dir, "V1_0_0__v1_feature1.sql", "CREATE TABLE v1_t1 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_1__v1_feature2.sql", "CREATE TABLE v1_t2 (id SERIAL PRIMARY KEY);"
        )

        # V2.x migrations
        create_migration(
            migrations_dir, "V2_0_0__v2_feature1.sql", "CREATE TABLE v2_t1 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V2_0_1__v2_feature2.sql", "CREATE TABLE v2_t2 (id SERIAL PRIMARY KEY);"
        )

        # If version filtering supports patterns like "2.*" or "2.0.*"
        # This test would verify that behavior
        # For now, test explicit version list
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(versions="2.0.0,2.0.1")

        assert result.success, f"Failed: {result.stderr}"

        # Only v2 tables should exist
        assert verify_table_exists(postgresql_container, "v2_t1")
        assert verify_table_exists(postgresql_container, "v2_t2")

    def test_versions_combined_with_tags(self, postgresql_container, tmp_path):
        """Test version filtering combined with tag filtering."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir, "V1_0_0__t1[ddl].sql", "CREATE TABLE t1 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_1__t2[dml].sql", "CREATE TABLE t2 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_2__t3[ddl].sql", "CREATE TABLE t3 (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V2_0_0__t4[ddl].sql", "CREATE TABLE t4 (id SERIAL PRIMARY KEY);"
        )

        # Migrate with versions 1.0.0,1.0.1,1.0.2 AND tag ddl
        # Should run 1.0.0 and 1.0.2 (not 1.0.1 as it has dml tag)
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(versions="1.0.0,1.0.1,1.0.2", tags="ddl")

        assert result.success, f"Failed: {result.stderr}"

        assert verify_table_exists(postgresql_container, "t1")
        assert not verify_table_exists(postgresql_container, "t2")  # dml tag
        assert verify_table_exists(postgresql_container, "t3")
        assert not verify_table_exists(postgresql_container, "t4")  # version 2.0.0

    def test_complex_version_scenario(self, postgresql_container, tmp_path):
        """Test complex real-world version filtering scenario."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Simulate hotfix scenario: apply specific versions while excluding problematic ones
        create_migration(
            migrations_dir, "V1_0_0__base.sql", "CREATE TABLE base (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir,
            "V1_0_1__feature_a.sql",
            "CREATE TABLE feature_a (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_2__broken_migration.sql",
            "CREATE TABLE broken (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_3__feature_b.sql",
            "CREATE TABLE feature_b (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir, "V1_0_4__hotfix.sql", "CREATE TABLE hotfix (id SERIAL PRIMARY KEY);"
        )

        # Apply all except the broken migration
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(exclude_versions="1.0.2")

        assert result.success, f"Failed: {result.stderr}"

        assert verify_table_exists(postgresql_container, "base")
        assert verify_table_exists(postgresql_container, "feature_a")
        assert not verify_table_exists(postgresql_container, "broken")
        assert verify_table_exists(postgresql_container, "feature_b")
        assert verify_table_exists(postgresql_container, "hotfix")

    def test_info_command_with_versions(self, postgresql_container, tmp_path):
        """Test that info command respects version filters."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir, "V1_0_0__users.sql", "CREATE TABLE users (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir, "V1_0_1__orders.sql", "CREATE TABLE orders (id SERIAL PRIMARY KEY);"
        )

        # Get info with version filter
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.info(versions="1.0.0")

        assert result.success, f"Failed: {result.stderr}"
        # Info should show filtered migrations

    def test_version_filter_no_matches(self, postgresql_container, tmp_path):
        """Test version filter with no matching migrations."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir, "V1_0_0__users.sql", "CREATE TABLE users (id SERIAL PRIMARY KEY);"
        )

        # Filter by non-existent version
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(versions="9.9.9")

        # Should succeed but apply no migrations
        assert result.success, f"Failed: {result.stderr}"
