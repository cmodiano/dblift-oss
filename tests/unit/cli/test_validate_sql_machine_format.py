"""Regression tests for validate-sql machine-format stdout contract.

The machine-format (`--format json`, sarif, etc.) stdout is a parser-facing
contract (see `cli/_constants.py:MACHINE_READABLE_FORMATS` and
ADR-0005/0008). Every terminal branch of `_handle_validate_sql` must emit
a parseable payload on stdout when `is_machine_format=True`, otherwise
downstream consumers (`jq`, CI reporters, IDE integrations) get empty
input and fail.

Cursor bot report:
  "Machine-format validate-sql emits empty stdout when no files found"
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cli._command_handlers import CliCommandContext, _handle_validate_sql
from cli._output import CommandOutput


def _make_ctx(
    *,
    files=None,
    scripts_dir=None,
    fmt="json",
    fail_on="error",
    rule_profile=None,
    rules=None,
    stdout_sink=None,
):
    args = SimpleNamespace(
        files=files,
        dialect="postgresql",
        format=fmt,
        output=None,
        rules_file=None,
        rule_profile=rule_profile,
        rules=rules,
        fail_on=fail_on,
        severity_threshold=None,
        no_performance=False,
    )
    client = MagicMock()
    client.config = MagicMock(database=SimpleNamespace(type="postgresql"), validation=None)
    log = MagicMock()
    ctx = CliCommandContext(client=client, args=args, log=log, scripts_dir=scripts_dir)
    return ctx


def _capture_stdout(monkeypatch):
    sink = io.StringIO()
    monkeypatch.setattr("sys.stdout", sink)
    return sink


def _cli_with_stub_license(tmp_path, *args):
    runner = tmp_path / "_run_cli.py"
    runner.write_text(
        textwrap.dedent("""
            from cli.main import main

            main()
            """),
        encoding="utf-8",
    )
    return [sys.executable, str(runner), *args]


class TestValidateSqlMachineFormatStdoutContract:
    """Every terminal branch must emit parseable JSON on stdout in machine mode."""

    def test_empty_directory_emits_valid_json_with_zero_files(self, tmp_path, monkeypatch):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        ctx = _make_ctx(scripts_dir=empty_dir)

        sink = _capture_stdout(monkeypatch)
        success, result = _handle_validate_sql(ctx)

        stdout = sink.getvalue().strip()
        assert stdout, "machine-format must never emit empty stdout"
        payload = json.loads(stdout)
        assert payload["success"] is True
        assert payload["checked_count"] == 0
        assert success is True

    def test_missing_files_arg_and_no_scripts_dir_emits_error_payload(self, monkeypatch):
        ctx = _make_ctx(scripts_dir=None)

        sink = _capture_stdout(monkeypatch)
        success, result = _handle_validate_sql(ctx)

        stdout = sink.getvalue().strip()
        assert stdout, "machine-format must never emit empty stdout on config errors"
        payload = json.loads(stdout)
        assert payload["success"] is False
        assert payload["command"] == "validate-sql"
        assert payload["checked_count"] == 0
        assert payload["summary"] == {"error": 1, "warning": 0, "info": 0}
        assert payload["findings"][0]["code"] == "validate-sql.config"
        assert payload["findings"][0]["details"]["blocking"] is True
        assert payload["findings"][0]["details"]["source"] == "runtime"
        assert "No files specified" in payload["findings"][0]["message"]
        assert success is False

    def test_human_format_no_files_does_not_write_json(self, tmp_path, monkeypatch):
        """Sanity: human mode keeps its log-based output, does not emit JSON."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        ctx = _make_ctx(scripts_dir=empty_dir, fmt="console")

        sink = _capture_stdout(monkeypatch)
        success, _ = _handle_validate_sql(ctx)

        assert success is True
        ctx.log.warning.assert_called()

    def test_validate_sql_html_without_output_writes_human_log(self, tmp_path):
        sql_file = tmp_path / "V1__bad.sql"
        sql_file.write_text("UPDATE users SET name = name;\n", encoding="utf-8")
        ctx = _make_ctx(files=[str(sql_file)], fmt="html", fail_on="warning")

        success, _ = _handle_validate_sql(ctx)

        assert success is False
        logged = "\n".join(str(call.args[0]) for call in ctx.log.info.call_args_list)
        assert "<!doctype html>" in logged.lower()
        assert "Validate Sql Report" in logged

    def test_validate_sql_html_output_writes_file(self, tmp_path):
        sql_file = tmp_path / "V1__bad.sql"
        sql_file.write_text("UPDATE users SET name = name;\n", encoding="utf-8")
        output = tmp_path / "sql-evidence.html"
        ctx = _make_ctx(files=[str(sql_file)], fmt="html", fail_on="warning")
        ctx.args.output = str(output)

        success, _ = _handle_validate_sql(ctx)

        assert success is False
        assert output.read_text(encoding="utf-8").startswith("<!doctype html>")

    def test_validate_sql_html_output_does_not_log_raw_html(self, tmp_path):
        sql_file = tmp_path / "V1__bad.sql"
        sql_file.write_text("UPDATE users SET name = name;\n", encoding="utf-8")
        output = tmp_path / "sql-evidence.html"
        ctx = _make_ctx(files=[str(sql_file)], fmt="html", fail_on="warning")
        ctx.args.output = str(output)

        success, _ = _handle_validate_sql(ctx)

        assert success is False
        assert output.read_text(encoding="utf-8").startswith("<!doctype html>")
        logged = "\n".join(str(call.args[0]) for call in ctx.log.info.call_args_list)
        assert "<!doctype html>" not in logged.lower()

    def test_validate_sql_uses_configured_html_format_without_cli_override(self, tmp_path):
        from config.validation_config import ValidationConfig

        sql_file = tmp_path / "V1__bad.sql"
        sql_file.write_text("UPDATE users SET name = name;\n", encoding="utf-8")
        ctx = _make_ctx(files=[str(sql_file)], fmt=None, fail_on="warning")
        ctx.client.config.validation = ValidationConfig(output_format="html", fail_on="warning")

        success, _ = _handle_validate_sql(ctx)

        assert success is False
        logged = "\n".join(str(call.args[0]) for call in ctx.log.info.call_args_list)
        assert "<!doctype html>" in logged.lower()

    def test_json_success_matches_fail_on_warning_threshold(self, tmp_path, monkeypatch):
        sql_file = tmp_path / "V1__bad.sql"
        sql_file.write_text("UPDATE users SET name = name;\n", encoding="utf-8")
        ctx = _make_ctx(files=[str(sql_file)], fail_on="warning")

        sink = _capture_stdout(monkeypatch)
        success, _ = _handle_validate_sql(ctx)

        payload = json.loads(sink.getvalue())
        assert success is False
        assert payload["fail_on"] == "warning"
        assert payload["summary"]["warning"] == 1
        assert payload["success"] is False

    def test_gitlab_format_emits_code_quality_array(self, tmp_path, monkeypatch):
        sql_file = tmp_path / "V1__bad.sql"
        sql_file.write_text("UPDATE users SET name = name;\n", encoding="utf-8")
        ctx = _make_ctx(files=[str(sql_file)], fmt="gitlab", fail_on="warning")

        sink = _capture_stdout(monkeypatch)
        success, _ = _handle_validate_sql(ctx)

        payload = json.loads(sink.getvalue())
        assert success is False
        assert isinstance(payload, list)
        assert payload[0]["check_name"] == "missing_where_clause"
        assert payload[0]["severity"] == "minor"
        assert payload[0]["location"]["path"] == str(sql_file)

    def test_config_fail_on_used_when_cli_flag_is_absent(self, tmp_path, monkeypatch):
        from config.validation_config import ValidationConfig

        sql_file = tmp_path / "V1__bad.sql"
        sql_file.write_text("UPDATE users SET name = name;\n", encoding="utf-8")
        ctx = _make_ctx(files=[str(sql_file)], fail_on=None)
        ctx.client.config.validation = ValidationConfig(fail_on="warning")

        sink = _capture_stdout(monkeypatch)
        success, _ = _handle_validate_sql(ctx)

        payload = json.loads(sink.getvalue())
        assert success is False
        assert payload["fail_on"] == "warning"
        assert payload["summary"]["warning"] == 1
        assert payload["success"] is False

    def test_rule_profile_applies_builtin_rules(self, tmp_path, monkeypatch):
        sql_file = tmp_path / "V1__grant_all.sql"
        sql_file.write_text(
            "GRANT ALL PRIVILEGES ON users TO app_user;\n",
            encoding="utf-8",
        )
        ctx = _make_ctx(files=[str(sql_file)], fail_on="error", rule_profile="core")

        sink = _capture_stdout(monkeypatch)
        success, result = _handle_validate_sql(ctx)

        payload = json.loads(sink.getvalue())
        assert success is False
        assert payload["success"] is False
        assert any(v.rule_id == "no_grant_all_privileges" for v in result.violations)

    def test_cli_rule_selection_applies_selected_rule(self, tmp_path, monkeypatch):
        sql_file = tmp_path / "V1__drop_without_backup.sql"
        sql_file.write_text("DROP TABLE users;\n", encoding="utf-8")
        ctx = _make_ctx(
            files=[str(sql_file)],
            fail_on="warning",
            rules=[["no_drop_without_backup"]],
        )

        sink = _capture_stdout(monkeypatch)
        success, result = _handle_validate_sql(ctx)

        payload = json.loads(sink.getvalue())
        assert success is False
        assert payload["success"] is False
        assert any(v.rule_id == "no_drop_without_backup" for v in result.violations)

    def test_machine_format_rule_config_error_emits_json_payload(self, monkeypatch):
        ctx = _make_ctx(files=["migrations"], rule_profile="core")
        ctx.args.rules_file = "custom-rules.yaml"

        sink = _capture_stdout(monkeypatch)
        success, result = _handle_validate_sql(ctx)

        payload = json.loads(sink.getvalue())
        assert success is False
        assert result is None
        assert payload["success"] is False
        assert payload["command"] == "validate-sql"
        assert payload["checked_count"] == 0
        assert payload["summary"] == {"error": 1, "warning": 0, "info": 0}
        assert payload["findings"][0]["code"] == "validate-sql.config"
        assert payload["findings"][0]["details"]["blocking"] is True
        assert payload["findings"][0]["details"]["source"] == "runtime"
        assert (
            "--rules-file cannot be combined with --profile or --rules"
            in payload["findings"][0]["message"]
        )

    def test_configured_machine_format_config_error_emits_json_payload(self, monkeypatch):
        from config.validation_config import ValidationConfig

        ctx = _make_ctx(files=["migrations"], fmt=None, rule_profile="core")
        ctx.args.rules_file = "custom-rules.yaml"
        ctx.client.config.validation = ValidationConfig(output_format="json")

        sink = _capture_stdout(monkeypatch)
        success, result = _handle_validate_sql(ctx)

        payload = json.loads(sink.getvalue())
        assert success is False
        assert result is None
        assert payload["success"] is False
        assert payload["command"] == "validate-sql"
        assert payload["findings"][0]["code"] == "validate-sql.config"
        assert (
            "--rules-file cannot be combined with --profile or --rules"
            in payload["findings"][0]["message"]
        )

    def test_machine_format_unknown_profile_emits_json_payload(self, monkeypatch):
        ctx = _make_ctx(files=["migrations"], rule_profile="missing")

        sink = _capture_stdout(monkeypatch)
        success, result = _handle_validate_sql(ctx)

        payload = json.loads(sink.getvalue())
        assert success is False
        assert result is None
        assert payload["success"] is False
        assert payload["command"] == "validate-sql"
        assert payload["findings"][0]["code"] == "validate-sql.config"
        assert "Unknown rule profile 'missing'" in payload["findings"][0]["message"]

    def test_machine_format_conflicting_config_rule_sources_emits_json_payload(self, monkeypatch):
        from config.validation_config import ValidationConfig

        ctx = _make_ctx(files=["migrations"])
        ctx.client.config.validation = ValidationConfig(rules_file="custom-rules.yaml")
        ctx.client.config.validation.rule_profile = "core"

        sink = _capture_stdout(monkeypatch)
        success, result = _handle_validate_sql(ctx)

        payload = json.loads(sink.getvalue())
        assert success is False
        assert result is None
        assert payload["success"] is False
        assert payload["command"] == "validate-sql"
        assert payload["findings"][0]["code"] == "validate-sql.config"
        assert (
            "--rules-file cannot be combined with --profile or --rules"
            in payload["findings"][0]["message"]
        )

    def test_build_validation_config_accepts_profile_and_rules(self):
        from cli.handlers.validate_sql import _build_validation_config

        ctx = _make_ctx(rule_profile="enterprise", rules=[["security,performance"]])

        validation_config = _build_validation_config(ctx)

        assert validation_config.rule_profile == "enterprise"
        assert validation_config.rules == ["security", "performance"]
        assert validation_config.rules_file is None

    def test_build_validation_config_rejects_rules_file_with_profile(self):
        from cli.handlers.validate_sql import _build_validation_config

        ctx = _make_ctx(rule_profile="core")
        ctx.args.rules_file = "custom-rules.yaml"

        with pytest.raises(ValueError, match="--rules-file cannot be combined"):
            _build_validation_config(ctx)

    def test_cli_rules_clears_config_rule_profile(self):
        from cli.handlers.validate_sql import _build_validation_config
        from config.validation_config import ValidationConfig

        ctx = _make_ctx(rules=[["no_grant_all_privileges"]])
        ctx.client.config.validation = ValidationConfig(rule_profile="enterprise")

        validation_config = _build_validation_config(ctx)

        assert validation_config.rule_profile is None
        assert validation_config.rules == ["no_grant_all_privileges"]
        assert validation_config.rules_file is None

    def test_cli_profile_clears_config_rules(self):
        from cli.handlers.validate_sql import _build_validation_config
        from config.validation_config import ValidationConfig

        ctx = _make_ctx(rule_profile="core")
        ctx.client.config.validation = ValidationConfig(rules=["no_grant_all_privileges"])

        validation_config = _build_validation_config(ctx)

        assert validation_config.rule_profile == "core"
        assert validation_config.rules == []
        assert validation_config.rules_file is None

    def test_syntax_violation_obeys_fail_on_never(self, tmp_path, monkeypatch):
        from core.sql_validator.linting.models import (
            ValidationResult,
            ValidationViolation,
            ViolationSeverity,
            ViolationSource,
        )
        from core.sql_validator.linting.sql_validator import SqlValidator

        sql_file = tmp_path / "V1__bad.sql"
        sql_file.write_text("SELECT * FROM ;\n", encoding="utf-8")
        result = ValidationResult(files_checked=1)
        result.add_violation(
            ValidationViolation(
                rule_id="parse_error",
                severity=ViolationSeverity.ERROR,
                message="Error tokenizing",
                source=ViolationSource.SYNTAX,
            )
        )
        monkeypatch.setattr(SqlValidator, "validate_files", lambda self, files: result)
        ctx = _make_ctx(files=[str(sql_file)], fail_on="never")

        sink = _capture_stdout(monkeypatch)
        success, _ = _handle_validate_sql(ctx)

        payload = json.loads(sink.getvalue())
        assert success is True
        assert payload["fail_on"] == "never"
        assert payload["success"] is True

    def test_machine_output_file_creates_parent_directory(self, tmp_path, monkeypatch):
        sql_file = tmp_path / "V1__bad.sql"
        sql_file.write_text("UPDATE users SET name = name;\n", encoding="utf-8")
        output = tmp_path / "reports" / "validation.json"
        ctx = _make_ctx(files=[str(sql_file)], fail_on="warning")
        ctx.args.output = str(output)

        sink = _capture_stdout(monkeypatch)
        success, _ = _handle_validate_sql(ctx)

        assert success is False
        assert output.exists()
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["command"] == "validate-sql"
        assert payload["success"] is False
        assert json.loads(sink.getvalue())["command"] == "validate-sql"

    def test_configured_machine_format_routes_top_level_output(self):
        from cli.main import _apply_validate_sql_configured_output_format, _CliContext
        from config.validation_config import ValidationConfig

        args = SimpleNamespace(command="validate-sql", format=None)
        config = SimpleNamespace(validation=ValidationConfig(output_format="json"))
        ctx = _CliContext(
            commands=["validate-sql"],
            global_arguments=[],
            subcommand_args=[],
            args=args,
            parser=None,
            log=None,
            config=config,
        )

        _apply_validate_sql_configured_output_format(ctx)

        assert args.format == "json"

    def test_human_prelude_is_first_when_streams_are_merged(self, tmp_path):
        sql_file = tmp_path / "V1__bad.sql"
        sql_file.write_text("UPDATE users SET name = name;\n", encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = os.getcwd()

        result = subprocess.run(
            _cli_with_stub_license(
                tmp_path,
                "validate-sql",
                "--dialect",
                "postgresql",
                str(sql_file),
            ),
            cwd=os.getcwd(),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )

        assert result.returncode == 0
        assert result.stdout.lstrip().startswith("┏")
        assert result.stdout.index("DBLIFT DATABASE MIGRATION LOG") < result.stdout.index(
            "validate-sql findings"
        )

    def test_parser_accepts_fail_on_profile_rules_and_rejects_removed_flag(self):
        from cli._parser_setup import create_parser

        parser = create_parser()
        args = parser.parse_args(
            [
                "validate-sql",
                "migrations",
                "--fail-on",
                "warning",
                "--profile",
                "enterprise",
                "--rules",
                "security,best_practices",
                "--rules",
                "performance",
            ]
        )

        assert args.command == "validate-sql"
        assert args.fail_on == "warning"
        assert args.rule_profile == "enterprise"
        assert args.rules == ["security,best_practices", "performance"]
        assert getattr(args, "output", None) is None

        default_args = parser.parse_args(["validate-sql", "migrations"])
        assert default_args.fail_on is None
        assert default_args.format is None

        with pytest.raises(SystemExit):
            parser.parse_args(["validate-sql", "migrations", "--fail-on-violations"])


# ---------------------------------------------------------------------------
# OBS-02: _is_migration_sql_file naming-convention filter
# ---------------------------------------------------------------------------


class TestIsMigrationSqlFile:
    """validate-sql directory scans must skip non-migration SQL files."""

    def _p(self, name: str) -> Path:
        return Path("/tmp") / name

    @pytest.mark.parametrize(
        "filename",
        [
            "V1__create_tables.sql",
            "V1.2__add_column.sql",
            "V10_5__patch.sql",
            "R__refresh_stats.sql",
            "U1__undo_create.sql",
            "B1__baseline.sql",
        ],
    )
    def test_migration_files_accepted(self, filename):
        from cli._command_handlers import _is_migration_sql_file

        assert _is_migration_sql_file(self._p(filename)) is True

    @pytest.mark.parametrize(
        "filename",
        [
            "schema.sql",
            "seed_data.sql",
            "random_file.sql",
            "backup_2026.sql",
            "validate_test.sql",
        ],
    )
    def test_non_migration_files_rejected(self, filename):
        from cli._command_handlers import _is_migration_sql_file

        assert _is_migration_sql_file(self._p(filename)) is False


# ---------------------------------------------------------------------------
# OBS-01/02: db subcommand logger must honour --log-dir / --log-format args
# ---------------------------------------------------------------------------


class TestDbUtilsLoggingFromArgs:
    """db subcommands must use --log-dir and --log-format from CLI args."""

    def test_custom_log_dir_is_used(self, tmp_path):
        from argparse import Namespace
        from unittest.mock import MagicMock, patch

        from cli.db_utils import check_connection

        custom_log_dir = tmp_path / "custom_logs"
        args = Namespace(
            db_url="postgresql+psycopg://localhost:5432/test",
            db_username="u",
            db_password="p",
            db_schema="public",
            db_type=None,
            config=None,
            log_dir=str(custom_log_dir),
            log_format="text",
            log_level="info",
        )

        with patch("cli.db_utils.DbliftLogger") as mock_logger_cls:
            mock_logger_cls.return_value = MagicMock()
            with patch("cli.db_utils.load_config", side_effect=Exception("skip")):
                try:
                    check_connection(args)
                except Exception:
                    pass
            call_kwargs = mock_logger_cls.call_args
            if call_kwargs:
                used_dir = call_kwargs[1].get("logfile_dir") or (
                    call_kwargs[0][0] if call_kwargs[0] else None
                )
                assert str(used_dir) == str(custom_log_dir)

    def test_json_log_format_is_used(self, tmp_path):
        from argparse import Namespace
        from unittest.mock import MagicMock, patch

        from cli.db_utils import check_connection
        from core.logger import LogFormat

        args = Namespace(
            db_url="postgresql+psycopg://localhost:5432/test",
            db_username="u",
            db_password="p",
            db_schema="public",
            db_type=None,
            config=None,
            log_dir=str(tmp_path),
            log_format="json",
            log_level="info",
        )

        with patch("cli.db_utils.DbliftLogger") as mock_logger_cls:
            mock_logger_cls.return_value = MagicMock()
            with patch("cli.db_utils.load_config", side_effect=Exception("skip")):
                try:
                    check_connection(args)
                except Exception:
                    pass
            call_kwargs = mock_logger_cls.call_args
            if call_kwargs:
                used_format = call_kwargs[1].get("format") or (
                    call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None
                )
                assert used_format == LogFormat.JSON
