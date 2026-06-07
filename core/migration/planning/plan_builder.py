"""Build an offline migration plan from a snapshot state and local scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from core.migration._type_match import is_migration_type, is_versioned, migration_type_name
from core.migration.migration import Migration, normalize_migration_checksum
from core.migration.planning._coercion import optional_int
from core.migration.planning.models import (
    SQL_VALIDATION_FAILURE_MESSAGE,
    ChecksumDrift,
    PlanData,
    PlannedMigration,
    SqlValidationSummary,
)
from core.migration.planning.snapshot_state import SnapshotMigrationState
from core.sql_validator.linting.sql_validator import SqlValidator


class PlanBuilder:
    """Compare local migration scripts with a snapshot's recorded migration state."""

    def __init__(
        self,
        *,
        scripts_dir: Path,
        snapshot_state: SnapshotMigrationState,
        script_manager: Any,
        dialect: str,
        recursive: bool = True,
        additional_dirs: Optional[List[Path]] = None,
        dir_recursive_map: Optional[Dict[Path, bool]] = None,
        skip_validate_sql: bool = False,
        validate_scope: str = "pending",
        validation_config: Optional[Any] = None,
    ) -> None:
        """Store dependencies and planning options."""
        self.scripts_dir = scripts_dir
        self.snapshot_state = snapshot_state
        self.script_manager = script_manager
        self.dialect = dialect
        self.recursive = recursive
        self.additional_dirs = additional_dirs
        self.dir_recursive_map = dir_recursive_map
        self.skip_validate_sql = skip_validate_sql
        self.validate_scope = validate_scope
        self.validation_config = validation_config

    def build(self) -> PlanData:
        """Compute pending work, drift, and SQL validation from local scripts."""
        migrations = self.script_manager.get_migration_scripts(
            self.scripts_dir,
            recursive=self.recursive,
            additional_dirs=self.additional_dirs,
            dir_recursive_map=self.dir_recursive_map,
        )
        versioned = [m for m in migrations if is_versioned(getattr(m, "type", None)) and m.version]
        repeatables = [
            m for m in migrations if is_migration_type(getattr(m, "type", None), "REPEATABLE")
        ]

        warnings: List[str] = []
        errors: List[str] = []
        if not self.snapshot_state.has_applied_manifest:
            warnings.append(
                "Snapshot does not include applied migration checksums; "
                "versioned checksum drift checks are limited."
            )

        pending = [
            self._planned_migration(m)
            for m in versioned
            if not self.snapshot_state.is_version_applied(m.version)
        ]
        checksum_drift = self._detect_versioned_drift(versioned)
        repeatables_pending = self._pending_repeatables(repeatables)
        already_applied_count = sum(
            1
            for migration in versioned
            if self.snapshot_state.is_version_applied(migration.version)
        )
        sql_validation = self._validate_sql(
            versioned=versioned,
            repeatables=repeatables,
            pending=pending,
            repeatables_pending=repeatables_pending,
        )
        if sql_validation.enabled and sql_validation.status == "FAIL":
            errors.append(SQL_VALIDATION_FAILURE_MESSAGE)

        return PlanData(
            snapshot_model=str(self.snapshot_state.snapshot_path),
            target_last_version=self.snapshot_state.last_version,
            target_installed_rank=optional_int(
                self.snapshot_state.metadata.get("migration", {}).get("installed_rank")
            ),
            pending=pending,
            repeatables_pending=repeatables_pending,
            checksum_drift=checksum_drift,
            already_applied_count=already_applied_count,
            warnings=warnings,
            errors=errors,
            sql_validation=sql_validation,
        )

    def _detect_versioned_drift(self, versioned: List[Migration]) -> List[ChecksumDrift]:
        """Return checksum mismatches for already-applied versioned scripts."""
        drift: List[ChecksumDrift] = []
        for migration in versioned:
            version = str(migration.version) if migration.version is not None else None
            if version is None:
                continue
            applied = self.snapshot_state.applied_by_version.get(version)
            if applied is None or applied.checksum is None:
                continue
            local_checksum = normalize_migration_checksum(migration.checksum)
            if local_checksum != applied.checksum:
                drift.append(
                    ChecksumDrift(
                        script=migration.script_name,
                        version=version,
                        expected_checksum=applied.checksum,
                        actual_checksum=local_checksum,
                    )
                )
        return drift

    def _pending_repeatables(self, repeatables: List[Migration]) -> List[PlannedMigration]:
        """Return repeatables missing from the snapshot or changed locally."""
        pending: List[PlannedMigration] = []
        for migration in repeatables:
            applied = self.snapshot_state.repeatables_by_script.get(migration.script_name)
            local_checksum = normalize_migration_checksum(migration.checksum)
            if applied is None or applied.checksum != local_checksum:
                pending.append(self._planned_migration(migration))
        return pending

    def _validate_sql(
        self,
        *,
        versioned: List[Migration],
        repeatables: List[Migration],
        pending: List[PlannedMigration],
        repeatables_pending: List[PlannedMigration],
    ) -> SqlValidationSummary:
        """Run validate-sql over planned files according to the selected scope."""
        if self.skip_validate_sql:
            return SqlValidationSummary(enabled=False, scope=self.validate_scope, status="SKIPPED")

        files = self._validation_files(versioned, repeatables, pending, repeatables_pending)
        if not files:
            return SqlValidationSummary(enabled=True, scope=self.validate_scope, status="PASS")

        validator = SqlValidator(self.dialect, validation_config=self.validation_config)
        result = validator.validate_files(files)
        status = "FAIL" if validator.should_fail(result) else "PASS"
        return SqlValidationSummary(
            enabled=True,
            scope=self.validate_scope,
            status=status,
            files_checked=getattr(result, "files_checked", len(files)),
            errors=getattr(result, "error_count", 0),
            warnings=getattr(result, "warning_count", 0),
            messages=_validation_messages(getattr(result, "violations", [])),
            findings=_validation_findings(result),
        )

    def _validation_files(
        self,
        versioned: List[Migration],
        repeatables: List[Migration],
        pending: List[PlannedMigration],
        repeatables_pending: List[PlannedMigration],
    ) -> List[Path]:
        """Return SQL files that should be passed to the validator."""
        if self.validate_scope == "all":
            migrations = versioned + repeatables
            return [m.path for m in migrations if _has_sql_path(m) and m.path is not None]

        files: List[Path] = []
        seen: set[Path] = set()
        for item in pending + repeatables_pending:
            path = Path(item.path)
            if path in seen or path.suffix.lower() != ".sql" or not path.exists():
                continue
            seen.add(path)
            files.append(path)
        return files

    @staticmethod
    def _planned_migration(migration: Migration) -> PlannedMigration:
        """Convert a migration script object to a report-friendly plan item."""
        return PlannedMigration(
            script=migration.script_name,
            version=str(migration.version) if migration.version is not None else None,
            description=str(migration.description or ""),
            type=migration_type_name(getattr(migration, "type", None)),
            checksum=normalize_migration_checksum(migration.checksum),
            path=str(migration.path or ""),
        )


def _has_sql_path(migration: Migration) -> bool:
    """Return True when the migration has an existing .sql file path."""
    path = getattr(migration, "path", None)
    return isinstance(path, Path) and path.suffix.lower() == ".sql" and path.exists()


def _validation_messages(violations: Any) -> List[str]:
    """Extract human-readable messages from validator violations."""
    messages: List[str] = []
    for violation in violations or []:
        message = getattr(violation, "message", None)
        if message:
            messages.append(str(message))
    return messages


def _validation_findings(result: Any) -> List[dict[str, Any]]:
    """Extract normalized SQL validation findings for plan output."""
    from core.ci.sql_validation import validation_result_to_finding_report

    report = validation_result_to_finding_report(result)
    return [finding.to_dict() for finding in report.findings]
