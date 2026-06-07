"""Types, options, and constants for the export-schema command.

Extracted from export_schema_command.py (story 20-16) to reduce file size.
"""

import datetime as _dt
from dataclasses import dataclass, field
from datetime import timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from core.introspection.base_introspector import BaseIntrospector
    from core.migration.snapshots.schema_snapshot import SchemaSnapshotPayload
    from core.migration.snapshots.schema_snapshot_service import SchemaSnapshotService
    from db.base_provider import BaseProvider

# Canonical list of the 17 object-type keys used across snapshot payloads and typed_lists dicts.
_OBJECT_TYPE_KEYS = [
    "tables",
    "views",
    "indexes",
    "sequences",
    "triggers",
    "events",
    "procedures",
    "functions",
    "packages",
    "modules",
    "synonyms",
    "user_defined_types",
    "extensions",
    "foreign_data_wrappers",
    "foreign_servers",
    "database_links",
    "linked_servers",
]

# Object types that follow the simple pattern: iterate + schema_matches filter.
_SCHEMA_FILTERED_TYPES = [
    "tables",
    "views",
    "sequences",
    "triggers",
    "events",
    "packages",
    "modules",
    "procedures",
    "functions",
    "synonyms",
    "user_defined_types",
]

# Object types with no schema filter (database-global).
_GLOBAL_TYPES = ["foreign_data_wrappers", "foreign_servers", "database_links", "linked_servers"]


def _json_default(obj: Any) -> Any:
    """Serializer for objects not handled by default json encoder."""
    if isinstance(obj, (_dt.datetime, _dt.date, _dt.time)):
        if isinstance(obj, _dt.datetime) and obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.isoformat()
    if isinstance(obj, Enum):
        return getattr(obj, "value", obj.name)
    return str(obj)


@dataclass
class ExportSchemaOptions:
    """Configuration options for the export_schema command.

    Groups all optional parameters of export_schema() to simplify
    the function signature and facilitate future extensions.
    """

    # Output options
    output: Optional[str] = None
    output_dir: Optional[str] = None
    split_by_type: bool = False
    include_drops: bool = False
    description: Optional[str] = None

    # Data source
    source: str = "live-database"
    snapshot_model: Optional[str] = None

    # Object filters
    tables: Optional[str] = None
    types: Optional[str] = None
    schema: Optional[str] = None
    unmanaged_only: bool = False
    managed_only: bool = False

    # Version/tag filters
    tags: Optional[str] = None
    exclude_tags: Optional[str] = None
    versions: Optional[str] = None
    exclude_versions: Optional[str] = None
    target_version: Optional[str] = None

    # Migration directories
    scripts_dir: Optional[Path] = None
    additional_scripts_dirs: Optional[List[Path]] = None
    dir_recursive_map: Optional[Dict[Path, bool]] = None
    recursive: bool = True


@dataclass
class ExportExecutionState:
    """Mutable pipeline state accumulated during a single SchemaExporter.run() invocation.

    Encapsulates the 10 intermediate attributes that were previously spread across
    SchemaExporter.__init__ (SIMP-39).  All fields default to None / [] so that
    SchemaExporter.__init__ remains a thin constructor.
    """

    filters: List[str] = field(default_factory=list)
    provider: Optional["BaseProvider"] = None
    introspector: Optional["BaseIntrospector"] = None
    snapshot_service: Optional["SchemaSnapshotService"] = None
    schema_version: Optional[str] = None
    target_schema: Optional[str] = None
    dialect: Optional[str] = None
    database_url: Optional[str] = None
    database_url_masked: Optional[str] = None
    schema_payload: Optional["SchemaSnapshotPayload"] = None


class _ExportAborted(Exception):
    """Internal signal: error already logged, run() should return False without re-logging."""
