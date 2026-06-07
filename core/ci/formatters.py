"""Shared formatters for normalized CI findings."""

from __future__ import annotations

import json
from hashlib import sha256
from html import escape as _escape
from pathlib import Path
from typing import Any, Dict, List

from core.ci.findings import Finding, FindingReport, should_fail_for_threshold


def format_finding_report(report: FindingReport, output_format: str) -> str:
    """Format a finding report in a supported CI output format."""
    normalized = (output_format or "console").lower()
    if normalized == "json":
        return json.dumps(report.to_dict(), indent=2)
    if normalized == "gitlab":
        return _format_gitlab(report)
    if normalized == "github-actions":
        return _format_github_actions(report)
    if normalized == "compact":
        return _format_compact(report)
    if normalized == "sarif":
        return _format_sarif(report)
    if normalized == "html":
        return _format_html(report)
    if normalized == "console":
        return _format_console(report)
    raise ValueError(f"Unknown CI finding format: {output_format}")


def _format_console(report: FindingReport) -> str:
    lines = [
        "",
        "=" * 60,
        f"{report.command} findings",
        "=" * 60,
        f"Checked: {report.checked_count}",
        f"Errors: {report.summary['error']}",
        f"Warnings: {report.summary['warning']}",
        f"Info: {report.summary['info']}",
        "",
    ]
    if not report.findings:
        lines.append("No findings.")
    for finding in report.findings:
        lines.append(_compact_line(finding))
    lines.append("=" * 60)
    return "\n".join(lines)


def _format_compact(report: FindingReport) -> str:
    if not report.findings:
        return f"OK [{report.command}]: {report.checked_count} checked, no findings"
    return "\n".join(_compact_line(finding) for finding in report.findings)


def _compact_line(finding: Finding) -> str:
    label = {"error": "ERROR", "warning": "WARN", "info": "INFO"}[finding.severity]
    location = finding.file or "inline"
    if finding.line is not None:
        location = f"{location}:{finding.line}"
    return f"{label} [{finding.code}]: {location}: {finding.message}"


def _format_github_actions(report: FindingReport) -> str:
    if not report.findings:
        return f"::notice::{report.command}: {report.checked_count} checked, no findings"

    lines = []
    for finding in report.findings:
        annotation = {"error": "error", "warning": "warning", "info": "notice"}[finding.severity]
        file = finding.file or "unknown"
        line = finding.line or 1
        message = f"{finding.message} [{finding.code}]"
        lines.append(f"::{annotation} file={file},line={line}::{message}")
    return "\n".join(lines)


def _format_gitlab(report: FindingReport) -> str:
    return json.dumps([_gitlab_issue(finding) for finding in report.findings], indent=2)


def _gitlab_issue(finding: Finding) -> Dict[str, Any]:
    path = _gitlab_path(finding.file)
    line = finding.line or 1
    return {
        "description": finding.message,
        "check_name": finding.code,
        "fingerprint": _gitlab_fingerprint(finding, path, line),
        "severity": _gitlab_severity(finding),
        "location": {
            "path": path,
            "lines": {"begin": line},
        },
    }


def _gitlab_path(path: str | None) -> str:
    if not path:
        return "unknown"
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            return candidate.as_posix()
    return path.removeprefix("./")


def _gitlab_fingerprint(finding: Finding, path: str, line: int) -> str:
    fingerprint = f"{finding.code}:{path}:{line}:{finding.message}"
    return sha256(fingerprint.encode("utf-8")).hexdigest()


def _gitlab_severity(finding: Finding) -> str:
    return {"error": "major", "warning": "minor", "info": "info"}[finding.severity]


def _format_sarif(report: FindingReport) -> str:
    return json.dumps(
        {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {"driver": {"name": "DBLift", "rules": _sarif_rules(report.findings)}},
                    "results": [_sarif_result(finding) for finding in report.findings],
                }
            ],
        },
        indent=2,
    )


def _sarif_rules(findings: List[Finding]) -> List[Dict[str, Any]]:
    seen = set()
    rules = []
    for finding in findings:
        if finding.code in seen:
            continue
        seen.add(finding.code)
        rules.append(
            {
                "id": finding.code,
                "shortDescription": {"text": finding.message},
                "defaultConfiguration": {"level": _sarif_level(finding)},
            }
        )
    return rules


def _sarif_result(finding: Finding) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ruleId": finding.code,
        "level": _sarif_level(finding),
        "message": {"text": finding.message},
    }
    if finding.file:
        result["locations"] = [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": finding.file},
                    "region": {
                        "startLine": finding.line or 1,
                        "startColumn": finding.column or 1,
                    },
                }
            }
        ]
    return result


def _sarif_level(finding: Finding) -> str:
    return {"error": "error", "warning": "warning", "info": "note"}[finding.severity]


def _format_html(report: FindingReport) -> str:
    if report.command == "validate-sql":
        return _format_validate_sql_html(report)
    return _format_workflow_html(report)


def _format_workflow_html(report: FindingReport) -> str:
    report_title = f"{report.command.replace('-', ' ').title()} Report"
    phases = report.metadata.get("phases", [])
    replayed_scripts = report.metadata.get("replayed_scripts", [])
    phase_rows = "\n".join(
        "<tr>"
        f"<td>{_escape(str(phase.get('name', '')))}</td>"
        f"<td>{_escape(str(phase.get('status', '')))}</td>"
        f"<td>{_escape(json.dumps(phase.get('metadata', {}), sort_keys=True))}</td>"
        "</tr>"
        for phase in phases
        if isinstance(phase, dict)
    )
    file_items = "\n".join(f"<li>{_escape(str(script))}</li>" for script in replayed_scripts)
    finding_items = "\n".join(
        f"<li>{_escape(_compact_line(finding))}</li>" for finding in report.findings
    )
    success = not should_fail_for_threshold(report, report.fail_on)
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>DBLift {_escape(report_title)}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;}"
        "table{border-collapse:collapse;width:100%;}"
        "td,th{border:1px solid #ddd;padding:.5rem;text-align:left;}"
        ".ok{color:#087443}.fail{color:#b42318}</style>"
        "</head><body>"
        f"<h1>{_escape(report_title)}</h1>"
        f"<p>Snapshot: {_escape(str(report.metadata.get('snapshot_model', '')))}</p>"
        f"<p>Success: {_escape(str(success))}</p>"
        "<h2>Phases</h2>"
        "<table><thead><tr><th>Phase</th><th>Status</th><th>Metadata</th></tr></thead>"
        f"<tbody>{phase_rows}</tbody></table>"
        "<h2>Replayed Scripts</h2>"
        f"<ul>{file_items}</ul>"
        "<h2>Findings</h2>"
        f"<ul>{finding_items}</ul>"
        "</body></html>"
    )


def _format_validate_sql_html(report: FindingReport) -> str:
    report_title = "Validate Sql Report"
    success = not should_fail_for_threshold(report, report.fail_on)
    metadata_items = "\n".join(
        f"<tr><th>{_escape(str(key))}</th><td>{_escape(str(value))}</td></tr>"
        for key, value in sorted(report.metadata.items())
        if value not in (None, "", [], {})
    )
    finding_rows = "\n".join(_html_finding_row(finding) for finding in report.findings)
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>DBLift {_escape(report_title)}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;}"
        "table{border-collapse:collapse;width:100%;margin:1rem 0;}"
        "td,th{border:1px solid #ddd;padding:.5rem;text-align:left;vertical-align:top;}"
        ".ok{color:#087443}.fail{color:#b42318}"
        "code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}</style>"
        "</head><body>"
        f"<h1>{_escape(report_title)}</h1>"
        "<h2>SQL Validation Evidence</h2>"
        f"<p class=\"{'ok' if success else 'fail'}\">Success: {_escape(str(success))}</p>"
        f"<p>Checked files: {_escape(str(report.checked_count))}</p>"
        f"<p>Failure threshold: {_escape(str(report.fail_on))}</p>"
        "<table><tbody>"
        f"<tr><th>Errors</th><td>{report.summary['error']}</td></tr>"
        f"<tr><th>Warnings</th><td>{report.summary['warning']}</td></tr>"
        f"<tr><th>Info</th><td>{report.summary['info']}</td></tr>"
        f"{metadata_items}"
        "</tbody></table>"
        "<h2>Findings</h2>"
        "<table><thead><tr>"
        "<th>Severity</th><th>Rule</th><th>Location</th><th>Message</th>"
        "<th>Evidence</th>"
        "</tr></thead><tbody>"
        f"{finding_rows}"
        "</tbody></table>"
        "</body></html>"
    )


def _html_finding_row(finding: Finding) -> str:
    location = finding.file or "inline"
    if finding.line is not None:
        location = f"{location}:{finding.line}"
    evidence = _html_finding_evidence(finding)
    return (
        "<tr>"
        f"<td>{_escape(finding.severity)}</td>"
        f"<td><code>{_escape(finding.code)}</code></td>"
        f"<td>{_escape(location)}</td>"
        f"<td>{_escape(finding.message)}</td>"
        f"<td>{evidence}</td>"
        "</tr>"
    )


def _html_finding_evidence(finding: Finding) -> str:
    details = finding.details or {}
    parts = []
    for key in ("rationale", "remediation", "suggestion"):
        if details.get(key):
            parts.append(f"<p><strong>{_escape(key)}:</strong> {_escape(str(details[key]))}</p>")
    if details.get("control_mapping"):
        controls = ", ".join(str(item) for item in details["control_mapping"])
        parts.append(f"<p><strong>controls:</strong> {_escape(controls)}</p>")
    if details.get("override_policy"):
        policy = json.dumps(details["override_policy"], sort_keys=True)
        parts.append(f"<p><strong>override policy:</strong> {_escape(policy)}</p>")
    if details.get("exception"):
        exception = json.dumps(details["exception"], sort_keys=True)
        parts.append(f"<p><strong>exception:</strong> {_escape(exception)}</p>")
    return "".join(parts)
