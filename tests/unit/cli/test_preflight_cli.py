import json
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_handler_emits_json_report(tmp_path, capsys, monkeypatch):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.preflight import _handle_preflight
    from core.preflight.models import PreflightPhase, PreflightResult

    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="error",
        phases=[PreflightPhase(name="plan", status="PASS")],
    )

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self, **kwargs):
            return result

    monkeypatch.setattr("cli.handlers.preflight.PreflightOrchestrator", FakeOrchestrator)
    ctx = CliCommandContext(
        client=MagicMock(),
        args=Namespace(
            snapshot_model="env.snapshot.json",
            container_image=None,
            container_existing=None,
            container_name=None,
            container_env=[],
            container_port=[],
            container_wait_timeout=120,
            keep_container=False,
            skip_replay=True,
            replay_scope="all",
            format="json",
            output=None,
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, actual = _handle_preflight(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is True
    assert actual is result
    assert payload["command"] == "preflight"
    assert payload["metadata"]["snapshot_model"] == "env.snapshot.json"


def test_handler_success_logging_matches_threshold_exit_code(tmp_path, monkeypatch):
    """All phases PASS but a plan warning + --fail-on warning must fail the
    command; the logged success must agree with the returned exit code."""
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.preflight import _handle_preflight
    from core.preflight.models import PreflightPhase, PreflightResult

    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="warning",
        phases=[PreflightPhase(name="plan", status="PASS")],
        plan_result=SimpleNamespace(
            sql_validation=SimpleNamespace(
                findings=[{"severity": "warning", "code": "sql.x", "message": "warned"}]
            )
        ),
    )

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return result

    monkeypatch.setattr("cli.handlers.preflight.PreflightOrchestrator", FakeOrchestrator)
    log = MagicMock()
    ctx = CliCommandContext(
        client=MagicMock(),
        args=Namespace(
            snapshot_model="env.snapshot.json",
            container_image=None,
            container_existing=None,
            container_name=None,
            container_env=[],
            container_port=[],
            container_wait_timeout=120,
            keep_container=False,
            skip_replay=True,
            replay_scope="all",
            format="console",
            output=None,
            fail_on="warning",
        ),
        log=log,
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, actual = _handle_preflight(ctx)

    assert success is False
    assert actual.success is False
    log.set_command_completed.assert_called_once()
    assert log.set_command_completed.call_args.kwargs["success"] is False


def test_handler_console_output_explains_threshold_failure(tmp_path, monkeypatch):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.preflight import _handle_preflight
    from core.preflight.models import PreflightPhase, PreflightResult

    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="warning",
        phases=[PreflightPhase(name="plan", status="PASS")],
        plan_result=SimpleNamespace(
            sql_validation=SimpleNamespace(
                findings=[{"severity": "warning", "code": "sql.x", "message": "warned"}]
            )
        ),
    )

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return result

    monkeypatch.setattr("cli.handlers.preflight.PreflightOrchestrator", FakeOrchestrator)
    log = MagicMock()
    ctx = CliCommandContext(
        client=MagicMock(),
        args=Namespace(
            snapshot_model="env.snapshot.json",
            container_image=None,
            container_existing=None,
            container_name=None,
            container_env=[],
            container_port=[],
            container_wait_timeout=120,
            keep_container=False,
            skip_replay=True,
            replay_scope="all",
            format="console",
            output=None,
            fail_on="warning",
        ),
        log=log,
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_preflight(ctx)

    rendered = log.info.call_args.args[0]
    assert success is False
    assert "Status: FAILED" in rendered
    assert "- plan: PASS" in rendered
    assert "Failure Threshold:" in rendered
    assert "- WARNING [sql.x]: inline: warned" in rendered


def test_handler_html_without_output_writes_stdout_not_log(tmp_path, capsys, monkeypatch):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.preflight import _handle_preflight
    from core.preflight.models import PreflightPhase, PreflightResult

    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="error",
        phases=[PreflightPhase(name="plan", status="PASS")],
    )

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return result

    monkeypatch.setattr("cli.handlers.preflight.PreflightOrchestrator", FakeOrchestrator)
    log = MagicMock()
    ctx = CliCommandContext(
        client=MagicMock(),
        args=Namespace(
            snapshot_model="env.snapshot.json",
            container_image=None,
            container_existing=None,
            container_name=None,
            container_env=[],
            container_port=[],
            container_wait_timeout=120,
            keep_container=False,
            skip_replay=True,
            replay_scope="all",
            format="html",
            output=None,
            fail_on="error",
        ),
        log=log,
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_preflight(ctx)

    assert success is True
    stdout = capsys.readouterr().out
    assert "<!doctype html>" in stdout.lower()
    assert not log.info.called


def test_handler_console_output_summarizes_preflight_phases(tmp_path, monkeypatch):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.preflight import _handle_preflight
    from core.preflight.models import PreflightPhase, PreflightResult

    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="error",
        phases=[
            PreflightPhase(name="plan", status="PASS", message="Plan ready"),
            PreflightPhase(
                name="replay",
                status="PASS",
                message="Replay completed",
                metadata={"container": "dblift-preflight"},
            ),
        ],
        replayed_scripts=["V1__init.sql"],
    )

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return result

    monkeypatch.setattr("cli.handlers.preflight.PreflightOrchestrator", FakeOrchestrator)
    log = MagicMock()
    ctx = CliCommandContext(
        client=MagicMock(),
        args=Namespace(
            snapshot_model="env.snapshot.json",
            container_image=None,
            container_existing=None,
            container_name=None,
            container_env=[],
            container_port=[],
            container_wait_timeout=120,
            keep_container=False,
            skip_replay=True,
            replay_scope="all",
            format="console",
            output=None,
            fail_on="error",
        ),
        log=log,
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_preflight(ctx)

    rendered = log.info.call_args.args[0]
    assert success is True
    assert "Preflight Report" in rendered
    assert "Phases:" in rendered
    assert "- replay: PASS - Replay completed" in rendered
    assert "Replayed Scripts:" in rendered
    assert "preflight findings" not in rendered


def test_handler_json_metadata_success_matches_threshold(tmp_path, capsys, monkeypatch):
    """report.metadata snapshots result.to_dict() before the override is set;
    the handler must patch metadata['success'] so JSON output agrees with the
    threshold-based top-level success."""
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.preflight import _handle_preflight
    from core.preflight.models import PreflightPhase, PreflightResult

    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="warning",
        phases=[PreflightPhase(name="plan", status="PASS")],
        plan_result=SimpleNamespace(
            sql_validation=SimpleNamespace(
                findings=[{"severity": "warning", "code": "sql.x", "message": "warned"}]
            )
        ),
    )

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return result

    monkeypatch.setattr("cli.handlers.preflight.PreflightOrchestrator", FakeOrchestrator)
    ctx = CliCommandContext(
        client=MagicMock(),
        args=Namespace(
            snapshot_model="env.snapshot.json",
            container_image=None,
            container_existing=None,
            container_name=None,
            container_env=[],
            container_port=[],
            container_wait_timeout=120,
            keep_container=False,
            skip_replay=True,
            replay_scope="all",
            format="json",
            output=None,
            fail_on="warning",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_preflight(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is False
    assert payload["success"] is False
    assert payload["metadata"]["success"] is False


def test_handler_preflight_imports_full_plan_findings(tmp_path, capsys, monkeypatch):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.preflight import _handle_preflight
    from core.logger.results import PlanResult
    from core.migration.planning.models import PlannedMigration
    from core.preflight.models import PreflightPhase, PreflightResult

    plan_result = PlanResult()
    plan_result.pending_migrations = [
        PlannedMigration(
            script="V2__users.sql",
            version="2",
            description="users",
            type="SQL",
            checksum=123,
            path=str(tmp_path / "V2__users.sql"),
        )
    ]
    plan_result.complete()
    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="info",
        phases=[PreflightPhase(name="plan", status="PASS")],
        plan_result=plan_result,
    )

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return result

    monkeypatch.setattr("cli.handlers.preflight.PreflightOrchestrator", FakeOrchestrator)
    ctx = CliCommandContext(
        client=MagicMock(),
        args=Namespace(
            snapshot_model="env.snapshot.json",
            container_image=None,
            container_existing=None,
            container_name=None,
            container_env=[],
            container_port=[],
            container_wait_timeout=120,
            keep_container=False,
            skip_replay=True,
            replay_scope="all",
            format="json",
            output=None,
            fail_on="info",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_preflight(ctx)

    payload = json.loads(capsys.readouterr().out)
    assert success is False
    assert payload["findings"][0]["code"] == "plan.pending"


def test_handle_preflight_writes_multi_format_artifacts_with_shared_timestamp(
    tmp_path, capsys, monkeypatch
):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.preflight import _handle_preflight
    from core.preflight.models import PreflightPhase, PreflightResult

    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="error",
        phases=[PreflightPhase(name="plan", status="PASS")],
        replayed_scripts=["V2__users.sql"],
    )

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return result

    class FixedDateTime:
        @staticmethod
        def now(tz=None):
            from datetime import datetime, timezone

            return datetime(2026, 6, 1, 14, 35, 22, tzinfo=timezone.utc)

    monkeypatch.setattr("cli.handlers.preflight.PreflightOrchestrator", FakeOrchestrator)
    monkeypatch.setattr("cli.handlers.report_outputs.datetime", FixedDateTime)
    output_dir = tmp_path / "reports"
    log = MagicMock()
    ctx = CliCommandContext(
        client=MagicMock(),
        args=Namespace(
            snapshot_model="env.snapshot.json",
            container_image=None,
            container_existing=None,
            container_name=None,
            container_env=[],
            container_port=[],
            container_wait_timeout=120,
            keep_container=False,
            skip_replay=True,
            replay_scope="all",
            rehearse_rollback=False,
            format="json,html,text",
            output=None,
            output_dir=str(output_dir),
            fail_on="error",
        ),
        log=log,
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_preflight(ctx)
    captured = capsys.readouterr()

    assert success is True
    assert json.loads(captured.out)["command"] == "preflight"
    assert "Wrote preflight reports" not in captured.out
    assert "Wrote preflight reports" in captured.err
    log.info.assert_not_called()
    json_path = output_dir / "preflight-report-20260601T143522Z.json"
    html_path = output_dir / "preflight-report-20260601T143522Z.html"
    text_path = output_dir / "preflight-report-20260601T143522Z.txt"
    assert json_path.exists()
    assert html_path.exists()
    assert text_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["command"] == "preflight"
    assert "DBLift Preflight Report" in html_path.read_text(encoding="utf-8")
    assert "Preflight Report" in text_path.read_text(encoding="utf-8")


def test_handle_preflight_rejects_output_file_with_multiple_formats(tmp_path, monkeypatch):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.preflight import _handle_preflight
    from core.preflight.models import PreflightResult

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return PreflightResult(snapshot_model="env.snapshot.json", fail_on="error")

    monkeypatch.setattr("cli.handlers.preflight.PreflightOrchestrator", FakeOrchestrator)
    ctx = CliCommandContext(
        client=MagicMock(),
        args=Namespace(
            snapshot_model="env.snapshot.json",
            container_image=None,
            container_existing=None,
            container_name=None,
            container_env=[],
            container_port=[],
            container_wait_timeout=120,
            keep_container=False,
            skip_replay=True,
            replay_scope="all",
            rehearse_rollback=False,
            format="json,html",
            output=str(tmp_path / "preflight.json"),
            output_dir=str(tmp_path),
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    with pytest.raises(ValueError, match="--output cannot be used with multiple formats"):
        _handle_preflight(ctx)


def test_handle_preflight_single_format_output_dir_creates_directory(tmp_path, monkeypatch):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.preflight import _handle_preflight
    from core.preflight.models import PreflightResult

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return PreflightResult(snapshot_model="env.snapshot.json", fail_on="error")

    monkeypatch.setattr("cli.handlers.preflight.PreflightOrchestrator", FakeOrchestrator)
    output_dir = tmp_path / "missing" / "reports"
    ctx = CliCommandContext(
        client=MagicMock(),
        args=Namespace(
            snapshot_model="env.snapshot.json",
            container_image=None,
            container_existing=None,
            container_name=None,
            container_env=[],
            container_port=[],
            container_wait_timeout=120,
            keep_container=False,
            skip_replay=True,
            replay_scope="all",
            rehearse_rollback=False,
            format="html",
            output=None,
            output_dir=str(output_dir),
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_preflight(ctx)

    assert success is True
    assert len(list(output_dir.glob("preflight-report-*.html"))) == 1


def test_preflight_single_github_actions_still_writes_annotations(tmp_path, capsys, monkeypatch):
    from cli.handlers._shared import CliCommandContext
    from cli.handlers.preflight import _handle_preflight
    from core.logger.results import PlanResult
    from core.migration.planning.models import PlannedMigration
    from core.preflight.models import PreflightPhase, PreflightResult

    plan_result = PlanResult()
    plan_result.pending_migrations = [
        PlannedMigration(
            "V2__users.sql",
            "2",
            "users",
            "SQL",
            123,
            str(tmp_path / "V2__users.sql"),
        )
    ]
    plan_result.complete()
    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="error",
        phases=[PreflightPhase(name="plan", status="PASS")],
        plan_result=plan_result,
    )

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return result

    monkeypatch.setattr("cli.handlers.preflight.PreflightOrchestrator", FakeOrchestrator)
    ctx = CliCommandContext(
        client=MagicMock(),
        args=Namespace(
            snapshot_model="env.snapshot.json",
            container_image=None,
            container_existing=None,
            container_name=None,
            container_env=[],
            container_port=[],
            container_wait_timeout=120,
            keep_container=False,
            skip_replay=True,
            replay_scope="all",
            rehearse_rollback=False,
            format="github-actions",
            output=None,
            output_dir=None,
            fail_on="error",
        ),
        log=MagicMock(),
        scripts_dir=tmp_path,
        recursive=True,
    )

    success, _ = _handle_preflight(ctx)

    output = capsys.readouterr().out
    assert success is True
    assert "::notice" in output
    assert "Migration V2__users.sql is pending [plan.pending]" in output
