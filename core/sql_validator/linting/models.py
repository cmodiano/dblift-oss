"""Data models for SQL validation."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ViolationSeverity(Enum):
    """Severity levels for validation violations."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ViolationSource(Enum):
    """Source of the validation violation."""

    BUSINESS_RULE = "business_rule"  # From declarative YAML rules
    PERFORMANCE = "performance"  # From performance analysis
    SYNTAX = "syntax"  # From syntax checking


@dataclass
class ValidationViolation:
    """Represents a single validation violation."""

    rule_id: str
    severity: ViolationSeverity
    message: str
    file_path: Optional[Path] = None
    line: Optional[int] = None
    column: Optional[int] = None
    source: ViolationSource = ViolationSource.BUSINESS_RULE
    suggestion: Optional[str] = None
    code_snippet: Optional[str] = None
    rationale: Optional[str] = None
    remediation: Optional[str] = None
    control_mapping: List[str] = field(default_factory=list)
    override_policy: Dict[str, Any] = field(default_factory=dict)
    exception: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "file_path": str(self.file_path) if self.file_path else None,
            "line": self.line,
            "column": self.column,
            "source": self.source.value,
            "suggestion": self.suggestion,
            "code_snippet": self.code_snippet,
            "rationale": self.rationale,
            "remediation": self.remediation,
            "control_mapping": list(self.control_mapping),
            "override_policy": dict(self.override_policy),
            "exception": dict(self.exception) if self.exception else None,
        }

    def __str__(self) -> str:
        """Human-readable string representation."""
        location = ""
        if self.file_path:
            location = f"{self.file_path}"
            if self.line:
                location += f":{self.line}"
                if self.column:
                    location += f":{self.column}"

        severity_symbol = {
            ViolationSeverity.ERROR: "❌",
            ViolationSeverity.WARNING: "⚠️",
            ViolationSeverity.INFO: "ℹ️",
        }.get(self.severity, "•")

        result = f"{severity_symbol} {self.message}"
        if location:
            result = f"{location}\n   {result}"
        if self.suggestion:
            result += f"\n   💡 Fix: {self.suggestion}"

        return result


@dataclass
class ValidationResult:
    """Result of SQL validation containing all violations."""

    violations: List[ValidationViolation] = field(default_factory=list)
    files_checked: int = 0
    success: bool = True

    @property
    def error_count(self) -> int:
        """Count of error-level violations."""
        return sum(1 for v in self.violations if v.severity == ViolationSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of warning-level violations."""
        return sum(1 for v in self.violations if v.severity == ViolationSeverity.WARNING)

    @property
    def info_count(self) -> int:
        """Count of info-level violations."""
        return sum(1 for v in self.violations if v.severity == ViolationSeverity.INFO)

    @property
    def has_violations(self) -> bool:
        """Check if there are any violations."""
        return len(self.violations) > 0

    @property
    def has_errors(self) -> bool:
        """Check if there are any error-level violations."""
        return self.error_count > 0

    def add_violation(self, violation: ValidationViolation) -> None:
        """Add a violation to the result."""
        self.violations.append(violation)
        if violation.severity == ViolationSeverity.ERROR:
            self.success = False

    def merge(self, other: "ValidationResult") -> None:
        """Merge another result into this one."""
        self.violations.extend(other.violations)
        self.files_checked += other.files_checked
        if not other.success:
            self.success = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "files_checked": self.files_checked,
            "violations": [v.to_dict() for v in self.violations],
            "summary": {
                "total": len(self.violations),
                "errors": self.error_count,
                "warnings": self.warning_count,
                "info": self.info_count,
            },
        }

    def get_violations_by_source(self, source: ViolationSource) -> List[ValidationViolation]:
        """Get violations from a specific source."""
        return [v for v in self.violations if v.source == source]

    def get_violations_by_file(self, file_path: Path) -> List[ValidationViolation]:
        """Get violations for a specific file."""
        return [v for v in self.violations if v.file_path == file_path]
