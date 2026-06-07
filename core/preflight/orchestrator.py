"""Preflight workflow orchestration."""

from __future__ import annotations

import time
from functools import cmp_to_key
from inspect import signature
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.migration.planning.models import SQL_VALIDATION_FAILURE_MESSAGE
from core.migration.version_utils import compare_versions
from core.preflight.docker import DockerRunner
from core.preflight.models import (
    ContainerMode,
    ContainerOptions,
    PreflightPhase,
    PreflightResult,
    ReplayOptions,
)
from core.preflight.replay import MigrationReplayRunner


class PreflightOrchestrator:
    """Coordinate planning, container lifecycle, and migration replay."""

    def __init__(
        self,
        *,
        config: Any,
        log: Any,
        plan_client: Any,
        scripts_dir: Path,
        recursive: bool,
        additional_scripts_dirs: List[Path],
        dir_recursive_map: Dict[Path, bool],
        docker_runner: Optional[DockerRunner] = None,
        client_factory: Optional[Callable[[Any, Any], Any]] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Store dependencies for the workflow."""
        self.config = config
        self.log = log
        self.plan_client = plan_client
        self.scripts_dir = scripts_dir
        self.recursive = recursive
        self.additional_scripts_dirs = additional_scripts_dirs
        self.dir_recursive_map = dir_recursive_map
        self.docker_runner = docker_runner or DockerRunner()
        self.client_factory = client_factory or self._default_client_factory
        self.sleep = sleep

    def run(
        self,
        *,
        snapshot_model: Path,
        container_options: ContainerOptions,
        replay_options: ReplayOptions,
        fail_on: str,
    ) -> PreflightResult:
        """Execute the preflight workflow."""
        result = PreflightResult(snapshot_model=str(snapshot_model), fail_on=fail_on)
        container_id: Optional[str] = None
        try:
            self._validate_inputs(
                snapshot_model=snapshot_model, container_options=container_options
            )
            plan_kwargs = {
                "snapshot_model": snapshot_model,
                "recursive": self.recursive,
                "additional_dirs": self.additional_scripts_dirs or None,
                "skip_validate_sql": False,
                "validate_scope": "pending",
            }
            if self._plan_accepts_scripts_dir():
                plan_kwargs["scripts_dir"] = self.scripts_dir
                plan_kwargs["dir_recursive_map"] = self.dir_recursive_map
            plan_result = self.plan_client.plan(**plan_kwargs)
            result.plan_result = plan_result
            plan_failed = not getattr(plan_result, "success", False)
            # A validate-sql-only failure is not blocking: it must not mark the plan
            # phase FAIL, or reporting would turn it into a blocking finding that fails
            # the run regardless of --fail-on. Its SQL findings flow through the plan
            # report with their own severities and are honored by the threshold.
            plan_blocking = plan_failed and not self._plan_failure_is_sql_validation_only(
                plan_result
            )
            result.add_phase(
                PreflightPhase(
                    name="plan",
                    status="FAIL" if plan_blocking else "PASS",
                    message=getattr(plan_result, "error_message", "") or "",
                    metadata={
                        "pending": len(getattr(plan_result, "pending_migrations", []) or []),
                        "repeatables_pending": len(
                            getattr(plan_result, "repeatables_pending", []) or []
                        ),
                    },
                )
            )
            if plan_blocking:
                return result

            if not replay_options.enabled:
                result.add_phase(
                    PreflightPhase(
                        name="replay",
                        status="SKIPPED",
                        message="Replay disabled by --skip-replay",
                    )
                )
                return result

            container_id = self.docker_runner.start(container_options)
            client = self._create_ready_client(container_options.wait_timeout_seconds)
            replay = MigrationReplayRunner(client=client, log=self.log).replay(
                scope=replay_options.scope
            )
            result.replayed_scripts = list(replay.scripts)
            result.add_phase(
                PreflightPhase(
                    name="replay",
                    status="PASS" if replay.success else "FAIL",
                    message=replay.error_message or "",
                    metadata={
                        "scope": replay.scope,
                        "scripts": len(replay.scripts),
                        "container": container_id,
                    },
                )
            )
            if replay_options.rehearse_rollback:
                # Gate on the replay phase, not aggregate result.success, so rollback
                # is rehearsed whenever the replay applied migrations.
                if replay.success:
                    versions = self._pending_versions(plan_result)
                    result.add_phase(self._rehearse_rollback(client, versions))
                else:
                    result.add_phase(
                        PreflightPhase(
                            name="rollback",
                            status="SKIPPED",
                            message="Skipped: prior phase failed",
                        )
                    )
            return result
        except Exception as exc:
            result.error_message = str(exc)
            return result
        finally:
            self.docker_runner.cleanup(container_id, container_options)

    @staticmethod
    def _plan_failure_is_sql_validation_only(plan_result: Any) -> bool:
        """Return True when the plan failed solely because validate-sql flagged findings.

        Such findings are re-evaluated against ``fail_on`` by the caller, so the
        workflow must still run replay/rollback instead of silently skipping them
        (e.g. ``--fail-on never`` would otherwise report success while replay was
        never executed). Runtime errors and checksum drift remain hard blockers.
        """
        # Prefer the structured property on PlanResult; fall back to string-matching
        # for duck-typed plan clients that don't implement the property.
        # Guard with isinstance(bool) so that auto-attribute objects (e.g. Mock) don't
        # bypass the fallback — only a genuine bool is treated as authoritative.
        prop = getattr(plan_result, "is_sql_validation_only_failure", None)
        if isinstance(prop, bool):
            return prop
        if getattr(plan_result, "error_message", None):
            return False
        if getattr(plan_result, "checksum_drift", None):
            return False
        plan_errors = list(getattr(plan_result, "plan_errors", None) or [])
        if not plan_errors:
            return False
        return all(error == SQL_VALIDATION_FAILURE_MESSAGE for error in plan_errors)

    @staticmethod
    def _pending_versions(plan_result: Any) -> List[str]:
        """Return the plan's pending versioned migration versions, newest first.

        These are exactly the versioned migrations the PR introduces. Repeatables
        carry no version and cannot be rolled back, so they are excluded.
        """
        pending = getattr(plan_result, "pending_migrations", None) or []
        versions = [
            str(getattr(migration, "version", "") or "")
            for migration in pending
            if getattr(migration, "version", None) is not None
        ]
        versions = [version for version in versions if version]
        versions.sort(key=cmp_to_key(compare_versions), reverse=True)
        return versions

    def _rehearse_rollback(self, client: Any, pending_versions: List[str]) -> PreflightPhase:
        """Roll back exactly the plan's pending migrations to exercise their undo scripts.

        Preflight validates a PR's plan, so rehearsal must exercise the undo of each
        migration the PR introduces — not the whole replayed history, not just the most
        recent migration, and not merely the latest N versions (which is wrong when the
        plan has out-of-order pending versions). Undo each pending version explicitly,
        newest first, and stop early on failure.
        """
        if not pending_versions:
            return PreflightPhase(
                name="rollback",
                status="SKIPPED",
                message="No versioned pending migrations to rehearse",
            )
        total_undone = 0
        for version in pending_versions:
            # Pass versions= to filter the applied-history view to this specific version.
            # The state manager filters applied_objects by version, so the undo command
            # sees it as the only applied migration and targets it directly — regardless
            # of what other (higher) versions are still applied in the container.
            # Bare undo() would pop the globally-newest applied version, which is wrong
            # for out-of-order pending migrations (e.g. pending V5,V7 while V10 exists).
            undo_result = client.undo(versions=version)
            if not getattr(undo_result, "success", False):
                return PreflightPhase(
                    name="rollback",
                    status="FAIL",
                    message=getattr(undo_result, "error_message", "") or "",
                    metadata={"undone_count": total_undone},
                )
            total_undone += int(getattr(undo_result, "undone_count", 0) or 0)
        if total_undone == 0:
            return PreflightPhase(
                name="rollback",
                status="FAIL",
                message="Undo reported success but rolled back 0 migrations — no undo scripts ran",
                metadata={"undone_count": 0},
            )
        return PreflightPhase(
            name="rollback",
            status="PASS",
            metadata={"undone_count": total_undone},
        )

    def _validate_inputs(
        self, *, snapshot_model: Path, container_options: ContainerOptions
    ) -> None:
        """Raise early if inputs are obviously invalid."""
        if not snapshot_model.is_file():
            raise ValueError(f"Snapshot model not found: {snapshot_model}")
        if container_options.mode == ContainerMode.MANAGED:
            self.docker_runner.check_docker_available()
        elif container_options.mode == ContainerMode.EXISTING:
            if not container_options.existing_name:
                raise ValueError("--container-existing is required for existing container mode")
            self.docker_runner.check_container_running(container_options.existing_name)

    @staticmethod
    def _default_client_factory(config: Any, log: Any) -> Any:
        """Create a DBLift client after the validation container is ready."""
        from api import DBLiftClient

        return DBLiftClient.from_config(config, logger=log)

    def _plan_accepts_scripts_dir(self) -> bool:
        """Return whether the configured plan client expects explicit script paths."""
        try:
            parameters = signature(self.plan_client.plan).parameters
        except (TypeError, ValueError):
            return False
        return "scripts_dir" in parameters

    @staticmethod
    def _probe_sql(client: Any) -> Optional[str]:
        """Return dialect-specific readiness SQL from provider quirks."""
        from db.provider_registry import ProviderRegistry as _ProviderRegistry

        provider = getattr(client, "provider", None)
        dialect = ""
        for candidate in (
            getattr(provider, "canonical_dialect_key", None),
            getattr(provider, "dialect", None),
            getattr(getattr(getattr(provider, "config", None), "database", None), "type", None),
        ):
            if isinstance(candidate, str) and candidate:
                dialect = candidate
                break
        return _ProviderRegistry.get_quirks(dialect).connection_probe_sql

    def _create_ready_client(self, timeout_seconds: int) -> Any:
        """Create a DB client, retrying until the validation database is ready."""
        deadline = time.monotonic() + timeout_seconds
        last_error: Optional[Exception] = None
        while True:
            try:
                client = self.client_factory(self.config, self.log)
                provider = getattr(client, "provider", None)
                connect = getattr(provider, "connect", None)
                probe = self._probe_sql(client)
                if callable(connect):
                    connect()
                if probe:
                    if provider and hasattr(provider, "execute_query"):
                        provider.execute_query(probe)
                return client
            except Exception as exc:
                last_error = exc
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Validation database did not become ready within "
                        f"{timeout_seconds} seconds: {last_error}"
                    ) from exc
                self.sleep(2)
