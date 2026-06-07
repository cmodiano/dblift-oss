"""Replay migrations against the preflight target database."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

VALID_REPLAY_SCOPES = {"all", "planned"}


@dataclass
class MigrationReplayResult:
    """Result of replaying migrations in a validation container."""

    success: bool = True
    scope: str = "all"
    scripts: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    raw_result: Optional[Any] = None


class MigrationReplayRunner:
    """Execute DBLift migrations against the validation database."""

    def __init__(self, *, client: Any, log: Any) -> None:
        """Store replay dependencies."""
        self.client = client
        self.log = log

    def replay(self, *, scope: str) -> MigrationReplayResult:
        """Run DBLift migrate and summarize the throwaway-container replay.

        ``scope`` documents the expected container state:
        - ``all`` means the container is empty, so migrate should apply every script.
        - ``planned`` means the container is preloaded with history matching the snapshot,
          so migrate should apply only the delta.
        """
        if scope not in VALID_REPLAY_SCOPES:
            raise ValueError(f"Invalid replay scope: {scope}")
        try:
            migrate_result = self.client.migrate()
            migrations = getattr(migrate_result, "migrations", [])
            try:
                migration_list = list(migrations)
            except TypeError:
                migration_list = []
            scripts = [str(getattr(migration, "script", "")) for migration in migration_list]
            success = bool(getattr(migrate_result, "success", True))
            raw_error_message = getattr(migrate_result, "error_message", None)
            error_message = raw_error_message if isinstance(raw_error_message, str) else None
            return MigrationReplayResult(
                success=success,
                scope=scope,
                scripts=[script for script in scripts if script],
                error_message=error_message,
                raw_result=migrate_result,
            )
        except Exception as exc:
            return MigrationReplayResult(success=False, scope=scope, error_message=str(exc))
