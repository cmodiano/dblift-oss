"""Unit tests for partition scheme parsing (PARTITION BY clause)."""

import pytest

from core.sql_parser.hybrid_parser import HybridParser

pytestmark = [pytest.mark.unit]


class TestPartitionSchemePostgreSQL:
    """Test PostgreSQL partition scheme parsing."""

    def test_parse_range_partition(self):
        """Test parsing PARTITION BY RANGE."""
        sql = """
        CREATE TABLE sales (
            sale_id INT,
            sale_date DATE,
            amount DECIMAL(10,2)
        ) PARTITION BY RANGE (sale_date);
        """

        parser = HybridParser("postgresql")
        result = parser.parse_sql(sql, default_schema="test_schema")

        assert result.success
        table = result.tables[0]
        assert table.partition_method == "RANGE"
        # PostgreSQL is case-preserving; parser uppercases from SQL
        assert table.partition_columns == ["SALE_DATE"]

    def test_parse_list_partition(self):
        """Test parsing PARTITION BY LIST."""
        sql = """
        CREATE TABLE employees (
            emp_id INT,
            region VARCHAR(50)
        ) PARTITION BY LIST (region);
        """

        parser = HybridParser("postgresql")
        result = parser.parse_sql(sql, default_schema="test_schema")

        assert result.success
        table = result.tables[0]
        assert table.partition_method == "LIST"
        # Parser uppercases from SQL
        assert table.partition_columns == ["REGION"]

    def test_parse_hash_partition(self):
        """Test parsing PARTITION BY HASH."""
        sql = """
        CREATE TABLE orders (
            order_id INT,
            customer_id INT
        ) PARTITION BY HASH (customer_id);
        """

        parser = HybridParser("postgresql")
        result = parser.parse_sql(sql, default_schema="test_schema")

        assert result.success
        table = result.tables[0]
        assert table.partition_method == "HASH"
        # Parser uppercases from SQL
        assert table.partition_columns == ["CUSTOMER_ID"]


class TestPartitionSchemeMySQL:
    """Test MySQL partition scheme parsing."""

    def test_parse_range_partition(self):
        """Test parsing PARTITION BY RANGE."""
        sql = """
        CREATE TABLE sales (
            sale_id INT,
            sale_date DATE,
            amount DECIMAL(10,2)
        )
        PARTITION BY RANGE (YEAR(sale_date)) (
            PARTITION p2023 VALUES LESS THAN (2024),
            PARTITION p2024 VALUES LESS THAN (2025)
        );
        """

        parser = HybridParser("mysql")
        result = parser.parse_sql(sql, default_schema="test_schema")

        assert result.success
        table = result.tables[0]
        assert table.partition_method == "RANGE"
        # Parser should extract "sale_date" from YEAR(sale_date), skipping YEAR function
        assert table.partition_columns == ["SALE_DATE"]

    def test_parse_key_partition(self):
        """Test parsing PARTITION BY KEY (MySQL-specific)."""
        sql = """
        CREATE TABLE users (
            user_id INT,
            username VARCHAR(100)
        )
        PARTITION BY KEY (user_id) PARTITIONS 4;
        """

        parser = HybridParser("mysql")
        result = parser.parse_sql(sql, default_schema="test_schema")

        assert result.success
        table = result.tables[0]
        assert table.partition_method == "KEY"
        # Parser uppercases from SQL
        assert table.partition_columns == ["USER_ID"]

    def test_parse_range_partition_with_nested_function(self):
        """Ensure nested functions inside PARTITION BY are handled."""
        sql = """
        CREATE TABLE invoices (
            invoice_id INT,
            created_at DATETIME
        )
        PARTITION BY RANGE (TO_DAYS(DATE(created_at))) (
            PARTITION p_old VALUES LESS THAN (TO_DAYS('2024-01-01')),
            PARTITION p_new VALUES LESS THAN (TO_DAYS('2025-01-01'))
        );
        """

        parser = HybridParser("mysql")
        result = parser.parse_sql(sql, default_schema="test_schema")

        assert result.success
        table = result.tables[0]
        assert table.partition_method == "RANGE"
        assert table.partition_columns == ["CREATED_AT"]


class TestNonPartitionedTables:
    """Test that non-partitioned tables don't get partition properties."""

    @pytest.mark.parametrize("dialect", ["postgresql", "mysql"])
    def test_regular_table_no_partition(self, dialect):
        """Test regular CREATE TABLE doesn't set partition properties."""
        sql = """
        CREATE TABLE users (
            id INT PRIMARY KEY,
            name VARCHAR(100)
        );
        """

        parser = HybridParser(dialect)
        result = parser.parse_sql(sql, default_schema="test_schema")

        assert result.success
        table = result.tables[0]
        assert table.partition_method is None
        assert table.partition_columns is None
