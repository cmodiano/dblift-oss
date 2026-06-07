import json

from core.ci.findings import Finding, FindingReport
from core.ci.formatters import format_finding_report


def _report():
    return FindingReport(
        command="plan",
        checked_count=2,
        findings=[
            Finding(
                severity="error",
                code="plan.checksum_drift",
                message="Checksum drift for V1__init.sql",
                file="migrations/V1__init.sql",
                line=1,
            ),
            Finding(
                severity="warning",
                code="plan.pending",
                message="Migration V2__users.sql is pending",
                file="migrations/V2__users.sql",
            ),
        ],
        metadata={"snapshot_model": "env.snapshot.json"},
    )


def test_json_formatter_uses_shared_contract():
    payload = json.loads(format_finding_report(_report(), "json"))

    assert payload["command"] == "plan"
    assert payload["summary"]["error"] == 1
    assert payload["findings"][0]["code"] == "plan.checksum_drift"


def test_gitlab_formatter_outputs_code_quality_schema():
    payload = json.loads(format_finding_report(_report(), "gitlab"))

    assert isinstance(payload, list)
    assert payload[0]["description"] == "Checksum drift for V1__init.sql"
    assert payload[0]["check_name"] == "plan.checksum_drift"
    assert payload[0]["severity"] == "major"
    assert payload[0]["location"] == {
        "path": "migrations/V1__init.sql",
        "lines": {"begin": 1},
    }
    assert len(payload[0]["fingerprint"]) == 64
    assert payload[1]["severity"] == "minor"
    assert payload[1]["location"]["lines"]["begin"] == 1


def test_gitlab_formatter_uses_relative_paths_from_cwd(tmp_path, monkeypatch):
    migration = tmp_path / "migrations" / "V1__init.sql"
    migration.parent.mkdir()
    migration.write_text("select 1;\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    report = FindingReport(
        command="validate-sql",
        findings=[
            Finding(
                severity="warning",
                code="sql.warning",
                message="warning",
                file=str(migration),
                line=3,
            )
        ],
    )

    payload = json.loads(format_finding_report(report, "gitlab"))

    assert payload[0]["location"]["path"] == "migrations/V1__init.sql"


def test_github_actions_formatter_outputs_annotations():
    output = format_finding_report(_report(), "github-actions")

    assert (
        "::error file=migrations/V1__init.sql,line=1::Checksum drift for V1__init.sql "
        "[plan.checksum_drift]"
    ) in output
    assert (
        "::warning file=migrations/V2__users.sql,line=1::Migration V2__users.sql is "
        "pending [plan.pending]"
    ) in output


def test_compact_formatter_outputs_one_line_per_finding():
    output = format_finding_report(_report(), "compact")

    assert (
        "ERROR [plan.checksum_drift]: migrations/V1__init.sql:1: Checksum drift for " "V1__init.sql"
    ) in output
    assert (
        "WARN [plan.pending]: migrations/V2__users.sql: Migration V2__users.sql is " "pending"
    ) in output


def test_sarif_formatter_outputs_sarif_results():
    payload = json.loads(format_finding_report(_report(), "sarif"))

    assert payload["version"] == "2.1.0"
    assert payload["runs"][0]["tool"]["driver"]["name"] == "DBLift"
    assert payload["runs"][0]["results"][0]["ruleId"] == "plan.checksum_drift"


def test_preflight_html_report_contains_phase_metadata():
    report = FindingReport(
        command="preflight",
        fail_on="error",
        checked_count=2,
        metadata={
            "phases": [
                {"name": "plan", "status": "PASS", "metadata": {"pending": 2}},
                {"name": "replay", "status": "PASS", "metadata": {"statements": 4}},
            ],
            "snapshot_model": "env.snapshot.json",
            "replayed_scripts": ["V1__init.sql", "V2__users.sql", "V1001__invoice.sql"],
        },
    )

    html = format_finding_report(report, "html")

    assert "<html" in html
    assert "Preflight Report" in html
    assert "env.snapshot.json" in html
    assert "V1001__invoice.sql" in html


def test_html_report_title_uses_command_name():
    html = format_finding_report(FindingReport(command="plan"), "html")

    assert "<title>DBLift Plan Report</title>" in html
    assert "<h1>Plan Report</h1>" in html
    assert "Preflight Report" not in html


def test_validate_sql_html_report_renders_policy_evidence():
    report = FindingReport(
        command="validate-sql",
        fail_on="warning",
        checked_count=1,
        findings=[
            Finding(
                severity="error",
                code="no_drop_table_without_ticket",
                message="DROP TABLE requires approved change evidence",
                file="migrations/V9__drop_customers.sql",
                line=1,
                details={
                    "source": "business_rule",
                    "rationale": "Dropping tables can permanently remove data.",
                    "remediation": "Attach an approved change ticket.",
                    "control_mapping": ["SOX-CC7.2"],
                    "override_policy": {"requires": ["owner", "ticket"]},
                },
            )
        ],
        metadata={
            "profile": "enterprise",
            "dialect": "postgresql",
            "rules_file": ".dblift_rules.yaml",
        },
    )

    html = format_finding_report(report, "html")

    assert "<!doctype html>" in html.lower()
    assert "Validate Sql Report" in html
    assert "SQL Validation Evidence" in html
    assert "no_drop_table_without_ticket" in html
    assert "SOX-CC7.2" in html
    assert "Attach an approved change ticket." in html
