"""
Test Oracle PL/SQL parsing through CLI.

CRITICAL: These tests verify that the Oracle parser correctly handles
complex Oracle scripts including:
- PL/SQL blocks (BEGIN/END)
- Stored procedures and functions with slash delimiter
- Packages (specification and body)
- Triggers
- Complex nested blocks
- String literals with special characters
- Comments

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
class TestOracleParser:
    """Test Oracle PL/SQL parsing through CLI."""

    def test_slash_delimiter_basic(self, oracle_container, tmp_path):
        """Test basic slash (/) delimiter for PL/SQL blocks."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE employees (
            emp_id NUMBER PRIMARY KEY,
            emp_name VARCHAR2(100),
            salary NUMBER(10, 2)
        );

        CREATE OR REPLACE PROCEDURE add_employee(
            p_id IN NUMBER,
            p_name IN VARCHAR2,
            p_salary IN NUMBER
        ) AS
        BEGIN
            INSERT INTO employees (emp_id, emp_name, salary)
            VALUES (p_id, p_name, p_salary);
            COMMIT;
        END;
        /

        INSERT INTO employees VALUES (1, 'John Doe', 50000);
        """

        create_migration(migrations_dir, "V1_0_0__procedures.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Migration failed: {result.stderr}"
        assert verify_table_exists(
            oracle_container, "employees", schema=oracle_container.get("schema", "DBLIFT_TEST")
        )

    def test_anonymous_plsql_block(self, oracle_container, tmp_path):
        """Test anonymous PL/SQL blocks with BEGIN/END."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE config (
            key VARCHAR2(100) PRIMARY KEY,
            value VARCHAR2(4000)
        );

        BEGIN
            -- Anonymous PL/SQL block
            INSERT INTO config VALUES ('version', '1.0.0');
            INSERT INTO config VALUES ('env', 'production');
            COMMIT;
        END;
        /

        -- Regular SQL after the block
        CREATE INDEX idx_config_value ON config(value);
        """

        create_migration(migrations_dir, "V1_0_0__anonymous.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_package_spec_and_body(self, oracle_container, tmp_path):
        """Test Oracle package specification and body."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE orders (
            order_id NUMBER PRIMARY KEY,
            total NUMBER(10, 2)
        );

        -- Package specification
        CREATE OR REPLACE PACKAGE order_pkg AS
            FUNCTION get_order_count RETURN NUMBER;
            PROCEDURE add_order(p_id NUMBER, p_total NUMBER);
        END order_pkg;
        /

        -- Package body
        CREATE OR REPLACE PACKAGE BODY order_pkg AS
            FUNCTION get_order_count RETURN NUMBER IS
                v_count NUMBER;
            BEGIN
                SELECT COUNT(*) INTO v_count FROM orders;
                RETURN v_count;
            END get_order_count;

            PROCEDURE add_order(p_id NUMBER, p_total NUMBER) IS
            BEGIN
                INSERT INTO orders (order_id, total)
                VALUES (p_id, p_total);
                COMMIT;
            END add_order;
        END order_pkg;
        /
        """

        create_migration(migrations_dir, "V1_0_0__package.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_nested_plsql_blocks(self, oracle_container, tmp_path):
        """Test nested PL/SQL blocks."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE accounts (
            account_id NUMBER PRIMARY KEY,
            balance NUMBER(10, 2)
        );

        CREATE OR REPLACE PROCEDURE transfer_funds(
            p_from_account NUMBER,
            p_to_account NUMBER,
            p_amount NUMBER
        ) AS
            v_balance NUMBER;
        BEGIN
            -- Outer block
            SELECT balance INTO v_balance
            FROM accounts
            WHERE account_id = p_from_account
            FOR UPDATE;

            IF v_balance >= p_amount THEN
                -- Nested block
                BEGIN
                    UPDATE accounts
                    SET balance = balance - p_amount
                    WHERE account_id = p_from_account;

                    UPDATE accounts
                    SET balance = balance + p_amount
                    WHERE account_id = p_to_account;

                    COMMIT;
                EXCEPTION
                    WHEN OTHERS THEN
                        ROLLBACK;
                        RAISE;
                END;
            ELSE
                RAISE_APPLICATION_ERROR(-20001, 'Insufficient funds');
            END IF;
        END transfer_funds;
        /

        INSERT INTO accounts VALUES (1, 1000);
        INSERT INTO accounts VALUES (2, 500);
        """

        create_migration(migrations_dir, "V1_0_0__nested.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_trigger_with_plsql(self, oracle_container, tmp_path):
        """Test trigger with PL/SQL body."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE audit_log (
            log_id NUMBER PRIMARY KEY,
            table_name VARCHAR2(100),
            operation VARCHAR2(10),
            log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE SEQUENCE audit_log_seq START WITH 1;

        CREATE TABLE users (
            user_id NUMBER PRIMARY KEY,
            username VARCHAR2(100)
        );

        CREATE OR REPLACE TRIGGER users_audit_trigger
        AFTER INSERT OR UPDATE OR DELETE ON users
        FOR EACH ROW
        DECLARE
            v_operation VARCHAR2(10);
        BEGIN
            IF INSERTING THEN
                v_operation := 'INSERT';
            ELSIF UPDATING THEN
                v_operation := 'UPDATE';
            ELSIF DELETING THEN
                v_operation := 'DELETE';
            END IF;

            INSERT INTO audit_log (log_id, table_name, operation)
            VALUES (audit_log_seq.NEXTVAL, 'users', v_operation);
        END;
        /
        """

        create_migration(migrations_dir, "V1_0_0__trigger.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_string_literals_with_quotes(self, oracle_container, tmp_path):
        """Test string literals with single quotes."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE messages (
            id NUMBER PRIMARY KEY,
            text VARCHAR2(4000)
        );

        -- String with embedded quote (escaped as '')
        INSERT INTO messages VALUES (1, 'This has a ''quoted'' word');

        -- PL/SQL block with string containing quote
        BEGIN
            INSERT INTO messages VALUES (2, 'Don''t split this; it''s one string');
            COMMIT;
        END;
        /

        -- Q-quote alternative quote delimiter
        INSERT INTO messages VALUES (3, Q'[This has 'quotes' and semicolons; no problem]');
        """

        create_migration(migrations_dir, "V1_0_0__strings.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_comments_in_plsql(self, oracle_container, tmp_path):
        """Test various Oracle comment styles in PL/SQL."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        -- Single line comment before table
        CREATE TABLE test_table (
            id NUMBER PRIMARY KEY,
            name VARCHAR2(100) -- inline comment
        );

        /* Multi-line comment
           with multiple lines
           and even a slash / in it
           and semicolon;
        */
        CREATE OR REPLACE PROCEDURE test_proc AS
        BEGIN
            -- Comment inside procedure
            NULL; -- Do nothing
            /* Nested comment
               with / slash
            */
        END test_proc;
        /
        """

        create_migration(migrations_dir, "V1_0_0__comments.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_function_with_return(self, oracle_container, tmp_path):
        """Test function with RETURN clause."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE products (
            product_id NUMBER PRIMARY KEY,
            price NUMBER(10, 2)
        );

        CREATE OR REPLACE FUNCTION calculate_tax(
            p_price NUMBER
        ) RETURN NUMBER
        DETERMINISTIC
        AS
            v_tax NUMBER;
        BEGIN
            v_tax := p_price * 0.08;
            RETURN v_tax;
        END calculate_tax;
        /

        INSERT INTO products VALUES (1, 100.00);
        """

        create_migration(migrations_dir, "V1_0_0__function.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_cursor_in_procedure(self, oracle_container, tmp_path):
        """Test cursor declaration and usage in procedure."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE departments (
            dept_id NUMBER PRIMARY KEY,
            dept_name VARCHAR2(100)
        );

        CREATE TABLE dept_summary (
            summary_id NUMBER PRIMARY KEY,
            summary_text VARCHAR2(4000)
        );

        CREATE OR REPLACE PROCEDURE process_departments AS
            CURSOR dept_cursor IS
                SELECT dept_id, dept_name
                FROM departments
                ORDER BY dept_id;
            
            v_summary VARCHAR2(4000);
        BEGIN
            v_summary := 'Departments: ';
            
            FOR dept_rec IN dept_cursor LOOP
                v_summary := v_summary || dept_rec.dept_name || '; ';
            END LOOP;
            
            INSERT INTO dept_summary VALUES (1, v_summary);
            COMMIT;
        END process_departments;
        /

        INSERT INTO departments VALUES (1, 'Engineering');
        INSERT INTO departments VALUES (2, 'Sales');
        """

        create_migration(migrations_dir, "V1_0_0__cursor.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_case_expression_in_plsql(self, oracle_container, tmp_path):
        """Test CASE expressions in PL/SQL."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE order_status (
            status_id NUMBER PRIMARY KEY,
            status_name VARCHAR2(50)
        );

        CREATE OR REPLACE PROCEDURE update_status(
            p_status_code NUMBER
        ) AS
            v_status_name VARCHAR2(50);
        BEGIN
            v_status_name := CASE p_status_code
                WHEN 1 THEN 'Pending'
                WHEN 2 THEN 'Processing'
                WHEN 3 THEN 'Shipped'
                WHEN 4 THEN 'Delivered'
                ELSE 'Unknown'
            END;
            
            INSERT INTO order_status VALUES (p_status_code, v_status_name);
            COMMIT;
        END update_status;
        /
        """

        create_migration(migrations_dir, "V1_0_0__case.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_exception_handling(self, oracle_container, tmp_path):
        """Test exception handling in PL/SQL."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE error_log (
            error_id NUMBER PRIMARY KEY,
            error_msg VARCHAR2(4000)
        );

        CREATE SEQUENCE error_log_seq START WITH 1;

        CREATE OR REPLACE PROCEDURE safe_operation(
            p_value NUMBER
        ) AS
            v_result NUMBER;
        BEGIN
            -- This might raise division by zero
            v_result := 100 / p_value;
            
        EXCEPTION
            WHEN ZERO_DIVIDE THEN
                INSERT INTO error_log VALUES (
                    error_log_seq.NEXTVAL,
                    'Division by zero error'
                );
                COMMIT;
            WHEN OTHERS THEN
                INSERT INTO error_log VALUES (
                    error_log_seq.NEXTVAL,
                    'Unknown error: ' || SQLERRM
                );
                COMMIT;
        END safe_operation;
        /
        """

        create_migration(migrations_dir, "V1_0_0__exception.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_multiple_statements_one_slash(self, oracle_container, tmp_path):
        """Test that slash only terminates PL/SQL blocks, not regular SQL."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE table1 (id NUMBER PRIMARY KEY, name VARCHAR2(100));
        CREATE TABLE table2 (id NUMBER PRIMARY KEY, name VARCHAR2(100));
        CREATE TABLE table3 (id NUMBER PRIMARY KEY, name VARCHAR2(100));

        -- Now a PL/SQL block that needs slash
        BEGIN
            INSERT INTO table1 VALUES (1, 'Test1');
            INSERT INTO table2 VALUES (2, 'Test2');
            INSERT INTO table3 VALUES (3, 'Test3');
            COMMIT;
        END;
        /

        -- Back to regular SQL (semicolon terminated)
        CREATE INDEX idx_table1 ON table1(name);
        CREATE INDEX idx_table2 ON table2(name);
        """

        create_migration(migrations_dir, "V1_0_0__mixed.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    @pytest.mark.skip(
        reason="Database links require elevated Oracle privileges (CREATE DATABASE LINK)"
    )
    def test_database_link_creation(self, oracle_container, tmp_path):
        """Test Oracle database link creation - SKIPPED due to privilege requirements."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE employees (
            emp_id NUMBER PRIMARY KEY,
            emp_name VARCHAR2(100)
        );

        -- Database links using local connection for testing
        CREATE DATABASE LINK remote_db
            CONNECT TO system IDENTIFIED BY oracle
            USING '(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=localhost)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=XEPDB1)))';

        -- Alternative: Public database link
        CREATE PUBLIC DATABASE LINK public_remote
            CONNECT TO system IDENTIFIED BY oracle
            USING '(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=localhost)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=XEPDB1)))';
        """

        create_migration(migrations_dir, "V1_0_0__database_links.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
        # Note: Database links require proper network configuration to verify
        # This test just ensures the SQL is parsed correctly

    def test_create_or_replace_view(self, oracle_container, tmp_path):
        """Test CREATE OR REPLACE VIEW syntax (Oracle grammar-based)."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE employees (
            emp_id NUMBER PRIMARY KEY,
            emp_name VARCHAR2(100)
        );

        CREATE OR REPLACE VIEW vw_employees AS
        SELECT emp_id, emp_name FROM employees;
        """

        create_migration(migrations_dir, "V1_0_0__or_replace_view.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_bitmap_index(self, oracle_container, tmp_path):
        """Test CREATE BITMAP INDEX syntax (Oracle grammar-based)."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE employees (
            emp_id NUMBER PRIMARY KEY,
            status VARCHAR2(20)
        );

        CREATE BITMAP INDEX idx_status ON employees(status);
        """

        create_migration(migrations_dir, "V1_0_0__bitmap_index.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_index_with_tablespace(self, oracle_container, tmp_path):
        """Test CREATE INDEX with TABLESPACE clause (Oracle grammar-based)."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE employees (
            emp_id NUMBER PRIMARY KEY,
            emp_name VARCHAR2(100)
        );

        CREATE INDEX idx_name ON employees(emp_name) TABLESPACE USERS;
        """

        create_migration(migrations_dir, "V1_0_0__index_tablespace.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_create_synonym(self, oracle_container, tmp_path):
        """Test CREATE OR REPLACE SYNONYM syntax (Oracle grammar-based)."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE employees (
            emp_id NUMBER PRIMARY KEY,
            emp_name VARCHAR2(100)
        );

        CREATE OR REPLACE PUBLIC SYNONYM emp FOR employees;
        """

        create_migration(migrations_dir, "V1_0_0__synonym.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_create_materialized_view(self, oracle_container, tmp_path):
        """Test CREATE MATERIALIZED VIEW syntax (Oracle grammar-based)."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE employees (
            emp_id NUMBER PRIMARY KEY,
            emp_name VARCHAR2(100),
            salary NUMBER(10,2)
        );

        CREATE MATERIALIZED VIEW mv_employees
        BUILD IMMEDIATE
        REFRESH COMPLETE ON DEMAND
        AS SELECT * FROM employees;
        """

        create_migration(migrations_dir, "V1_0_0__materialized_view.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_create_force_view(self, oracle_container, tmp_path):
        """Test CREATE OR REPLACE FORCE VIEW syntax (Oracle grammar-based)."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, oracle_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE employees (
            emp_id NUMBER PRIMARY KEY,
            emp_name VARCHAR2(100)
        );

        -- FORCE view can be created even if referenced objects don't exist yet
        CREATE OR REPLACE FORCE VIEW vw_test AS
        SELECT * FROM employees WHERE dept_id IN (SELECT dept_id FROM departments);
        """

        create_migration(migrations_dir, "V1_0_0__force_view.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
