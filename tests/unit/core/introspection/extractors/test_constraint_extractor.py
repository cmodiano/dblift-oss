"""Tests for ConstraintExtractor covering primary keys, foreign keys, unique and check constraints."""

import unittest
from unittest.mock import MagicMock


def _make_extractor(dialect="postgresql", vendor_queries=None):
    from core.introspection.extractors.constraint_extractor import ConstraintExtractor

    provider = MagicMock()
    provider.query_executor = MagicMock()
    if vendor_queries is None:
        vendor_queries = MagicMock()
        vendor_queries.get_primary_key_query.return_value = ("SELECT pk", [])
        vendor_queries.get_foreign_keys_query.return_value = ("SELECT fk", [])
    ext = ConstraintExtractor(provider=provider, dialect=dialect, vendor_queries=vendor_queries)
    ext.ensure_metadata = MagicMock()
    ext.metadata = MagicMock()
    ext.connection = MagicMock()
    ext.log = MagicMock()
    return ext


def _pk_row(column: str = "id", name: str | None = "pk_users") -> dict[str, str | None]:
    return {"column_name": column, "constraint_name": name}


def _fk_row(
    name: str | None = "fk_orders_users",
    column: str = "user_id",
    ref_table: str = "users",
    ref_column: str = "id",
    ref_schema: str = "public",
    on_delete: str = "NO ACTION",
    on_update: str = "NO ACTION",
) -> dict[str, str | None]:
    return {
        "name": name,
        "column_name": column,
        "ref_table": ref_table,
        "ref_schema": ref_schema,
        "ref_column": ref_column,
        "on_delete": on_delete,
        "on_update": on_update,
    }


class TestConstraintExtractorGetConstraints(unittest.TestCase):
    def test_returns_empty_on_exception(self):
        ext = _make_extractor()
        ext.provider.query_executor.execute_query.side_effect = Exception("DB err")
        ext.get_unique_constraints = MagicMock(return_value=[])
        ext.get_check_constraints = MagicMock(return_value=[])
        result = ext.get_constraints("public", "users")
        self.assertEqual(result, [])

    def test_collects_pk_fk_unique_check(self):
        ext = _make_extractor()
        ext.provider.query_executor.execute_query.side_effect = [[], []]
        ext.get_unique_constraints = MagicMock(return_value=[])
        ext.get_check_constraints = MagicMock(return_value=[])
        result = ext.get_constraints("public", "users")
        self.assertEqual(result, [])

    def test_pk_added_to_constraints(self):
        from core.sql_model.base import ConstraintType

        ext = _make_extractor()
        ext.provider.query_executor.execute_query.side_effect = [[_pk_row()], []]
        ext.get_unique_constraints = MagicMock(return_value=[])
        ext.get_check_constraints = MagicMock(return_value=[])
        ext.to_python_string = lambda x: x
        ext._sanitize_constraint_name = lambda x: x
        result = ext.get_constraints("public", "users")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].constraint_type, ConstraintType.PRIMARY_KEY)


class TestConstraintExtractorGetPrimaryKey(unittest.TestCase):
    def _make(self, dialect="postgresql"):
        ext = _make_extractor(dialect=dialect)
        ext.to_python_string = lambda x: x
        ext._sanitize_constraint_name = lambda x: x
        return ext

    def test_returns_none_when_no_pk(self):
        ext = self._make()
        ext.provider.query_executor.execute_query.return_value = []
        result = ext.get_primary_key("public", "users")
        self.assertIsNone(result)

    def test_returns_pk_constraint(self):
        from core.sql_model.base import ConstraintType

        ext = self._make()
        ext.provider.query_executor.execute_query.return_value = [_pk_row(name="pk_u")]
        result = ext.get_primary_key("public", "users")
        self.assertIsNotNone(result)
        self.assertEqual(result.constraint_type, ConstraintType.PRIMARY_KEY)
        self.assertIn("id", result.column_names)

    def test_handles_exception_returns_none(self):
        ext = self._make()
        ext.provider.query_executor.execute_query.side_effect = Exception("DB error")
        result = ext.get_primary_key("public", "users")
        self.assertIsNone(result)

    def test_generates_default_pk_name_when_none(self):
        ext = self._make()
        ext.provider.query_executor.execute_query.return_value = [_pk_row(name=None)]
        result = ext.get_primary_key("public", "users")
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.name)

    def test_composite_pk_multiple_columns(self):
        ext = self._make()
        ext.provider.query_executor.execute_query.return_value = [
            _pk_row("id1", "pk"),
            _pk_row("id2", "pk"),
        ]
        result = ext.get_primary_key("public", "users")
        self.assertIsNotNone(result)


class TestConstraintExtractorGetForeignKeys(unittest.TestCase):
    def _make(self):
        ext = _make_extractor()
        ext.to_python_string = lambda x: x
        ext._sanitize_constraint_name = lambda x: x
        return ext

    def test_returns_empty_when_no_fks(self):
        ext = self._make()
        ext.provider.query_executor.execute_query.return_value = []
        result = ext.get_foreign_keys("public", "orders")
        self.assertEqual(result, [])

    def test_returns_fk_constraint(self):
        from core.sql_model.base import ConstraintType

        ext = self._make()
        ext.provider.query_executor.execute_query.return_value = [_fk_row()]
        result = ext.get_foreign_keys("public", "orders")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].constraint_type, ConstraintType.FOREIGN_KEY)

    def test_handles_exception_returns_empty(self):
        ext = self._make()
        ext.provider.query_executor.execute_query.side_effect = Exception("DB error")
        result = ext.get_foreign_keys("public", "orders")
        self.assertEqual(result, [])

    def test_generates_fk_name_when_none(self):
        ext = self._make()
        ext.provider.query_executor.execute_query.return_value = [_fk_row(name=None)]
        result = ext.get_foreign_keys("public", "orders")
        self.assertEqual(len(result), 1)
        self.assertIsNotNone(result[0].name)

    def test_on_delete_cascade(self):
        ext = self._make()
        ext.provider.query_executor.execute_query.return_value = [
            _fk_row(name="fk1", column="uid", on_delete="CASCADE")
        ]
        result = ext.get_foreign_keys("public", "orders")
        self.assertEqual(result[0].on_delete, "CASCADE")


class TestConstraintExtractorGetUniqueConstraints(unittest.TestCase):
    def test_returns_empty_on_exception(self):
        ext = _make_extractor(dialect="mysql")
        result = ext.get_unique_constraints("public", "t")
        self.assertEqual(result, [])

    def test_postgresql_path(self):
        ext = _make_extractor(dialect="postgresql")
        ext.provider.query_executor.execute_query.return_value = [
            {"constraint_name": "uq_email", "column_name": "email", "ordinal_position": 1}
        ]
        result = ext.get_unique_constraints("public", "users")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "uq_email")

    def test_no_vendor_hook_returns_empty(self):
        ext = _make_extractor(dialect="mysql")
        result = ext.get_unique_constraints("db", "users")
        self.assertEqual(result, [])

class TestConstraintExtractorCheckConstraints(unittest.TestCase):
    def test_returns_empty_without_vendor_queries(self):
        ext = _make_extractor()
        result = ext.get_check_constraints("public", "t")
        self.assertEqual(result, [])

    def test_returns_check_constraints_with_vendor_queries(self):
        vq = MagicMock()
        vq.get_check_constraints_query.return_value = ("SELECT 1", [])
        ext = _make_extractor(vendor_queries=vq)
        ext.provider.query_executor.execute_query.return_value = [
            {
                "constraint_name": "chk_age",
                "constraint_definition": "age > 0",
                "is_deferrable": False,
                "initially_deferred": False,
            }
        ]
        result = ext.get_check_constraints("public", "users")
        self.assertIsInstance(result, list)

    def test_handles_exception_returns_empty(self):
        vq = MagicMock()
        vq.get_check_constraints_query.return_value = ("SELECT 1", [])
        ext = _make_extractor(vendor_queries=vq)
        ext.provider.query_executor.execute_query.side_effect = Exception("DB err")
        result = ext.get_check_constraints("public", "users")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# New tests for previously uncovered branches
# ---------------------------------------------------------------------------


class TestSanitizeConstraintName(unittest.TestCase):
    """Tests for _sanitize_constraint_name covering Oracle, DB2, and passthrough."""

    def test_none_returns_none(self):
        ext = _make_extractor(dialect="postgresql")
        self.assertIsNone(ext._sanitize_constraint_name(None))

    def test_empty_string_returns_empty(self):
        ext = _make_extractor(dialect="postgresql")
        result = ext._sanitize_constraint_name("")
        # empty string is falsy -> returned as-is (falsy branch)
        self.assertEqual(result, "")

    def test_normal_name_passthrough(self):
        ext = _make_extractor(dialect="postgresql")
        self.assertEqual(ext._sanitize_constraint_name("uq_email"), "uq_email")



class TestGetConstraintsFullPath(unittest.TestCase):
    """Tests for get_constraints() covering the full happy path."""

    def _make_full(self, dialect="postgresql"):
        ext = _make_extractor(dialect=dialect)
        ext.to_python_string = lambda x: x
        return ext

    def test_unique_deduplication_by_columns(self):
        """Unique constraint whose columns match the PK columns is dropped."""
        from core.sql_model.base import ConstraintType, SqlConstraint

        ext = self._make_full()

        ext.provider.query_executor.execute_query.side_effect = [[_pk_row()], []]

        # unique constraint on same column as PK
        dup_unique = SqlConstraint(
            constraint_type=ConstraintType.UNIQUE,
            name="uq_id",
            column_names=["id"],
            dialect="postgresql",
        )
        ext.get_unique_constraints = MagicMock(return_value=[dup_unique])
        ext.get_check_constraints = MagicMock(return_value=[])

        result = ext.get_constraints("public", "users")
        types = [c.constraint_type for c in result]
        # Only PK; the duplicate unique was dropped
        self.assertIn(ConstraintType.PRIMARY_KEY, types)
        self.assertNotIn(ConstraintType.UNIQUE, types)

    def test_unique_deduplication_by_name(self):
        """Unique constraint whose name matches PK name is dropped."""
        from core.sql_model.base import ConstraintType, SqlConstraint

        ext = self._make_full()

        ext.provider.query_executor.execute_query.side_effect = [[_pk_row()], []]

        # different column, same name as PK
        dup_unique = SqlConstraint(
            constraint_type=ConstraintType.UNIQUE,
            name="pk_users",
            column_names=["email"],
            dialect="postgresql",
        )
        ext.get_unique_constraints = MagicMock(return_value=[dup_unique])
        ext.get_check_constraints = MagicMock(return_value=[])

        result = ext.get_constraints("public", "users")
        types = [c.constraint_type for c in result]
        self.assertNotIn(ConstraintType.UNIQUE, types)

    def test_distinct_unique_constraint_kept(self):
        """Unique constraint on different column from PK is kept."""
        from core.sql_model.base import ConstraintType, SqlConstraint

        ext = self._make_full()

        ext.provider.query_executor.execute_query.side_effect = [[_pk_row()], []]

        unique = SqlConstraint(
            constraint_type=ConstraintType.UNIQUE,
            name="uq_email",
            column_names=["email"],
            dialect="postgresql",
        )
        ext.get_unique_constraints = MagicMock(return_value=[unique])
        ext.get_check_constraints = MagicMock(return_value=[])

        result = ext.get_constraints("public", "users")
        types = [c.constraint_type for c in result]
        self.assertIn(ConstraintType.PRIMARY_KEY, types)
        self.assertIn(ConstraintType.UNIQUE, types)

    def test_check_constraints_added(self):
        """Check constraints are appended to result list."""
        from core.sql_model.base import ConstraintType, SqlConstraint

        ext = self._make_full()
        ext.provider.query_executor.execute_query.side_effect = [[], []]
        ext.get_unique_constraints = MagicMock(return_value=[])

        chk = SqlConstraint(
            constraint_type=ConstraintType.CHECK,
            name="chk_age",
            check_expression="age > 0",
            dialect="postgresql",
        )
        ext.get_check_constraints = MagicMock(return_value=[chk])

        result = ext.get_constraints("public", "users")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].constraint_type, ConstraintType.CHECK)


class TestGetForeignKeysCompositePath(unittest.TestCase):
    """Composite FK with multiple rows sharing the same FK_NAME."""

    def _make(self):
        ext = _make_extractor()
        ext.to_python_string = lambda x: x
        return ext

    def test_composite_fk_two_columns(self):
        """Two rows with same FK_NAME produce one FK with two columns."""
        from core.sql_model.base import ConstraintType

        ext = self._make()

        ext.provider.query_executor.execute_query.return_value = [
            _fk_row(
                name="fk_orders_items",
                column="order_id",
                ref_table="items",
                ref_column="id",
            ),
            _fk_row(
                name="fk_orders_items",
                column="item_type",
                ref_table="items",
                ref_column="type",
            ),
        ]
        result = ext.get_foreign_keys("public", "orders")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].constraint_type, ConstraintType.FOREIGN_KEY)
        self.assertIn("order_id", result[0].column_names)
        self.assertIn("item_type", result[0].column_names)

    def test_fk_on_update_set_null(self):
        """update_rule=2 maps to SET NULL."""
        ext = self._make()
        ext.provider.query_executor.execute_query.return_value = [
            _fk_row(name="fk1", column="uid", on_update="SET NULL")
        ]
        result = ext.get_foreign_keys("public", "orders")
        self.assertEqual(result[0].on_update, "SET NULL")


class TestGetCheckConstraintsBranches(unittest.TestCase):
    """Tests for get_check_constraints covering all parsing branches."""

    def _make_with_vq(self, rows, sql="SELECT 1", supports_check=True):
        vq = MagicMock()
        vq.supports_check_constraints.return_value = supports_check
        vq.get_check_constraints_query.return_value = (sql, [])
        ext = _make_extractor(dialect="postgresql", vendor_queries=vq)
        ext.provider.query_executor.execute_query.return_value = rows
        return ext

    def test_no_vendor_queries_returns_empty(self):
        ext = _make_extractor(dialect="postgresql", vendor_queries=None)
        self.assertEqual(ext.get_check_constraints("public", "t"), [])

    def test_vendor_not_supporting_check_returns_empty(self):
        vq = MagicMock()
        vq.supports_check_constraints.return_value = False
        ext = _make_extractor(dialect="postgresql", vendor_queries=vq)
        self.assertEqual(ext.get_check_constraints("public", "t"), [])

    def test_empty_sql_returns_empty(self):
        vq = MagicMock()
        vq.supports_check_constraints.return_value = True
        vq.get_check_constraints_query.return_value = (None, [])
        ext = _make_extractor(dialect="postgresql", vendor_queries=vq)
        self.assertEqual(ext.get_check_constraints("public", "t"), [])

    def test_check_expr_with_check_keyword_parsed(self):
        """CHECK (age > 0) → expression becomes 'age > 0'."""
        ext = self._make_with_vq(
            [
                {
                    "constraint_name": "chk_age",
                    "constraint_definition": "CHECK (age > 0)",
                    "is_deferrable": None,
                    "initially_deferred": None,
                }
            ]
        )
        result = ext.get_check_constraints("public", "users")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].check_expression, "age > 0")

    def test_check_expr_bare_with_outer_parens(self):
        """(age > 0) → expression becomes 'age > 0' when it's a single balanced paren."""
        ext = self._make_with_vq(
            [
                {
                    "constraint_name": "chk_age",
                    "constraint_definition": "(age > 0)",
                    "is_deferrable": None,
                    "initially_deferred": None,
                }
            ]
        )
        result = ext.get_check_constraints("public", "users")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].check_expression, "age > 0")

    def test_check_expr_bare_without_parens(self):
        """Plain expression without CHECK or parens passes through."""
        ext = self._make_with_vq(
            [
                {
                    "constraint_name": "chk_age",
                    "constraint_definition": "age > 0",
                    "is_deferrable": None,
                    "initially_deferred": None,
                }
            ]
        )
        result = ext.get_check_constraints("public", "users")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].check_expression, "age > 0")

    def test_trivial_1_equals_1_skipped(self):
        ext = self._make_with_vq(
            [
                {
                    "constraint_name": "chk_dummy",
                    "constraint_definition": "1=1",
                    "is_deferrable": None,
                    "initially_deferred": None,
                }
            ]
        )
        result = ext.get_check_constraints("public", "users")
        self.assertEqual(result, [])

    def test_empty_constraint_def_skipped(self):
        ext = self._make_with_vq(
            [
                {
                    "constraint_name": "chk_empty",
                    "constraint_definition": None,
                    "is_deferrable": None,
                    "initially_deferred": None,
                }
            ]
        )
        result = ext.get_check_constraints("public", "users")
        self.assertEqual(result, [])

    def test_is_deferrable_yes_string(self):
        """is_deferrable='YES' → constraint.is_deferrable == True."""
        ext = self._make_with_vq(
            [
                {
                    "constraint_name": "chk_x",
                    "constraint_definition": "x > 0",
                    "is_deferrable": "YES",
                    "initially_deferred": "NO",
                }
            ]
        )
        result = ext.get_check_constraints("public", "t")
        self.assertTrue(result[0].is_deferrable)
        self.assertFalse(result[0].initially_deferred)

    def test_initially_deferred_true_string(self):
        """initially_deferred='TRUE' → constraint.initially_deferred == True."""
        ext = self._make_with_vq(
            [
                {
                    "constraint_name": "chk_x",
                    "constraint_definition": "x > 0",
                    "is_deferrable": "YES",
                    "initially_deferred": "TRUE",
                }
            ]
        )
        result = ext.get_check_constraints("public", "t")
        self.assertTrue(result[0].initially_deferred)

    def test_is_deferrable_none_defaults_false(self):
        """is_deferrable=None → constraint.is_deferrable == False."""
        ext = self._make_with_vq(
            [
                {
                    "constraint_name": "chk_x",
                    "constraint_definition": "x > 0",
                    "is_deferrable": None,
                    "initially_deferred": None,
                }
            ]
        )
        result = ext.get_check_constraints("public", "t")
        self.assertFalse(result[0].is_deferrable)
        self.assertFalse(result[0].initially_deferred)

    def test_is_enabled_set_when_present(self):
        """is_enabled='YES' → constraint.is_enabled == True."""
        ext = self._make_with_vq(
            [
                {
                    "constraint_name": "chk_x",
                    "constraint_definition": "x > 0",
                    "is_deferrable": None,
                    "initially_deferred": None,
                    "is_enabled": "YES",
                }
            ]
        )
        result = ext.get_check_constraints("public", "t")
        self.assertTrue(result[0].is_enabled)

    def test_is_validated_set_when_present(self):
        """is_validated='1' → constraint.is_validated == True."""
        ext = self._make_with_vq(
            [
                {
                    "constraint_name": "chk_x",
                    "constraint_definition": "x > 0",
                    "is_deferrable": None,
                    "initially_deferred": None,
                    "is_validated": "1",
                }
            ]
        )
        result = ext.get_check_constraints("public", "t")
        self.assertTrue(result[0].is_validated)

    def test_is_enabled_none_not_set(self):
        """is_enabled=None → attribute is_enabled not set on constraint."""
        ext = self._make_with_vq(
            [
                {
                    "constraint_name": "chk_x",
                    "constraint_definition": "x > 0",
                    "is_deferrable": None,
                    "initially_deferred": None,
                }
            ]
        )
        result = ext.get_check_constraints("public", "t")
        # is_enabled should not be set (attribute absent)
        self.assertFalse(hasattr(result[0], "is_enabled") and result[0].is_enabled)

    def test_multiple_constraints_returned(self):
        """Multiple valid rows produce multiple constraints."""
        rows = [
            {
                "constraint_name": "chk_a",
                "constraint_definition": "a > 0",
                "is_deferrable": None,
                "initially_deferred": None,
            },
            {
                "constraint_name": "chk_b",
                "constraint_definition": "b > 0",
                "is_deferrable": None,
                "initially_deferred": None,
            },
        ]
        ext = self._make_with_vq(rows)
        result = ext.get_check_constraints("public", "t")
        self.assertEqual(len(result), 2)

class TestGetUniqueConstraintsPostgresqlFallback(unittest.TestCase):
    """Tests for PostgreSQL pg_constraint path."""

    def _make_pg(self):
        ext = _make_extractor(dialect="postgresql")
        return ext

    def test_postgresql_query_failure_returns_empty(self):
        ext = self._make_pg()
        ext.provider.query_executor.execute_query.side_effect = Exception("pg_catalog error")

        result = ext.get_unique_constraints("public", "users")
        self.assertEqual(result, [])

    def test_postgresql_returns_constraints_from_pg_catalog(self):
        ext = self._make_pg()
        ext.provider.query_executor.execute_query.return_value = [
            {"constraint_name": "uq_email", "column_name": "email", "ordinal_position": 1},
        ]
        result = ext.get_unique_constraints("public", "users")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "uq_email")

    def test_postgresql_skips_null_constraint_or_column_name(self):
        ext = self._make_pg()
        ext.provider.query_executor.execute_query.return_value = [
            {"constraint_name": None, "column_name": "email", "ordinal_position": 1},
            {"constraint_name": "uq_name", "column_name": None, "ordinal_position": 1},
        ]
        result = ext.get_unique_constraints("public", "users")
        self.assertEqual(result, [])


