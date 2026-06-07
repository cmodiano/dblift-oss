from core.ci.findings import Finding, FindingReport, should_fail_for_threshold


def test_error_threshold_fails_on_error_only():
    report = FindingReport(
        command="plan",
        findings=[
            Finding(
                severity="warning",
                code="plan.pending",
                message="Migration pending",
                file="migrations/V2__users.sql",
            )
        ],
    )

    assert should_fail_for_threshold(report, "error") is False


def test_warning_threshold_fails_on_warning():
    report = FindingReport(
        command="plan",
        findings=[
            Finding(
                severity="warning",
                code="plan.pending",
                message="Migration pending",
                file="migrations/V2__users.sql",
            )
        ],
    )

    assert should_fail_for_threshold(report, "warning") is True


def test_never_threshold_does_not_fail_on_findings():
    report = FindingReport(
        command="validate-sql",
        findings=[
            Finding(
                severity="error",
                code="sql.syntax",
                message="Syntax error",
                file="migrations/V1__bad.sql",
                line=4,
            )
        ],
    )

    assert should_fail_for_threshold(report, "never") is False


def test_syntax_source_obeys_threshold_never():
    report = FindingReport(
        command="validate-sql",
        fail_on="never",
        findings=[
            Finding(
                severity="error",
                code="parse_error",
                message="Error tokenizing",
                details={"source": "syntax"},
            )
        ],
    )

    assert should_fail_for_threshold(report, "never") is False
    assert report.to_dict()["success"] is True


def test_runtime_source_fails_even_when_threshold_is_never():
    report = FindingReport(
        command="plan",
        fail_on="never",
        findings=[
            Finding(
                severity="error",
                code="plan.error",
                message="Snapshot missing",
                details={"blocking": True, "source": "runtime"},
            )
        ],
    )

    assert should_fail_for_threshold(report, "never") is True
    assert report.to_dict()["success"] is False


def test_plan_validation_source_obeys_threshold_never():
    report = FindingReport(
        command="plan",
        fail_on="never",
        findings=[
            Finding(
                severity="error",
                code="plan.error",
                message="Snapshot metadata is malformed",
                details={"validation_source": "plan"},
            )
        ],
    )

    assert should_fail_for_threshold(report, "never") is False
    assert report.to_dict()["success"] is True


def test_plan_source_is_not_an_always_fail_source():
    report = FindingReport(
        command="plan",
        fail_on="never",
        findings=[
            Finding(
                severity="error",
                code="plan.error",
                message="Plan validation issue",
                details={"source": "plan"},
            )
        ],
    )

    assert should_fail_for_threshold(report, "never") is False
    assert report.to_dict()["success"] is True


def test_blocking_finding_fails_even_when_threshold_is_never():
    report = FindingReport(
        command="plan",
        fail_on="never",
        findings=[
            Finding(
                severity="error",
                code="plan.checksum_drift",
                message="Checksum drift",
                details={"blocking": True, "source": "checksum_drift"},
            )
        ],
    )

    assert should_fail_for_threshold(report, "never") is True
    assert report.to_dict()["success"] is False


def test_report_to_dict_includes_summary_counts():
    report = FindingReport(
        command="validate-sql",
        checked_count=2,
        findings=[
            Finding(severity="error", code="sql.syntax", message="Syntax error"),
            Finding(severity="warning", code="sql.performance", message="Missing index"),
            Finding(severity="info", code="sql.naming", message="Informational"),
        ],
    )

    payload = report.to_dict()

    assert payload["command"] == "validate-sql"
    assert payload["checked_count"] == 2
    assert payload["summary"] == {"error": 1, "warning": 1, "info": 1}
    assert payload["findings"][0]["severity"] == "error"


def test_report_to_dict_success_uses_report_fail_on_threshold():
    report = FindingReport(
        command="plan",
        fail_on="warning",
        findings=[
            Finding(
                severity="warning",
                code="plan.pending",
                message="Migration pending",
            )
        ],
    )

    payload = report.to_dict()

    assert payload["fail_on"] == "warning"
    assert payload["success"] is False


def test_finding_normalizes_unknown_severity_to_warning():
    report = FindingReport(
        command="plan",
        findings=[
            Finding(
                severity="critical",  # type: ignore[arg-type]
                code="plan.custom",
                message="Custom rule severity",
            )
        ],
    )

    payload = report.to_dict()

    assert report.summary == {"error": 0, "warning": 1, "info": 0}
    assert payload["findings"][0]["severity"] == "warning"


def test_sql_validation_conversion_preserves_enterprise_metadata():
    from pathlib import Path

    from core.ci.sql_validation import validation_result_to_finding_report
    from core.sql_validator.linting.models import (
        ValidationResult,
        ValidationViolation,
        ViolationSeverity,
    )

    result = ValidationResult(
        files_checked=1,
        violations=[
            ValidationViolation(
                rule_id="no_drop_table_without_ticket",
                severity=ViolationSeverity.ERROR,
                message="DROP TABLE requires approved change evidence",
                file_path=Path("migrations/V9__drop_customers.sql"),
                rationale="Dropping tables can permanently remove data.",
                remediation="Attach an approved change ticket.",
                control_mapping=["SOX-CC7.2"],
                override_policy={"requires": ["owner", "ticket"]},
            )
        ],
    )

    report = validation_result_to_finding_report(result)

    details = report.findings[0].details
    assert details["rationale"] == "Dropping tables can permanently remove data."
    assert details["remediation"] == "Attach an approved change ticket."
    assert details["control_mapping"] == ["SOX-CC7.2"]
    assert details["override_policy"] == {"requires": ["owner", "ticket"]}
