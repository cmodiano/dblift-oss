import pytest

from core.sql_model.index import Index

pytestmark = [pytest.mark.unit]


def test_index_normalizes_include_columns_in_init():
    index = Index(
        name="ix_test",
        table_name="t",
        columns=["c1"],
        include_columns=[{"name": "c2"}, {"alias": "c3"}, "c4"],
    )

    assert index.include_columns == ["c2", "c3", "c4"]


def test_index_from_dict_handles_legacy_include_column_payload():
    data = {
        "name": "ix_test",
        "table_name": "t",
        "columns": ["c1"],
        "include_columns": [{"name": "c2"}, {"COLUMN_NAME": "c5"}],
    }

    index = Index.from_dict(data)

    assert index.include_columns == ["c2", "c5"]


def test_index_create_statement_with_expression_column():
    index = Index(
        name="idx_upper_email",
        table_name="customers",
        columns=['UPPER("email")'],
        sort_directions=["ASC"],
        dialect="oracle",
        expression_flags=[True],
    )

    stmt = index.create_statement
    assert 'UPPER("email")' in stmt
    assert '""UPPER("email")""' not in stmt


def test_index_create_statement_includes_tablespace_for_oracle():
    index = Index(
        name="idx_sales_region",
        table_name="sales",
        columns=["region"],
        sort_directions=["ASC"],
        dialect="oracle",
        type="BITMAP",
        tablespace="USERS",
    )

    stmt = index.create_statement
    assert stmt.startswith("CREATE BITMAP INDEX")
    assert 'TABLESPACE "USERS"' in stmt


def test_index_create_statement_marks_local_for_oracle_bitmap():
    index = Index(
        name="idx_sales_region",
        table_name="sales",
        columns=["region"],
        sort_directions=["ASC"],
        dialect="oracle",
        type="BITMAP",
        is_local=True,
    )

    stmt = index.create_statement
    assert "CREATE BITMAP INDEX" in stmt
    assert " LOCAL" in stmt


def test_mysql_index_does_not_schema_qualify_name():
    index = Index(
        name="idx_products_deleted",
        table_name="products",
        columns=["is_deleted"],
        schema="store_app_metadata",
        table_schema="store_app_metadata",
        dialect="mysql",
    )

    stmt = index.create_statement
    assert "`store_app_metadata`.`idx_products_deleted`" not in stmt
    assert "CREATE INDEX `idx_products_deleted` ON `store_app_metadata`.`products`" in stmt
    drop_stmt = index.drop_statement
    assert drop_stmt == "DROP INDEX `idx_products_deleted` ON `store_app_metadata`.`products`"


def test_index_with_fillfactor():
    """Test index with fillfactor property."""
    index = Index(
        name="idx_users_email",
        table_name="users",
        columns=["email"],
        fillfactor=90,
        dialect="postgresql",
    )

    assert index.fillfactor == 90
    # Test that property is set correctly
    # Note: SQL generation may use generators that don't include fillfactor yet
    # This test verifies the property is stored correctly
    stmt = index._generate_basic_create_statement()
    assert "fillfactor = 90" in stmt.lower() or "fillfactor=90" in stmt.lower()


def test_index_with_compression():
    """Test index with compression property."""
    index = Index(
        name="idx_users_email",
        table_name="users",
        columns=["email"],
        compression="pglz",
        dialect="postgresql",
    )

    assert index.compression == "pglz"
    stmt = index.create_statement
    assert "compression" in stmt.lower()


def test_index_with_fillfactor_and_compression():
    """Test index with both fillfactor and compression combines into single WITH clause."""
    index = Index(
        name="idx_users_email",
        table_name="users",
        columns=["email"],
        fillfactor=90,
        compression="lz4",
        dialect="postgresql",
    )

    stmt = index.create_statement
    # Verify both options are present
    assert "fillfactor = 90" in stmt.lower() or "fillfactor=90" in stmt.lower()
    assert "compression" in stmt.lower()
    assert "lz4" in stmt.lower()
    # Verify there's only one WITH clause
    with_count = stmt.lower().count("with (")
    assert with_count == 1, f"Expected exactly one WITH clause, found {with_count}. SQL: {stmt}"
    # Verify options are comma-separated in single WITH clause
    assert "fillfactor" in stmt and "compression" in stmt
    # Verify no duplicate WITH keywords
    assert stmt.count("WITH (") == 1, f"Multiple WITH clauses found. SQL: {stmt}"


def test_index_with_comment():
    """Test index with comment property."""
    index = Index(
        name="idx_users_email",
        table_name="users",
        columns=["email"],
        comment="Index on email column for fast lookups",
        dialect="postgresql",
    )

    assert index.comment == "Index on email column for fast lookups"


class TestIndexDropStatement:
    def test_postgresql_uses_if_exists(self):
        idx = Index(
            name="idx_users_email", table_name="users", columns=["email"], dialect="postgresql"
        )
        assert idx.drop_statement == 'DROP INDEX IF EXISTS "idx_users_email"'

    def test_oracle_omits_if_exists(self):
        idx = Index(
            name="IDX_USERS_EMAIL",
            table_name="USERS",
            columns=["EMAIL"],
            schema="HR",
            dialect="oracle",
        )
        assert idx.drop_statement == 'DROP INDEX "HR"."IDX_USERS_EMAIL"'
        assert "IF EXISTS" not in idx.drop_statement

    def test_db2_omits_if_exists(self):
        idx = Index(
            name="IDX_USERS_EMAIL",
            table_name="USERS",
            columns=["EMAIL"],
            schema="DB2INST1",
            dialect="db2",
        )
        assert idx.drop_statement == 'DROP INDEX "DB2INST1"."IDX_USERS_EMAIL"'
        assert "IF EXISTS" not in idx.drop_statement

    def test_mysql_uses_table_form_no_if_exists(self):
        idx = Index(name="idx_users_email", table_name="users", columns=["email"], dialect="mysql")
        assert idx.drop_statement == "DROP INDEX `idx_users_email` ON `users`"
        assert "IF EXISTS" not in idx.drop_statement

    def test_sqlserver_uses_table_form_with_if_exists(self):
        idx = Index(
            name="idx_users_email", table_name="users", columns=["email"], dialect="sqlserver"
        )
        assert idx.drop_statement == "DROP INDEX IF EXISTS [idx_users_email] ON [users]"


def test_index_properties_serialization():
    """Test index properties in to_dict and from_dict."""
    index = Index(
        name="idx_users_email",
        table_name="users",
        columns=["email"],
        fillfactor=90,
        compression="pglz",
        comment="Email index",
        dialect="postgresql",
    )
    data = index.to_dict()

    assert data.get("fillfactor") == 90
    assert data.get("compression") == "pglz"
    assert data.get("comment") == "Email index"

    restored = Index.from_dict(data)
    assert restored.fillfactor == 90
    assert restored.compression == "pglz"
    assert restored.comment == "Email index"
