"""Models for the preflight deployment-readiness workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

PreflightStatus = Literal["PASS", "FAIL", "SKIPPED"]


class ContainerMode(str, Enum):
    """How preflight obtains a validation database container."""

    NONE = "none"
    MANAGED = "managed"
    EXISTING = "existing"


@dataclass(frozen=True)
class ContainerOptions:
    """Docker container options for preflight replay."""

    mode: ContainerMode = ContainerMode.NONE
    image: Optional[str] = None
    existing_name: Optional[str] = None
    name: Optional[str] = None
    ports: List[str] = field(default_factory=list)
    env: List[str] = field(default_factory=list)
    env_file: Optional[str] = None
    wait_timeout_seconds: int = 120
    keep: bool = False

    @property
    def managed(self) -> bool:
        """Return True when DBLift owns container cleanup."""
        return self.mode == ContainerMode.MANAGED


@dataclass(frozen=True)
class ReplayOptions:
    """Options controlling validation-container migration replay."""

    enabled: bool = True
    scope: str = "all"
    rehearse_rollback: bool = False


@dataclass(frozen=True)
class PreflightPhase:
    """One phase in the preflight workflow."""

    name: str
    status: PreflightStatus
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the phase for JSON and HTML reports."""
        payload: Dict[str, Any] = {"name": self.name, "status": self.status}
        if self.message:
            payload["message"] = self.message
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass
class PreflightResult:
    """Complete preflight workflow result."""

    snapshot_model: str
    fail_on: str
    phases: List[PreflightPhase] = field(default_factory=list)
    plan_result: Optional[Any] = None
    replayed_scripts: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    success_override: Optional[bool] = None

    @property
    def success(self) -> bool:
        """Return True when no phase failed and no runtime error was recorded.

        ``success_override`` lets the caller align this with a threshold-based
        verdict (e.g. ``--fail-on warning`` against plan findings) so logged
        status and exit code never disagree.
        """
        if self.success_override is not None:
            return self.success_override
        return self.error_message is None and all(phase.status != "FAIL" for phase in self.phases)

    def add_phase(self, phase: PreflightPhase) -> None:
        """Append one phase result."""
        self.phases.append(phase)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the preflight result."""
        return {
            "success": self.success,
            "snapshot_model": self.snapshot_model,
            "fail_on": self.fail_on,
            "phases": [phase.to_dict() for phase in self.phases],
            "replayed_scripts": list(self.replayed_scripts),
            "error": self.error_message,
        }
