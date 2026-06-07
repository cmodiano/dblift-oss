import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_handle_plan_forwards_cli_options(tmp_path):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.snapshot_model = "snapshot.json"
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="snapshot.json",
            skip_validate_sql=True,
            validate_scope="all",
            format="console",
            output=None,
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, actual = _handle_plan(ctx)

    assert success is True
    assert actual is result
    assert client.plan.call_args.kwargs["snapshot_model"] == Path("snapshot.json")
    assert "scripts_dir" not in client.plan.call_args.kwargs
    assert client.plan.call_args.kwargs["skip_validate_sql"] is True
    assert client.plan.call_args.kwargs["validate_scope"] == "all"


def test_handle_plan_forwards_dir_recursive_map_to_bound_client(tmp_path):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="snapshot.json",
            skip_validate_sql=True,
            validate_scope="all",
            format="console",
            output=None,
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
        dir_recursive_map={tmp_path: False},
    )

    success, actual = _handle_plan(ctx)

    assert success is True
    assert actual is result
    assert client.plan.call_args.kwargs["dir_recursive_map"] == {tmp_path: False}


def test_handle_plan_forwards_scripts_dir_to_offline_client(tmp_path):
    from cli.handlers._shared import CliCommandContext, ValidateSqlConfigClient
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.snapshot_model = "snapshot.json"
    result.complete()

    class OfflineClient(ValidateSqlConfigClient):
        def __init__(self):
            pass

        def plan(self, **kwargs):
            self.kwargs = kwargs
            return result

    client = OfflineClient()
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="console",
            output=None,
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=False,
        dir_recursive_map={tmp_path: False},
    )

    success, actual = _handle_plan(ctx)

    assert success is True
    assert actual is result
    assert client.kwargs["scripts_dir"] == tmp_path
    assert client.kwargs["dir_recursive_map"] == {tmp_path: False}


def test_handle_plan_requires_scripts_dir_for_offline_client():
    from cli.handlers._shared import CliCommandContext, ValidateSqlConfigClient
    from cli.handlers.plan import _handle_plan

    class OfflineClient(ValidateSqlConfigClient):
        def __init__(self):
            pass

    ctx = CliCommandContext(
        client=OfflineClient(),
        args=Namespace(
            snapshot_model="snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="console",
            output=None,
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=None,
        recursive=False,
    )

    with pytest.raises(ValueError, match="scripts directory is required for plan"):
        _handle_plan(ctx)


def test_handle_plan_writes_same_json_to_stdout_and_output(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.snapshot_model = "snapshot.json"
    result.already_applied_count = 1
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    output = tmp_path / "plan.json"
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=str(output),
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    assert success is True
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert stdout_payload["command"] == "plan"
    assert "findings" in stdout_payload


def test_handle_plan_writes_console_output_to_file(tmp_path):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.snapshot_model = "snapshot.json"
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    output = tmp_path / "plan.txt"
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="console",
            output=str(output),
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    assert success is True
    assert "Migration Plan Report" in output.read_text(encoding="utf-8")


def test_validate_sql_config_client_plan_delegates_to_plan_command(tmp_path):
    from cli.handlers._shared import ValidateSqlConfigClient

    scripts_dir = tmp_path / "migrations"
    scripts_dir.mkdir()
    (scripts_dir / "V2__users.sql").write_text("select 1;\n", encoding="utf-8")
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "metadata": {
                    "migration": {
                        "last_version": "1",
                        "applied_versions": ["1"],
                        "applied": [
                            {
                                "script": "V1__init.sql",
                                "version": "1",
                                "type": "SQL",
                                "success": True,
                            }
                        ],
                        "repeatables": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    config = Namespace(
        migrations=Namespace(script_encoding="utf-8", detect_encoding=False),
        database=Namespace(type="postgresql", schema="public"),
        validation=None,
    )

    result = ValidateSqlConfigClient(config).plan(
        scripts_dir=scripts_dir,
        snapshot_model=snapshot,
        skip_validate_sql=True,
    )

    assert result.success is True
    assert result.target_schema == "public"
    assert [migration.script for migration in result.pending_migrations] == ["V2__users.sql"]


def _pending_plan_result(tmp_path):
    from core.logger.results import PlanResult
    from core.migration.planning.models import PlannedMigration

    result = PlanResult()
    result.pending_migrations = [
        PlannedMigration(
            script="V2__users.sql",
            version="2",
            description="users",
            type="SQL",
            checksum=123,
            path=str(tmp_path / "V2__users.sql"),
        )
    ]
    result.complete()
    return result


def test_plan_github_actions_reports_pending_without_failing_at_error_threshold(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan

    client = MagicMock()
    client.plan.return_value = _pending_plan_result(tmp_path)
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="github-actions",
            output=None,
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    output = capsys.readouterr().out
    assert success is True
    assert "::notice" in output
    assert "Migration V2__users.sql is pending [plan.pending]" in output


def test_plan_fail_on_warning_ignores_pending_migration(tmp_path):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan

    client = MagicMock()
    client.plan.return_value = _pending_plan_result(tmp_path)
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="github-actions",
            output=None,
            fail_on="warning",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    assert success is True


def test_plan_json_success_matches_fail_on_warning_threshold(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan

    client = MagicMock()
    client.plan.return_value = _pending_plan_result(tmp_path)
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            fail_on="warning",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is True
    assert payload["fail_on"] == "warning"
    assert payload["summary"]["info"] == 1
    assert payload["findings"][0]["severity"] == "info"
    assert payload["success"] is True
    assert payload["metadata"]["success"] is True


def test_plan_console_status_matches_fail_on_warning_threshold(tmp_path):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan

    client = MagicMock()
    client.plan.return_value = _pending_plan_result(tmp_path)
    log = MagicMock()
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="console",
            output=None,
            fail_on="warning",
        ),
        log=log,
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, result = _handle_plan(ctx)

    rendered = log.info.call_args.args[0]
    assert success is True
    assert result.success is True
    assert "Status: SUCCESS" in rendered
    assert "Status: FAILED" not in rendered


def test_plan_json_error_message_is_error_finding(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.set_error("Plan operation failed: snapshot missing")
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="missing.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is False
    assert payload["success"] is False
    assert payload["summary"]["error"] == 1
    assert payload["findings"][0]["message"] == "Plan operation failed: snapshot missing"


def test_plan_runtime_error_fails_even_when_fail_on_never(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.set_error("Plan operation failed: snapshot missing")
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="missing.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            fail_on="never",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is False
    assert payload["success"] is False
    assert payload["findings"][0]["details"]["source"] == "runtime"


def test_handle_plan_writes_multi_format_artifacts_with_shared_timestamp(
    tmp_path, capsys, monkeypatch
):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.snapshot_model = "snapshot.json"
    result.complete()
    client = MagicMock()
    client.plan.return_value = result

    class FixedDateTime:
        @staticmethod
        def now(tz=None):
            from datetime import datetime, timezone

            return datetime(2026, 6, 1, 14, 35, 22, tzinfo=timezone.utc)

    monkeypatch.setattr("cli.handlers.report_outputs.datetime", FixedDateTime)
    output_dir = tmp_path / "reports"
    log = MagicMock()
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json,html,text",
            output=None,
            output_dir=str(output_dir),
            fail_on="error",
        ),
        log=log,
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)
    captured = capsys.readouterr()

    assert success is True
    assert json.loads(captured.out)["command"] == "plan"
    assert "Wrote plan reports" not in captured.out
    assert "Wrote plan reports" in captured.err
    log.info.assert_not_called()
    json_path = output_dir / "plan-report-20260601T143522Z.json"
    html_path = output_dir / "plan-report-20260601T143522Z.html"
    text_path = output_dir / "plan-report-20260601T143522Z.txt"
    assert json_path.exists()
    assert html_path.exists()
    assert text_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["command"] == "plan"
    assert "DBLift Plan Report" in html_path.read_text(encoding="utf-8")
    assert "Migration Plan Report" in text_path.read_text(encoding="utf-8")


def test_handle_plan_rejects_multi_format_without_output_dir(tmp_path):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json,html",
            output=None,
            output_dir=None,
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    with pytest.raises(ValueError, match="--output-dir is required"):
        _handle_plan(ctx)


def test_handle_plan_single_format_output_dir_creates_directory(tmp_path):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.snapshot_model = "snapshot.json"
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    output_dir = tmp_path / "missing" / "reports"
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="html",
            output=None,
            output_dir=str(output_dir),
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    assert success is True
    assert len(list(output_dir.glob("plan-report-*.html"))) == 1


def test_plan_single_json_without_output_still_writes_stdout_only(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.snapshot_model = "snapshot.json"
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    log = MagicMock()
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            output_dir=None,
            fail_on="error",
        ),
        log=log,
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is True
    assert payload["command"] == "plan"
    assert not log.info.called


def test_render_plan_text_does_not_import_html_renderer(monkeypatch):
    import builtins

    from cli.handlers.plan import _plan_result_to_finding_report, _render_plan_report
    from core.logger.results import PlanResult

    result = PlanResult()
    result.complete()
    finding_report = _plan_result_to_finding_report(result, "error")
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "core.reports.html":
            raise AssertionError("HTML renderer should not be imported for text output")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    rendered = _render_plan_report(
        result,
        finding_report,
        "text",
        "20260601T143522Z",
        [],
        MagicMock(format=lambda *_args: "text report"),
    )

    assert rendered == "text report"


def test_plan_error_message_keeps_runtime_source_when_duplicated(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.set_error("Plan operation failed: snapshot missing")
    result.plan_errors = ["Plan operation failed: snapshot missing"]
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="missing.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            fail_on="never",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is False
    assert payload["success"] is False
    assert len(payload["findings"]) == 1
    assert payload["findings"][0]["details"]["source"] == "runtime"


def test_plan_errors_obey_fail_on_never(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.plan_errors = ["Snapshot metadata is malformed"]
    result.refresh_success()
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            fail_on="never",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is True
    assert payload["success"] is True
    assert payload["findings"][0]["message"] == "Snapshot metadata is malformed"
    assert payload["findings"][0]["details"]["validation_source"] == "plan"


def test_plan_sql_validation_error_obeys_fail_on_never(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult
    from core.migration.planning.models import (
        SQL_VALIDATION_FAILURE_MESSAGE,
        SqlValidationSummary,
    )

    result = PlanResult()
    result.plan_errors = [SQL_VALIDATION_FAILURE_MESSAGE]
    result.sql_validation = SqlValidationSummary(
        enabled=True,
        scope="pending",
        status="FAIL",
        files_checked=1,
        errors=1,
        findings=[
            {
                "severity": "error",
                "code": "BUS001",
                "message": "Business rule violation",
                "file": str(tmp_path / "V1__rule.sql"),
                "line": 5,
                "details": {"source": "business_rule"},
            }
        ],
    )
    result.refresh_success()
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            fail_on="never",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is True
    assert payload["success"] is True
    assert [finding["code"] for finding in payload["findings"]] == ["BUS001"]


def test_plan_sql_validation_fallback_uses_aggregate_counts(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult
    from core.migration.planning.models import SqlValidationSummary

    result = PlanResult()
    result.sql_validation = SqlValidationSummary(
        enabled=True,
        scope="pending",
        status="FAIL",
        files_checked=2,
        errors=1,
        warnings=1,
        messages=["Missing index", "Syntax error"],
    )
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is False
    assert payload["summary"]["error"] == 1
    assert payload["summary"]["warning"] == 1
    assert payload["findings"][0]["severity"] == "error"
    assert payload["findings"][0]["message"] == "SQL validation reported 1 error"
    assert payload["findings"][1]["severity"] == "warning"
    assert payload["findings"][1]["message"] == "SQL validation reported 1 warning"
    assert payload["findings"][0]["details"]["messages"] == [
        "Missing index",
        "Syntax error",
    ]


def test_plan_sql_validation_preserves_message_severity(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult
    from core.migration.planning.models import SqlValidationSummary

    result = PlanResult()
    result.sql_validation = SqlValidationSummary(
        enabled=True,
        scope="pending",
        status="FAIL",
        files_checked=2,
        errors=1,
        warnings=1,
        messages=["Missing index", "Syntax error"],
        findings=[
            {
                "severity": "warning",
                "code": "PERF001",
                "message": "Missing index",
                "file": str(tmp_path / "V1__warn.sql"),
                "line": 3,
            },
            {
                "severity": "error",
                "code": "SYN001",
                "message": "Syntax error",
                "file": str(tmp_path / "V2__error.sql"),
                "line": 7,
                "details": {"source": "syntax"},
            },
        ],
    )
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            fail_on="never",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is True
    assert payload["success"] is True
    assert payload["summary"]["error"] == 1
    assert payload["summary"]["warning"] == 1
    assert payload["findings"][0]["severity"] == "warning"
    assert payload["findings"][1]["severity"] == "error"
    assert payload["findings"][1]["details"]["source"] == "syntax"


def test_plan_sql_validation_source_cannot_bypass_fail_on_never(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult
    from core.migration.planning.models import SqlValidationSummary

    result = PlanResult()
    result.sql_validation = SqlValidationSummary(
        enabled=True,
        scope="pending",
        status="FAIL",
        files_checked=1,
        errors=1,
        findings=[
            {
                "severity": "error",
                "code": "SQL001",
                "message": "Validation rule reused a reserved source",
                "file": str(tmp_path / "V1__rule.sql"),
                "details": {"source": "plan"},
            }
        ],
    )
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            fail_on="never",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is True
    assert payload["success"] is True
    assert payload["findings"][0]["details"]["source"] == "plan"


def test_plan_sql_validation_preserves_always_fail_source_details(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult
    from core.migration.planning.models import SqlValidationSummary

    result = PlanResult()
    result.sql_validation = SqlValidationSummary(
        enabled=True,
        scope="pending",
        status="FAIL",
        files_checked=1,
        errors=1,
        findings=[
            {
                "severity": "error",
                "code": "SQL001",
                "message": "Validation source should be preserved",
                "file": str(tmp_path / "V1__rule.sql"),
                "details": {"source": "runtime"},
            }
        ],
    )
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            fail_on="never",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is True
    assert payload["success"] is True
    assert payload["findings"][0]["details"]["source"] == "runtime"


def test_plan_sql_validation_details_cannot_set_blocking(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult
    from core.migration.planning.models import SqlValidationSummary

    result = PlanResult()
    result.sql_validation = SqlValidationSummary(
        enabled=True,
        scope="pending",
        status="FAIL",
        files_checked=1,
        errors=1,
        findings=[
            {
                "severity": "error",
                "code": "SQL001",
                "message": "Validation rule attempted to set blocking",
                "file": str(tmp_path / "V1__rule.sql"),
                "details": {"blocking": True, "source": "runtime"},
            }
        ],
    )
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            fail_on="never",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is True
    assert payload["success"] is True
    assert payload["findings"][0]["details"]["source"] == "runtime"
    assert "blocking" not in payload["findings"][0]["details"]


def test_plan_sql_validation_config_error_keeps_blocking(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult
    from core.migration.planning.models import SqlValidationSummary

    result = PlanResult()
    result.sql_validation = SqlValidationSummary(
        enabled=True,
        scope="pending",
        status="FAIL",
        files_checked=0,
        errors=1,
        findings=[
            {
                "severity": "error",
                "code": "validate-sql.config",
                "message": "No files specified",
                "details": {"blocking": True, "source": "runtime"},
            }
        ],
    )
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            fail_on="never",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is False
    assert payload["success"] is False
    assert payload["findings"][0]["details"] == {"blocking": True, "source": "runtime"}


def test_plan_checksum_drift_fails_when_threshold_is_never(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult
    from core.migration.planning.models import ChecksumDrift

    result = PlanResult()
    result.checksum_drift = [
        ChecksumDrift(
            script="V1__init.sql",
            version="1",
            expected_checksum=111,
            actual_checksum=222,
        )
    ]
    result.refresh_success()
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=False,
            validate_scope="pending",
            format="json",
            output=None,
            fail_on="never",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is False
    assert payload["success"] is False
    assert payload["summary"]["error"] == 1
    assert payload["findings"][0]["severity"] == "error"
    assert payload["findings"][0]["details"]["source"] == "checksum_drift"
    assert payload["findings"][0]["details"]["blocking"] is True


def test_plan_html_without_output_writes_stdout_not_log(tmp_path, capsys):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.plan import _handle_plan
    from core.logger.results import PlanResult

    result = PlanResult()
    result.complete()
    client = MagicMock()
    client.plan.return_value = result
    log = MagicMock()
    ctx = CliCommandContext(
        client=client,
        args=Namespace(
            snapshot_model="env.snapshot.json",
            skip_validate_sql=True,
            validate_scope="pending",
            format="html",
            output=None,
            fail_on="error",
        ),
        log=log,
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_plan(ctx)

    assert success is True
    stdout = capsys.readouterr().out
    assert "<html" in stdout.lower()
    assert not log.info.called
