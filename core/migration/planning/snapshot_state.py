"""Load migration state from a DBLift schema snapshot."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Set

from core.migration.migration import normalize_migration_checksum
from core.migration.planning._coercion import optional_int
from core.migration.planning.models import AppliedMigrationState, AppliedRepeatableState
from core.migration.version_utils import is_migration_success


@dataclass(frozen=True)
class SnapshotMigrationState:
    """Migration state extracted from a snapshot model file."""

    snapshot_path: Path
    metadata: Dict[str, Any]
    last_version: Optional[str]
    applied_versions: Set[str]
    applied_by_version: Dict[str, AppliedMigrationState] = field(default_factory=dict)
    repeatables_by_script: Dict[str, AppliedRepeatableState] = field(default_factory=dict)
    has_applied_manifest: bool = False

    @property
    def applied_checksums_by_version(self) -> Dict[str, int]:
        """Return stored checksums for applied versioned migrations."""
        return {
            version: applied.checksum
            for version, applied in self.applied_by_version.items()
            if applied.checksum is not None
        }

    def is_version_applied(self, version: Optional[str]) -> bool:
        """Return True when a version is present in the snapshot state."""
        return bool(version) and str(version) in self.applied_versions

    @classmethod
    def from_path(cls, snapshot_path: Path) -> "SnapshotMigrationState":
        """Load migration state from a DBLift snapshot model path."""
        path = Path(snapshot_path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Could not read snapshot model '{path}': {exc}") from exc

        if not isinstance(raw, dict):
            raise ValueError(f"Snapshot model '{path}' must contain a JSON object")
        metadata = raw.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError(f"Snapshot model '{path}' is missing metadata")
        migration_meta = metadata.get("migration")
        if not isinstance(migration_meta, dict):
            raise ValueError(f"Snapshot model '{path}' is missing metadata.migration")

        applied_by_version = _load_applied_manifest(migration_meta)
        has_applied_manifest = "applied" in migration_meta
        legacy_versions = {
            str(version)
            for version in migration_meta.get("applied_versions", [])
            if version is not None
        }
        applied_versions = set(applied_by_version) if has_applied_manifest else legacy_versions

        return cls(
            snapshot_path=path,
            metadata=metadata,
            last_version=_optional_str(migration_meta.get("last_version")),
            applied_versions=applied_versions,
            applied_by_version=applied_by_version,
            repeatables_by_script=_load_repeatables(migration_meta),
            has_applied_manifest=has_applied_manifest,
        )


def _load_applied_manifest(migration_meta: Dict[str, Any]) -> Dict[str, AppliedMigrationState]:
    """Load the enriched versioned migration manifest, if present."""
    applied_by_version: Dict[str, AppliedMigrationState] = {}
    for raw in migration_meta.get("applied", []) or []:
        if not isinstance(raw, dict):
            continue
        version = _optional_str(raw.get("version"))
        if not version:
            continue
        success_raw = raw.get("success", True)
        if not is_migration_success(success_raw):
            continue
        applied_by_version[version] = AppliedMigrationState(
            version=version,
            script=str(raw.get("script") or ""),
            checksum=normalize_migration_checksum(raw.get("checksum")),
            installed_rank=optional_int(raw.get("installed_rank")),
            installed_on=_optional_str(raw.get("installed_on")),
            type=str(raw.get("type") or ""),
            success=True,
        )
    return applied_by_version


def _load_repeatables(migration_meta: Dict[str, Any]) -> Dict[str, AppliedRepeatableState]:
    """Load repeatable migration checksums from snapshot metadata."""
    repeatables: Dict[str, AppliedRepeatableState] = {}
    for raw in migration_meta.get("repeatables", []) or []:
        if not isinstance(raw, dict):
            continue
        script = str(raw.get("script") or "")
        if not script:
            continue
        repeatables[script] = AppliedRepeatableState(
            script=script,
            checksum=normalize_migration_checksum(raw.get("checksum")),
            installed_rank=optional_int(raw.get("installed_rank")),
            installed_on=_optional_str(raw.get("installed_on")),
        )
    return repeatables


def _optional_str(value: Any) -> Optional[str]:
    """Return value as a string while preserving None."""
    if value is None:
        return None
    return str(value)
