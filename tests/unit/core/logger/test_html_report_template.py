from core.logger.formatters.htmlformatter import HtmlFormatter
from core.logger.results import MigrateResult, MigrationInfo


class _Journal:
    def get_migration_performance_summary(self, migration_id):
        return {
            "version": "1",
            "description": "init",
            "statements": [
                {
                    "statement": "CREATE TABLE demo (id int);",
                    "execution_time": 12,
                    "success": True,
                }
            ],
            "total_execution_time": 12,
        }

    def get_performance_stats_by_object_type(self, migration_id):
        return {}


def test_migrate_html_journal_includes_sql_with_show_sql():
    result = MigrateResult()
    result.show_sql = True
    result.migrations.append(
        MigrationInfo(
            script="V1__init.sql",
            version="1",
            description="init",
            status="SUCCESS",
            execution_time=12,
        )
    )
    result.journal = _Journal()
    result.complete()

    html = HtmlFormatter().format_result(result, "public", "demo", "MIGRATE")

    assert "CREATE TABLE demo (id int);" in html
    assert 'data-sql="CREATE TABLE demo (id int);"' in html


def test_migrate_html_journal_hides_sql_without_show_sql():
    result = MigrateResult()
    result.show_sql = False
    result.migrations.append(
        MigrationInfo(
            script="V1__init.sql",
            version="1",
            description="init",
            status="SUCCESS",
            execution_time=12,
        )
    )
    result.journal = _Journal()
    result.complete()

    html = HtmlFormatter().format_result(result, "public", "demo", "MIGRATE")

    assert "CREATE TABLE demo (id int);" not in html
