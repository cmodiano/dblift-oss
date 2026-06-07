"""Offline plan command implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from core.logger.results import PlanResult
from core.migration.planning.plan_builder import PlanBuilder
from core.migration.planning.snapshot_state import SnapshotMigrationState

from .base_command import BaseCommand


class PlanCommand(BaseCommand):
    """Build a migration plan from a committed DBLift snapshot."""

    def execute(
        self,
        scripts_dir: Path,
        snapshot_model: Path,
        recursive: Optional[bool] = None,
        additional_dirs: Optional[List[Path]] = None,
        dir_recursive_map: Optional[Dict[Path, bool]] = None,
        skip_validate_sql: bool = False,
        validate_scope: str = "pending",
    ) -> PlanResult:
        """Build the offline plan without touching the database provider."""
        result = PlanResult()
        result.snapshot_model = str(snapshot_model)
        result.target_schema = str(
            getattr(getattr(self.config, "database", None), "schema", "") or ""
        )

        try:
            snapshot_state = SnapshotMigrationState.from_path(snapshot_model)
            builder = PlanBuilder(
                scripts_dir=scripts_dir,
                snapshot_state=snapshot_state,
                script_manager=self.script_manager,
                dialect=str(
                    getattr(
                        getattr(self.config, "database", None),
                        "type",
                        "postgresql",  # lint: allow-dialect-string: default validation dialect
                    )
                ),
                recursive=True if recursive is None else recursive,
                additional_dirs=additional_dirs,
                dir_recursive_map=dir_recursive_map,
                skip_validate_sql=skip_validate_sql,
                validate_scope=validate_scope,
                validation_config=getattr(self.config, "validation", None),
            )
            plan = builder.build()
            result.apply_plan_data(plan)
            result.complete()
            return result
        except Exception as exc:
            result.set_error(f"Plan operation failed: {exc}")
            result.complete()
            return result
