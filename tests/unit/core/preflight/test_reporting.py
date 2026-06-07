from types import SimpleNamespace

from core.preflight.models import PreflightPhase, PreflightResult
from core.preflight.reporting import preflight_result_to_finding_report


def test_report_contains_phase_error_as_error_finding():
    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="error",
        phases=[PreflightPhase(name="replay", status="FAIL", message="ORA-00942")],
    )

    report = preflight_result_to_finding_report(result)

    assert report.command == "preflight"
    assert report.fail_on == "error"
    assert report.summary["error"] == 1
    assert report.findings[0].code == "preflight.replay"
    assert report.findings[0].message == "ORA-00942"


def test_report_imports_plan_findings():
    plan_report = type(
        "PlanReport",
        (),
        {
            "findings": [
                type(
                    "FindingLike",
                    (),
                    {
                        "severity": "warning",
                        "code": "plan.pending",
                        "message": "Migration V2__users.sql is pending",
                        "file": "V2__users.sql",
                        "line": None,
                        "column": None,
                        "details": {},
                    },
                )()
            ]
        },
    )()
    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="warning",
        phases=[PreflightPhase(name="plan", status="PASS")],
    )

    report = preflight_result_to_finding_report(result, plan_report=plan_report)

    assert report.summary["warning"] == 1
    assert report.findings[0].code == "plan.pending"


def test_report_imports_plan_findings_from_dicts():
    """SqlValidationSummary.findings are dicts (Finding.to_dict()); they must
    still flow into the report so --fail-on can trigger on plan warnings/info."""
    sql_validation = SimpleNamespace(
        findings=[
            {
                "severity": "warning",
                "code": "sql.missing_where",
                "message": "UPDATE without WHERE",
                "file": "V3__bulk.sql",
            }
        ]
    )
    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="warning",
        phases=[PreflightPhase(name="plan", status="PASS")],
    )

    report = preflight_result_to_finding_report(result, plan_report=sql_validation)

    assert report.summary["warning"] == 1
    assert report.findings[0].code == "sql.missing_where"
    assert report.findings[0].file == "V3__bulk.sql"
