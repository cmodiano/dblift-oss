"""Models used by offline migration planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SQL_VALIDATION_FAILURE_MESSAGE = "validate-sql failed for planned migrations"


@dataclass(frozen=True)
class AppliedMigrationState:
    """Versioned migration state loaded from snapshot metadata."""

    version: Optional[str]
    script: str
    checksum: Optional[int]
    installed_rank: Optional[int]
    installed_on: Optional[str]
    type: str
    success: bool


@dataclass(frozen=True)
class AppliedRepeatableState:
    """Repeatable migration state loaded from snapshot metadata."""

    script: str
    checksum: Optional[int]
    installed_rank: Optional[int]
    installed_on: Optional[str]


@dataclass(frozen=True)
class PlannedMigration:
    """Local migration selected for the offline plan."""

    script: str
    version: Optional[str]
    description: str
    type: str
    checksum: Optional[int]
    path: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the planned migration for JSON/report output."""
        return {
            "script": self.script,
            "version": self.version,
            "description": self.description,
            "type": self.type,
            "checksum": self.checksum,
            "path": self.path,
        }


@dataclass(frozen=True)
class ChecksumDrift:
    """Checksum mismatch between snapshot metadata and local script content."""

    script: str
    version: Optional[str]
    expected_checksum: Optional[int]
    actual_checksum: Optional[int]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the checksum drift for JSON/report output."""
        return {
            "script": self.script,
            "version": self.version,
            "expected_checksum": self.expected_checksum,
            "actual_checksum": self.actual_checksum,
        }


@dataclass(frozen=True)
class SqlValidationSummary:
    """Summary of SQL validation executed during planning."""

    enabled: bool
    scope: str
    status: str
    files_checked: int = 0
    errors: int = 0
    warnings: int = 0
    messages: List[str] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize SQL validation status for JSON/report output."""
        return {
            "enabled": self.enabled,
            "scope": self.scope,
            "status": self.status,
            "files_checked": self.files_checked,
            "errors": self.errors,
            "warnings": self.warnings,
            "messages": list(self.messages),
            "findings": [dict(finding) for finding in self.findings],
        }


@dataclass(frozen=True)
class PlanData:
    """Complete offline plan computed from snapshot state and local scripts."""

    snapshot_model: str
    target_last_version: Optional[str]
    target_installed_rank: Optional[int]
    pending: List[PlannedMigration]
    repeatables_pending: List[PlannedMigration]
    checksum_drift: List[ChecksumDrift]
    already_applied_count: int
    warnings: List[str]
    errors: List[str]
    sql_validation: SqlValidationSummary

    @property
    def has_errors(self) -> bool:
        """Return True when the plan found blocking issues."""
        return bool(self.errors or self.checksum_drift)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the full plan payload for JSON/report output."""
        return {
            "snapshot_model": self.snapshot_model,
            "target_last_version": self.target_last_version,
            "target_installed_rank": self.target_installed_rank,
            "pending": [item.to_dict() for item in self.pending],
            "repeatables_pending": [item.to_dict() for item in self.repeatables_pending],
            "checksum_drift": [item.to_dict() for item in self.checksum_drift],
            "already_applied_count": self.already_applied_count,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "sql_validation": self.sql_validation.to_dict(),
        }
