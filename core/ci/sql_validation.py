"""Converters from SQL validation models to normalized CI findings."""

from __future__ import annotations

from typing import Any, cast

from core.ci.findings import Finding, FindingReport, FindingSeverity, normalize_fail_on


def validation_result_to_finding_report(result: Any, fail_on: str = "error") -> FindingReport:
    """Convert SQL validation output to normalized CI findings."""
    findings = []
    for violation in getattr(result, "violations", []):
        severity = getattr(getattr(violation, "severity", None), "value", None)
        if severity not in ("error", "warning", "info"):
            severity = "warning"
        source = getattr(getattr(violation, "source", None), "value", None) or "sql"
        rule_id = getattr(violation, "rule_id", None) or f"sql.{source}"
        details = {"source": source}
        for attr in (
            "suggestion",
            "rationale",
            "remediation",
            "control_mapping",
            "override_policy",
            "exception",
        ):
            value = getattr(violation, attr, None)
            if value:
                details[attr] = value
        findings.append(
            Finding(
                severity=cast(FindingSeverity, severity),
                code=str(rule_id),
                message=str(getattr(violation, "message", "")),
                file=str(getattr(violation, "file_path", "") or "") or None,
                line=getattr(violation, "line", None),
                column=getattr(violation, "column", None),
                details=details,
            )
        )
    raw_checked_count = getattr(result, "files_checked", 0) or 0
    try:
        checked_count = int(raw_checked_count)
    except (TypeError, ValueError):
        checked_count = 0

    return FindingReport(
        command="validate-sql",
        fail_on=normalize_fail_on(fail_on),
        checked_count=checked_count,
        findings=findings,
    )
