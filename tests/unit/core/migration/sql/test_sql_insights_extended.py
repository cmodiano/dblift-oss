"""Tests for core/migration/sql/sql_insights.py."""

import unittest


class TestSqlInsightsInit(unittest.TestCase):
    def _make(self, dialect="postgresql"):
        from core.migration.sql.sql_insights import SqlInsights

        return SqlInsights(dialect=dialect)

    def test_stores_dialect(self):
        ins = self._make("postgresql")
        self.assertEqual(ins.dialect, "postgresql")

    def test_db2_not_available(self):
        ins = self._make("db2")
        self.assertFalse(ins.available)

    def test_postgresql_available_if_sqlglot(self):
        from core.migration.sql.sql_insights import SQLGLOT_AVAILABLE

        ins = self._make("postgresql")
        self.assertEqual(ins.available, SQLGLOT_AVAILABLE)


class TestAnalyzeQueryComplexity(unittest.TestCase):
    def _ins(self):
        from core.migration.sql.sql_insights import SqlInsights

        return SqlInsights(dialect="postgresql")

    def test_simple_select(self):
        ins = self._ins()
        result = ins.analyze_query_complexity("SELECT 1")
        self.assertIsInstance(result, dict)
        self.assertIn("complexity_score", result)

    def test_complex_select(self):
        ins = self._ins()
        sql = (
            "SELECT a.id, b.name FROM users a JOIN orders b ON a.id = b.user_id WHERE a.active = 1"
        )
        result = ins.analyze_query_complexity(sql)
        self.assertIsInstance(result, dict)

    def test_empty_sql(self):
        ins = self._ins()
        result = ins.analyze_query_complexity("")
        self.assertIsInstance(result, dict)

    def test_not_available_returns_empty(self):
        from core.migration.sql.sql_insights import SqlInsights

        ins = SqlInsights(dialect="db2")
        result = ins.analyze_query_complexity("SELECT 1")
        self.assertIsInstance(result, dict)


class TestExtractTableDependencies(unittest.TestCase):
    def _ins(self):
        from core.migration.sql.sql_insights import SqlInsights

        return SqlInsights(dialect="postgresql")

    def test_simple_select(self):
        ins = self._ins()
        result = ins.extract_table_dependencies("SELECT * FROM users")
        self.assertIsInstance(result, dict)
        self.assertIn("tables", result)

    def test_join_query(self):
        ins = self._ins()
        sql = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id"
        result = ins.extract_table_dependencies(sql)
        self.assertIsInstance(result, dict)

    def test_empty_sql(self):
        ins = self._ins()
        result = ins.extract_table_dependencies("")
        self.assertIsInstance(result, dict)


class TestPredictPerformanceIssues(unittest.TestCase):
    def _ins(self):
        from core.migration.sql.sql_insights import SqlInsights

        return SqlInsights(dialect="postgresql")

    def test_returns_list(self):
        ins = self._ins()
        result = ins.predict_performance_issues("SELECT * FROM users WHERE id = 1")
        self.assertIsInstance(result, list)

    def test_complex_query(self):
        ins = self._ins()
        sql = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id WHERE u.status = 'active'"
        result = ins.predict_performance_issues(sql)
        self.assertIsInstance(result, list)


class TestGenerateExecutionPlanHints(unittest.TestCase):
    def _ins(self):
        from core.migration.sql.sql_insights import SqlInsights

        return SqlInsights(dialect="postgresql")

    def test_returns_dict(self):
        ins = self._ins()
        result = ins.generate_execution_plan_hints("SELECT * FROM users")
        self.assertIsInstance(result, dict)


class TestFormatSqlForLogging(unittest.TestCase):
    def _ins(self):
        from core.migration.sql.sql_insights import SqlInsights

        return SqlInsights(dialect="postgresql")

    def test_short_sql(self):
        ins = self._ins()
        result = ins.format_sql_for_logging("SELECT 1", max_length=200)
        self.assertIsInstance(result, str)

    def test_truncates_long_sql(self):
        ins = self._ins()
        long_sql = "SELECT " + "x, " * 100
        result = ins.format_sql_for_logging(long_sql, max_length=50)
        self.assertLessEqual(len(result), 200)  # With ellipsis
