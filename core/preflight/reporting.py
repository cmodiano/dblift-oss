"""Convert preflight workflow results into normalized CI findings."""

from __future__ import annotations

from typing import Any, List, cast

from core.ci.findings import Finding, FindingReport, FindingSeverity, normalize_fail_on
from core.preflight.models import PreflightResult


def _finding_field(finding: Any, key: str, default: Any = None) -> Any:
    """Read a field from a Finding object or dict, returning default if absent."""
    if isinstance(finding, dict):
        return finding.get(key, default)
    return getattr(finding, key, default)


def preflight_result_to_finding_report(
    result: PreflightResult,
    *,
    plan_report: Any = None,
) -> FindingReport:
    """Build the normalized CI report for preflight."""
    findings: List[Finding] = []

    if plan_report is not None:
        for finding in getattr(plan_report, "findings", []) or []:
            findings.append(
                Finding(
                    severity=cast(FindingSeverity, _finding_field(finding, "severity", "warning")),
                    code=str(_finding_field(finding, "code", "plan.finding")),
                    message=str(_finding_field(finding, "message", "")),
                    file=_finding_field(finding, "file"),
                    line=_finding_field(finding, "line"),
                    column=_finding_field(finding, "column"),
                    details=dict(_finding_field(finding, "details", {}) or {}),
                )
            )

    for phase in result.phases:
        if phase.status != "FAIL":
            continue
        findings.append(
            Finding(
                severity="error",
                code=f"preflight.{phase.name}",
                message=phase.message or f"Preflight phase failed: {phase.name}",
                details={"blocking": True, "source": "runtime", **phase.metadata},
            )
        )

    if result.error_message:
        findings.append(
            Finding(
                severity="error",
                code="preflight.error",
                message=result.error_message,
                details={"blocking": True, "source": "runtime"},
            )
        )

    return FindingReport(
        command="preflight",
        fail_on=normalize_fail_on(result.fail_on),
        checked_count=len(result.replayed_scripts),
        findings=findings,
        metadata=result.to_dict(),
    )
