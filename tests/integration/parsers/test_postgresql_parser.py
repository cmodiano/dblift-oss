"""
Test PostgreSQL SQL parsing through CLI.

CRITICAL: These tests verify that the PostgreSQL parser correctly handles
complex PL/pgSQL scripts including:
- Dollar-quoted string literals
- Nested functions and procedures
- Complex control flow
- String literals with special characters
- Comments and unusual formatting

All tests use the production CLI (cli/main.py) to ensure
parsing works end-to-end in real migrations.
"""

import pytest

from tests.integration.helpers.cli_runner import DBLiftCLI
from tests.integration.helpers.database_helper import verify_table_exists
from tests.integration.helpers.migration_helper import (
    create_config,
    create_migration,
)


@pytest.mark.integration
class TestPostgreSQLParser:
    """Test PostgreSQL PL/pgSQL parsing through CLI."""

    def test_dollar_quoting_basic(self, postgresql_container, tmp_path):
        """Test dollar-quoted string literals."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE code_samples (
            id SERIAL PRIMARY KEY,
            code TEXT
        );

        -- Dollar quoting with SQL inside
        INSERT INTO code_samples (code) VALUES ($$
            SELECT * FROM users;
            DELETE FROM logs;
        $$);

        -- Dollar quoting with semicolons
        INSERT INTO code_samples (code) VALUES ($$
            This text has semicolons; but they shouldn't split statements;
        $$);

        -- Verify data inserted
        SELECT COUNT(*) FROM code_samples;
        """

        create_migration(migrations_dir, "V1_0_0__dollar_quotes.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Migration failed: {result.stderr}"
        assert "V1_0_0__dollar_quotes.sql" in result.output

    def test_dollar_quoting_named(self, postgresql_container, tmp_path):
        """Test named dollar quotes."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE functions (
            id SERIAL PRIMARY KEY,
            func_body TEXT
        );

        -- Named dollar quotes
        INSERT INTO functions (func_body) VALUES ($func$
            CREATE FUNCTION test() RETURNS void AS $body$
            BEGIN
                -- nested dollar quote
                NULL;
            END;
            $body$ LANGUAGE plpgsql;
        $func$);
        """

        create_migration(migrations_dir, "V1_0_0__named_dollar.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_plpgsql_function_complex(self, postgresql_container, tmp_path):
        """Test complex PL/pgSQL function with nested blocks."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE accounts (
            id SERIAL PRIMARY KEY,
            balance DECIMAL(10, 2)
        );

        CREATE OR REPLACE FUNCTION transfer_funds(
            from_account INT,
            to_account INT,
            amount DECIMAL
        ) RETURNS BOOLEAN AS $$
        DECLARE
            from_balance DECIMAL;
        BEGIN
            -- Get source balance with row lock
            SELECT balance INTO from_balance
            FROM accounts
            WHERE id = from_account
            FOR UPDATE;

            -- Check sufficient funds
            IF from_balance < amount THEN
                RAISE EXCEPTION 'Insufficient funds: % < %', from_balance, amount;
            END IF;

            -- Perform transfer (two updates)
            UPDATE accounts SET balance = balance - amount
            WHERE id = from_account;

            UPDATE accounts SET balance = balance + amount
            WHERE id = to_account;

            RETURN TRUE;
        EXCEPTION
            WHEN OTHERS THEN
                RAISE NOTICE 'Transfer failed: %', SQLERRM;
                RETURN FALSE;
        END;
        $$ LANGUAGE plpgsql;

        -- Insert test data
        INSERT INTO accounts (balance) VALUES (1000.00), (500.00);
        """

        create_migration(migrations_dir, "V1_0_0__transfer_func.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(postgresql_container, "accounts")

    def test_plpgsql_trigger(self, postgresql_container, tmp_path):
        """Test PL/pgSQL trigger creation."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE audit_log (
            id SERIAL PRIMARY KEY,
            table_name VARCHAR(100),
            operation VARCHAR(10),
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100),
            email VARCHAR(255)
        );

        -- Trigger function
        CREATE OR REPLACE FUNCTION audit_trigger_func()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO audit_log (table_name, operation)
            VALUES (TG_TABLE_NAME, TG_OP);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        -- Trigger
        CREATE TRIGGER users_audit_trigger
        AFTER INSERT OR UPDATE OR DELETE ON users
        FOR EACH ROW
        EXECUTE FUNCTION audit_trigger_func();
        """

        create_migration(migrations_dir, "V1_0_0__audit_trigger.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_string_literals_with_quotes(self, postgresql_container, tmp_path):
        """Test various string literal formats."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE messages (
            id SERIAL PRIMARY KEY,
            text TEXT
        );

        -- Standard single quotes
        INSERT INTO messages (text) VALUES ('Simple message');

        -- Escaped quotes
        INSERT INTO messages (text) VALUES ('Message with ''quoted'' text');

        -- Semicolon in string
        INSERT INTO messages (text) VALUES ('Message with semicolon; inside');

        -- Backslash in string
        INSERT INTO messages (text) VALUES ('Path: C:\\Users\\test');

        -- Dollar quote
        INSERT INTO messages (text) VALUES ($$Message with 'any' characters$$);
        """

        create_migration(migrations_dir, "V1_0_0__strings.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_comments_various_styles(self, postgresql_container, tmp_path):
        """Test various comment styles."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        -- Single line comment
        CREATE TABLE test1 (id SERIAL PRIMARY KEY);

        /* Multi-line comment
           spanning several lines
           with semicolons; in it
        */
        CREATE TABLE test2 (id SERIAL PRIMARY KEY);

        /* Block comment before test3; C-style block comments do not nest in PostgreSQL. */
        CREATE TABLE test3 (id SERIAL PRIMARY KEY);

        -- Comment at end of line
        CREATE TABLE test4 (id SERIAL PRIMARY KEY); -- another comment

        /* Comment with SQL keywords
           SELECT * FROM users;
           DELETE FROM logs;
        */
        CREATE TABLE test5 (id SERIAL PRIMARY KEY);
        """

        create_migration(migrations_dir, "V1_0_0__comments.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_complex_query_with_cte(self, postgresql_container, tmp_path):
        """Test complex query with Common Table Expressions."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE sales (
            id SERIAL PRIMARY KEY,
            product_id INT,
            amount DECIMAL(10, 2),
            sale_date DATE
        );

        CREATE VIEW monthly_sales AS
        WITH monthly_totals AS (
            SELECT
                DATE_TRUNC('month', sale_date) AS month,
                product_id,
                SUM(amount) AS total
            FROM sales
            GROUP BY DATE_TRUNC('month', sale_date), product_id
        ),
        product_ranks AS (
            SELECT
                month,
                product_id,
                total,
                RANK() OVER (PARTITION BY month ORDER BY total DESC) AS rank
            FROM monthly_totals
        )
        SELECT * FROM product_ranks
        WHERE rank <= 10;
        """

        create_migration(migrations_dir, "V1_0_0__cte_view.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_array_and_json_types(self, postgresql_container, tmp_path):
        """Test PostgreSQL-specific data types."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE products (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            tags TEXT[],
            metadata JSONB
        );

        -- Insert with array
        INSERT INTO products (name, tags, metadata) VALUES
        ('Product 1', ARRAY['electronics', 'sale'], '{"price": 99.99, "inStock": true}'),
        ('Product 2', ARRAY['clothing', 'new'], '{"price": 49.99, "sizes": ["S", "M", "L"]}');

        -- Create index on JSONB
        CREATE INDEX idx_metadata ON products USING GIN (metadata);
        """

        create_migration(migrations_dir, "V1_0_0__pg_types.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_extension_creation(self, postgresql_container, tmp_path):
        """Test PostgreSQL extension creation."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE test_table (
            id SERIAL PRIMARY KEY,
            data TEXT
        );

        -- Create commonly available extensions
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
        CREATE EXTENSION IF NOT EXISTS btree_gin;
        
        -- Create with specific version (if available)
        CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

        -- Use extension functionality
        CREATE INDEX idx_data_trgm ON test_table USING GIN (data gin_trgm_ops);
        """

        create_migration(migrations_dir, "V1_0_0__extensions.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(postgresql_container, "test_table")

    def test_foreign_data_wrapper_creation(self, postgresql_container, tmp_path):
        """Test PostgreSQL foreign data wrapper creation."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE local_table (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100)
        );

        -- Create foreign data wrapper (using file_fdw which is commonly available)
        CREATE EXTENSION IF NOT EXISTS file_fdw;
        
        CREATE FOREIGN DATA WRAPPER custom_fdw
            HANDLER file_fdw_handler
            VALIDATOR file_fdw_validator;

        -- Note: This just tests parser support, not actual FDW functionality
        INSERT INTO local_table (name) VALUES ('local data');
        """

        create_migration(migrations_dir, "V1_0_0__fdw.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_foreign_server_creation(self, postgresql_container, tmp_path):
        """Test PostgreSQL foreign server creation."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE local_data (
            id SERIAL PRIMARY KEY,
            value TEXT
        );

        -- Create extension and FDW first
        CREATE EXTENSION IF NOT EXISTS postgres_fdw;

        -- Create foreign server
        CREATE SERVER remote_postgres
            FOREIGN DATA WRAPPER postgres_fdw
            OPTIONS (host 'remote.server.com', port '5432', dbname 'remote_db');

        -- Alternative: File-based server
        CREATE EXTENSION IF NOT EXISTS file_fdw;
        
        CREATE SERVER file_server
            FOREIGN DATA WRAPPER file_fdw;

        -- Note: Actual foreign table creation would require valid connection
        -- This test just ensures parser handles the syntax
        INSERT INTO local_data (value) VALUES ('test');
        """

        create_migration(migrations_dir, "V1_0_0__foreign_server.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
