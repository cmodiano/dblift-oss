"""CosmosDB Migration Plan Models.

Data classes representing migration plan steps and plans for CosmosDB SDK operations.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MigrationPlanStep:
    """Represents a single step in a migration plan."""

    sql: str
    operation_type: str
    sdk_operation: Optional[str] = None
    python_code: Optional[str] = None
    description: str = ""
    warning: Optional[str] = None
    note: Optional[str] = None
    is_sdk_required: bool = False
    estimated_ru_impact: Optional[int] = None
    undo_sql: Optional[str] = None


@dataclass
class MigrationPlan:
    """Represents a complete migration plan with dry-run information."""

    steps: List[MigrationPlanStep] = field(default_factory=list)
    total_ru_impact: int = 0
    has_destructive_operations: bool = False
    has_sdk_operations: bool = False

    def add_step(self, step: MigrationPlanStep) -> None:
        """Add a step to the migration plan."""
        self.steps.append(step)
        if step.estimated_ru_impact:
            self.total_ru_impact += step.estimated_ru_impact
        if step.warning and "DELETE" in step.warning.upper():
            self.has_destructive_operations = True
        if step.is_sdk_required:
            self.has_sdk_operations = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "steps": [
                {
                    "sql": s.sql,
                    "operation_type": s.operation_type,
                    "sdk_operation": s.sdk_operation,
                    "python_code": s.python_code,
                    "description": s.description,
                    "warning": s.warning,
                    "note": s.note,
                    "is_sdk_required": s.is_sdk_required,
                    "estimated_ru_impact": s.estimated_ru_impact,
                    "undo_sql": s.undo_sql,
                }
                for s in self.steps
            ],
            "total_ru_impact": self.total_ru_impact,
            "has_destructive_operations": self.has_destructive_operations,
            "has_sdk_operations": self.has_sdk_operations,
        }
