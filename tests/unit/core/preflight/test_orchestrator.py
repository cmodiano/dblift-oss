import subprocess
from pathlib import Path
from unittest.mock import Mock, call, patch

from core.migration.planning.models import SQL_VALIDATION_FAILURE_MESSAGE
from core.preflight.models import ContainerMode, ContainerOptions, ReplayOptions
from core.preflight.orchestrator import PreflightOrchestrator


def test_orchestrator_runs_plan_and_skips_replay_when_requested(tmp_path):
    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")
    plan_result = Mock()
    plan_result.success = True
    plan_result.pending_migrations = []
    plan_result.repeatables_pending = []
    plan_client = Mock()
    plan_client.plan.return_value = plan_result

    result = PreflightOrchestrator(
        config=Mock(),
        log=Mock(),
        plan_client=plan_client,
        scripts_dir=tmp_path,
        recursive=True,
        additional_scripts_dirs=[],
        dir_recursive_map={},
        docker_runner=Mock(),
        client_factory=Mock(),
    ).run(
        snapshot_model=snapshot,
        container_options=ContainerOptions(),
        replay_options=ReplayOptions(enabled=False),
        fail_on="error",
    )

    assert result.success is True
    assert [phase.name for phase in result.phases] == ["plan", "replay"]
    assert result.phases[1].status == "SKIPPED"
    plan_client.plan.assert_called_once()


def test_orchestrator_omits_scripts_dir_for_bound_client_plan(tmp_path):
    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")
    plan_result = Mock()
    plan_result.success = True
    plan_result.pending_migrations = []
    plan_result.repeatables_pending = []

    class BoundPlanClient:
        def plan(self, **kwargs):
            if "scripts_dir" in kwargs:
                raise TypeError("scripts_dir is not a valid per-call override")
            return plan_result

    result = PreflightOrchestrator(
        config=Mock(),
        log=Mock(),
        plan_client=BoundPlanClient(),
        scripts_dir=tmp_path,
        recursive=True,
        additional_scripts_dirs=[],
        dir_recursive_map={},
        docker_runner=Mock(),
        client_factory=Mock(),
    ).run(
        snapshot_model=snapshot,
        container_options=ContainerOptions(),
        replay_options=ReplayOptions(enabled=False),
        fail_on="error",
    )

    assert result.success is True
    assert result.error_message is None


def test_orchestrator_starts_managed_container_before_client_factory(tmp_path):
    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")
    calls = []
    plan_result = Mock()
    plan_result.success = True
    plan_result.pending_migrations = []
    plan_result.repeatables_pending = []
    docker_runner = Mock()
    docker_runner.start.side_effect = lambda options: calls.append("docker") or "container-123"
    client = Mock()
    client.provider = Mock()

    def client_factory(config, log):
        calls.append("client")
        return client

    result = PreflightOrchestrator(
        config=Mock(),
        log=Mock(),
        plan_client=Mock(plan=Mock(return_value=plan_result)),
        scripts_dir=tmp_path,
        recursive=True,
        additional_scripts_dirs=[],
        dir_recursive_map={},
        docker_runner=docker_runner,
        client_factory=client_factory,
    ).run(
        snapshot_model=snapshot,
        container_options=ContainerOptions(
            mode=ContainerMode.MANAGED,
            image="artifactory/db/postgres:latest",
        ),
        replay_options=ReplayOptions(enabled=True),
        fail_on="error",
    )

    assert result.success is True
    assert calls == ["docker", "client"]
    docker_runner.cleanup.assert_called_once()


def _make_orchestrator(tmp_path, **kwargs):
    defaults = dict(
        config=Mock(),
        log=Mock(),
        plan_client=Mock(),
        scripts_dir=tmp_path,
        recursive=True,
        additional_scripts_dirs=[],
        dir_recursive_map={},
        docker_runner=Mock(),
        client_factory=Mock(),
    )
    defaults.update(kwargs)
    return PreflightOrchestrator(**defaults)


def test_missing_snapshot_model_sets_error_without_calling_plan(tmp_path):
    plan_client = Mock()
    orchestrator = _make_orchestrator(tmp_path, plan_client=plan_client)

    result = orchestrator.run(
        snapshot_model=tmp_path / "does_not_exist.json",
        container_options=ContainerOptions(),
        replay_options=ReplayOptions(enabled=False),
        fail_on="error",
    )

    assert result.error_message is not None
    assert "not found" in result.error_message
    plan_client.plan.assert_not_called()


def test_managed_mode_docker_unavailable_sets_error(tmp_path):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text("{}")
    docker_runner = Mock()
    docker_runner.check_docker_available.side_effect = RuntimeError(
        "Docker daemon is not available: connection refused"
    )
    orchestrator = _make_orchestrator(tmp_path, docker_runner=docker_runner)

    result = orchestrator.run(
        snapshot_model=snapshot,
        container_options=ContainerOptions(mode=ContainerMode.MANAGED, image="some-image:latest"),
        replay_options=ReplayOptions(enabled=True),
        fail_on="error",
    )

    assert result.error_message is not None
    assert "Docker daemon is not available" in result.error_message


def test_existing_mode_without_name_sets_error(tmp_path):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text("{}")
    orchestrator = _make_orchestrator(tmp_path)

    result = orchestrator.run(
        snapshot_model=snapshot,
        container_options=ContainerOptions(mode=ContainerMode.EXISTING, existing_name=None),
        replay_options=ReplayOptions(enabled=True),
        fail_on="error",
    )

    assert result.error_message is not None
    assert "required" in result.error_message


def test_existing_mode_dead_container_sets_error(tmp_path):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text("{}")
    docker_runner = Mock()
    docker_runner.check_container_running.side_effect = RuntimeError(
        "Container 'ci-db' is not running"
    )
    orchestrator = _make_orchestrator(tmp_path, docker_runner=docker_runner)

    result = orchestrator.run(
        snapshot_model=snapshot,
        container_options=ContainerOptions(mode=ContainerMode.EXISTING, existing_name="ci-db"),
        replay_options=ReplayOptions(enabled=True),
        fail_on="error",
    )

    assert result.error_message is not None
    assert "not running" in result.error_message


def test_orchestrator_retries_client_factory_until_database_ready(tmp_path):
    attempts = []
    plan_result = Mock()
    plan_result.success = True
    plan_result.pending_migrations = []
    plan_result.repeatables_pending = []

    def client_factory(config, log):
        attempts.append("try")
        if len(attempts) == 1:
            raise RuntimeError("database is starting")
        client = Mock()
        client.provider = Mock()
        return client

    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")
    result = PreflightOrchestrator(
        config=Mock(),
        log=Mock(),
        plan_client=Mock(plan=Mock(return_value=plan_result)),
        scripts_dir=tmp_path,
        recursive=True,
        additional_scripts_dirs=[],
        dir_recursive_map={},
        docker_runner=Mock(start=Mock(return_value="container-123"), cleanup=Mock()),
        client_factory=client_factory,
        sleep=lambda seconds: None,
    ).run(
        snapshot_model=snapshot,
        container_options=ContainerOptions(
            mode=ContainerMode.MANAGED,
            image="artifactory/db/postgres:latest",
            wait_timeout_seconds=5,
        ),
        replay_options=ReplayOptions(enabled=True),
        fail_on="error",
    )

    assert result.success is True
    assert len(attempts) == 2


def test_plan_failure_skips_docker_and_replay(tmp_path):
    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")
    plan_result = Mock()
    plan_result.success = False
    plan_result.pending_migrations = []
    plan_result.repeatables_pending = []
    plan_result.error_message = "pending migrations found"
    docker_runner = Mock()
    plan_client = Mock()
    plan_client.plan.return_value = plan_result

    orchestrator = _make_orchestrator(
        tmp_path, plan_client=plan_client, docker_runner=docker_runner
    )
    result = orchestrator.run(
        snapshot_model=snapshot,
        container_options=ContainerOptions(),
        replay_options=ReplayOptions(enabled=True),
        fail_on="error",
    )

    assert result.phases[0].status == "FAIL"
    assert len(result.phases) == 1
    docker_runner.start.assert_not_called()
    assert result.error_message is None
    assert result.success is False


def test_client_connection_timeout_sets_error_message(tmp_path, monkeypatch):
    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")
    plan_result = Mock()
    plan_result.success = True
    plan_result.pending_migrations = []
    plan_result.repeatables_pending = []

    # client_factory always fails
    def failing_client_factory(config, log):
        raise ConnectionError("DB down")

    # Make deadline expire immediately: first call returns 0 (sets deadline = 0 + timeout),
    # second call returns a value past the deadline.
    monotonic_values = iter([0.0, 9999.0])
    monkeypatch.setattr(
        "core.preflight.orchestrator.time.monotonic", lambda: next(monotonic_values)
    )

    orchestrator = _make_orchestrator(
        tmp_path,
        plan_client=Mock(plan=Mock(return_value=plan_result)),
        docker_runner=Mock(
            start=Mock(return_value="container-123"),
            cleanup=Mock(),
            check_docker_available=Mock(),
        ),
        client_factory=failing_client_factory,
        sleep=Mock(),
    )
    result = orchestrator.run(
        snapshot_model=snapshot,
        container_options=ContainerOptions(
            mode=ContainerMode.MANAGED,
            image="artifactory/db/postgres:latest",
            wait_timeout_seconds=30,
        ),
        replay_options=ReplayOptions(enabled=True),
        fail_on="error",
    )

    assert result.error_message is not None
    assert "did not become ready" in result.error_message
    assert "30 seconds" in result.error_message  # 30 = timeout_seconds used in test
    assert result.success is False


def test_docker_start_exception_produces_error_result(tmp_path):
    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")
    plan_result = Mock()
    plan_result.success = True
    plan_result.pending_migrations = []
    plan_result.repeatables_pending = []

    docker_runner = Mock()
    docker_runner.start.side_effect = subprocess.CalledProcessError(1, "docker run")
    docker_runner.check_docker_available = Mock()

    orchestrator = _make_orchestrator(
        tmp_path,
        plan_client=Mock(plan=Mock(return_value=plan_result)),
        docker_runner=docker_runner,
    )
    result = orchestrator.run(
        snapshot_model=snapshot,
        container_options=ContainerOptions(
            mode=ContainerMode.MANAGED,
            image="artifactory/db/postgres:latest",
        ),
        replay_options=ReplayOptions(enabled=True),
        fail_on="error",
    )

    assert result.error_message is not None
    assert "docker run" in result.error_message
    assert result.success is False


def test_health_probe_retries_when_execute_query_fails_then_succeeds(tmp_path, monkeypatch):
    """A failing execute_query probe triggers retry; second attempt returns client."""
    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")
    plan_result = Mock()
    plan_result.success = True
    plan_result.pending_migrations = []
    plan_result.repeatables_pending = []

    provider = Mock()
    provider.dialect = "postgresql"
    client = Mock()
    client.provider = provider

    # First execute_query fails, second succeeds
    provider.execute_query.side_effect = [Exception("not ready"), None]

    # client_factory always returns the same client
    client_factory = Mock(return_value=client)

    # monkeypatch monotonic: [0.0 (set deadline), 1.0 (check after failure), 2.0 (check after success)]
    monotonic_values = iter([0.0, 1.0, 2.0])
    monkeypatch.setattr(
        "core.preflight.orchestrator.time.monotonic", lambda: next(monotonic_values)
    )

    sleep_mock = Mock()
    result = PreflightOrchestrator(
        config=Mock(),
        log=Mock(),
        plan_client=Mock(plan=Mock(return_value=plan_result)),
        scripts_dir=tmp_path,
        recursive=True,
        additional_scripts_dirs=[],
        dir_recursive_map={},
        docker_runner=Mock(start=Mock(return_value="container-123"), cleanup=Mock()),
        client_factory=client_factory,
        sleep=sleep_mock,
    ).run(
        snapshot_model=snapshot,
        container_options=ContainerOptions(
            mode=ContainerMode.MANAGED,
            image="artifactory/db/postgres:latest",
            wait_timeout_seconds=30,
        ),
        replay_options=ReplayOptions(enabled=True),
        fail_on="error",
    )

    # Retry happened (sleep was called once)
    sleep_mock.assert_called_once()
    # Client was eventually returned (run succeeded)
    assert result.error_message is None
    assert result.success is True


def test_health_probe_skips_when_provider_has_no_execute_query(tmp_path):
    """No execute_query on provider → probe is skipped, client returned normally."""
    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")
    plan_result = Mock()
    plan_result.success = True
    plan_result.pending_migrations = []
    plan_result.repeatables_pending = []

    provider = Mock(spec=["connect", "dialect"])  # no execute_query attribute
    provider.dialect = "postgresql"
    client = Mock()
    client.provider = provider

    result = PreflightOrchestrator(
        config=Mock(),
        log=Mock(),
        plan_client=Mock(plan=Mock(return_value=plan_result)),
        scripts_dir=tmp_path,
        recursive=True,
        additional_scripts_dirs=[],
        dir_recursive_map={},
        docker_runner=Mock(start=Mock(return_value="container-123"), cleanup=Mock()),
        client_factory=Mock(return_value=client),
    ).run(
        snapshot_model=snapshot,
        container_options=ContainerOptions(
            mode=ContainerMode.MANAGED,
            image="artifactory/db/postgres:latest",
        ),
        replay_options=ReplayOptions(enabled=True),
        fail_on="error",
    )

    assert result.error_message is None
    assert result.success is True


def test_health_probe_uses_oracle_dual_syntax(tmp_path):
    """Oracle dialect probe SQL is 'SELECT 1 FROM DUAL' via ProviderRegistry quirks."""
    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")
    plan_result = Mock()
    plan_result.success = True
    plan_result.pending_migrations = []
    plan_result.repeatables_pending = []

    provider = Mock()
    provider.dialect = "oracle"
    client = Mock()
    client.provider = provider

    with patch("db.provider_registry.ProviderRegistry.get_quirks") as mock_get_quirks:
        quirks = Mock()
        quirks.connection_probe_sql = "SELECT 1 FROM DUAL"
        mock_get_quirks.return_value = quirks

        PreflightOrchestrator(
            config=Mock(),
            log=Mock(),
            plan_client=Mock(plan=Mock(return_value=plan_result)),
            scripts_dir=tmp_path,
            recursive=True,
            additional_scripts_dirs=[],
            dir_recursive_map={},
            docker_runner=Mock(start=Mock(return_value="container-123"), cleanup=Mock()),
            client_factory=Mock(return_value=client),
        ).run(
            snapshot_model=snapshot,
            container_options=ContainerOptions(
                mode=ContainerMode.MANAGED,
                image="artifactory/db/oracle:latest",
            ),
            replay_options=ReplayOptions(enabled=True),
            fail_on="error",
        )

    mock_get_quirks.assert_called_with("oracle")
    provider.execute_query.assert_called_once_with("SELECT 1 FROM DUAL")


def test_health_probe_uses_provider_canonical_dialect_key():
    """SQLAlchemy providers expose canonical_dialect_key instead of dialect."""
    provider = Mock()
    provider.canonical_dialect_key = "db2"
    client = Mock(provider=provider)

    with patch("db.provider_registry.ProviderRegistry.get_quirks") as mock_get_quirks:
        quirks = Mock(connection_probe_sql="SELECT 1 FROM SYSIBM.SYSDUMMY1")
        mock_get_quirks.return_value = quirks

        probe = PreflightOrchestrator._probe_sql(client)

    assert probe == "SELECT 1 FROM SYSIBM.SYSDUMMY1"
    mock_get_quirks.assert_called_once_with("db2")


def _make_replay_orchestrator(tmp_path, mock_client, plan_success=True, pending_versions=None):
    """Helper: orchestrator with a successful plan and the given mock client."""
    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")
    plan_result = Mock()
    plan_result.success = plan_success
    plan_result.pending_migrations = [Mock(version=v) for v in (pending_versions or [])]
    plan_result.repeatables_pending = []
    plan_result.error_message = "" if plan_success else "plan failed"
    return (
        snapshot,
        _make_orchestrator(
            tmp_path,
            plan_client=Mock(plan=Mock(return_value=plan_result)),
            docker_runner=Mock(start=Mock(return_value="container-123"), cleanup=Mock()),
            client_factory=lambda config, log: mock_client,
        ),
    )


def test_rollback_phase_added_when_flag_set_and_replay_passes(tmp_path):
    undo_result = Mock()
    undo_result.success = True
    undo_result.undone_count = 3
    undo_result.error_message = None

    mock_client = Mock()
    mock_client.provider = Mock()
    mock_client.undo.return_value = undo_result

    replay_result = Mock()
    replay_result.success = True
    replay_result.scripts = ["V1__init.sql"]
    replay_result.error_message = None
    replay_result.scope = "all"

    snapshot, orchestrator = _make_replay_orchestrator(
        tmp_path, mock_client, pending_versions=["1"]
    )

    with patch("core.preflight.orchestrator.MigrationReplayRunner") as MockReplayRunner:
        MockReplayRunner.return_value.replay.return_value = replay_result
        result = orchestrator.run(
            snapshot_model=snapshot,
            container_options=ContainerOptions(mode=ContainerMode.MANAGED, image="db:latest"),
            replay_options=ReplayOptions(enabled=True, rehearse_rollback=True),
            fail_on="error",
        )

    assert [phase.name for phase in result.phases] == ["plan", "replay", "rollback"]
    rollback = result.phases[2]
    assert rollback.status == "PASS"
    assert rollback.metadata["undone_count"] == 3
    mock_client.undo.assert_called_once_with(versions="1")


def test_rollback_phase_skipped_when_prior_phase_failed(tmp_path):
    mock_client = Mock()
    mock_client.provider = Mock()

    replay_result = Mock()
    replay_result.success = False
    replay_result.scripts = []
    replay_result.error_message = "migration failed"
    replay_result.scope = "all"

    snapshot, orchestrator = _make_replay_orchestrator(tmp_path, mock_client)

    with patch("core.preflight.orchestrator.MigrationReplayRunner") as MockReplayRunner:
        MockReplayRunner.return_value.replay.return_value = replay_result
        result = orchestrator.run(
            snapshot_model=snapshot,
            container_options=ContainerOptions(mode=ContainerMode.MANAGED, image="db:latest"),
            replay_options=ReplayOptions(enabled=True, rehearse_rollback=True),
            fail_on="error",
        )

    assert [phase.name for phase in result.phases] == ["plan", "replay", "rollback"]
    rollback = result.phases[2]
    assert rollback.status == "SKIPPED"
    assert "prior phase failed" in rollback.message
    mock_client.undo.assert_not_called()


def test_rollback_phase_absent_when_flag_not_set(tmp_path):
    mock_client = Mock()
    mock_client.provider = Mock()

    replay_result = Mock()
    replay_result.success = True
    replay_result.scripts = []
    replay_result.error_message = None
    replay_result.scope = "all"

    snapshot, orchestrator = _make_replay_orchestrator(tmp_path, mock_client)

    with patch("core.preflight.orchestrator.MigrationReplayRunner") as MockReplayRunner:
        MockReplayRunner.return_value.replay.return_value = replay_result
        result = orchestrator.run(
            snapshot_model=snapshot,
            container_options=ContainerOptions(mode=ContainerMode.MANAGED, image="db:latest"),
            replay_options=ReplayOptions(enabled=True, rehearse_rollback=False),
            fail_on="error",
        )

    assert not any(phase.name == "rollback" for phase in result.phases)
    mock_client.undo.assert_not_called()


def test_rollback_phase_fail_when_undo_returns_failure(tmp_path):
    undo_result = Mock()
    undo_result.success = False
    undo_result.undone_count = 0
    undo_result.error_message = "undo failed"

    mock_client = Mock()
    mock_client.provider = Mock()
    mock_client.undo.return_value = undo_result

    replay_result = Mock()
    replay_result.success = True
    replay_result.scripts = ["V1__init.sql"]
    replay_result.error_message = None
    replay_result.scope = "all"

    snapshot, orchestrator = _make_replay_orchestrator(
        tmp_path, mock_client, pending_versions=["1"]
    )

    with patch("core.preflight.orchestrator.MigrationReplayRunner") as MockReplayRunner:
        MockReplayRunner.return_value.replay.return_value = replay_result
        result = orchestrator.run(
            snapshot_model=snapshot,
            container_options=ContainerOptions(mode=ContainerMode.MANAGED, image="db:latest"),
            replay_options=ReplayOptions(enabled=True, rehearse_rollback=True),
            fail_on="error",
        )

    rollback = next(p for p in result.phases if p.name == "rollback")
    assert rollback.status == "FAIL"
    assert "undo failed" in rollback.message


def test_rollback_phase_exception_sets_error_message(tmp_path):
    mock_client = Mock()
    mock_client.provider = Mock()
    mock_client.undo.side_effect = RuntimeError("undo exploded")

    replay_result = Mock()
    replay_result.success = True
    replay_result.scripts = ["V1__init.sql"]
    replay_result.error_message = None
    replay_result.scope = "all"

    snapshot, orchestrator = _make_replay_orchestrator(
        tmp_path, mock_client, pending_versions=["1"]
    )

    with patch("core.preflight.orchestrator.MigrationReplayRunner") as MockReplayRunner:
        MockReplayRunner.return_value.replay.return_value = replay_result
        result = orchestrator.run(
            snapshot_model=snapshot,
            container_options=ContainerOptions(mode=ContainerMode.MANAGED, image="db:latest"),
            replay_options=ReplayOptions(enabled=True, rehearse_rollback=True),
            fail_on="error",
        )

    assert result.error_message is not None
    assert "undo exploded" in result.error_message
    assert result.success is False
    assert not any(phase.name == "rollback" for phase in result.phases)


def test_sql_validation_only_plan_failure_still_runs_replay(tmp_path):
    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")

    plan_result = Mock()
    plan_result.success = False
    plan_result.error_message = ""
    plan_result.checksum_drift = []
    plan_result.plan_errors = [SQL_VALIDATION_FAILURE_MESSAGE]
    plan_result.pending_migrations = []
    plan_result.repeatables_pending = []

    replay_result = Mock()
    replay_result.success = True
    replay_result.scripts = ["V1__init.sql"]
    replay_result.error_message = None
    replay_result.scope = "all"

    docker_runner = Mock(start=Mock(return_value="container-123"), cleanup=Mock())
    orchestrator = _make_orchestrator(
        tmp_path,
        plan_client=Mock(plan=Mock(return_value=plan_result)),
        docker_runner=docker_runner,
        client_factory=lambda config, log: Mock(provider=Mock()),
    )

    with patch("core.preflight.orchestrator.MigrationReplayRunner") as MockReplayRunner:
        MockReplayRunner.return_value.replay.return_value = replay_result
        result = orchestrator.run(
            snapshot_model=snapshot,
            container_options=ContainerOptions(mode=ContainerMode.MANAGED, image="db:latest"),
            replay_options=ReplayOptions(enabled=True),
            fail_on="never",
        )

    # validate-sql-only failure must not silently skip replay, and the plan phase
    # must not be a blocking FAIL (reporting would otherwise hard-fail --fail-on never)
    docker_runner.start.assert_called_once()
    replay_phase = next(p for p in result.phases if p.name == "replay")
    assert replay_phase.status == "PASS"
    plan_phase = next(p for p in result.phases if p.name == "plan")
    assert plan_phase.status == "PASS"


def test_rollback_rehearsed_after_sql_validation_only_plan_failure(tmp_path):
    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")

    plan_result = Mock()
    plan_result.success = False
    plan_result.error_message = ""
    plan_result.checksum_drift = []
    plan_result.plan_errors = [SQL_VALIDATION_FAILURE_MESSAGE]
    plan_result.pending_migrations = [Mock(version="1")]
    plan_result.repeatables_pending = []

    replay_result = Mock()
    replay_result.success = True
    replay_result.scripts = ["V1__init.sql"]
    replay_result.error_message = None
    replay_result.scope = "all"

    undo_result = Mock()
    undo_result.success = True
    undo_result.undone_count = 1
    undo_result.error_message = None
    mock_client = Mock(provider=Mock())
    mock_client.undo.return_value = undo_result

    orchestrator = _make_orchestrator(
        tmp_path,
        plan_client=Mock(plan=Mock(return_value=plan_result)),
        docker_runner=Mock(start=Mock(return_value="container-123"), cleanup=Mock()),
        client_factory=lambda config, log: mock_client,
    )

    with patch("core.preflight.orchestrator.MigrationReplayRunner") as MockReplayRunner:
        MockReplayRunner.return_value.replay.return_value = replay_result
        result = orchestrator.run(
            snapshot_model=snapshot,
            container_options=ContainerOptions(mode=ContainerMode.MANAGED, image="db:latest"),
            replay_options=ReplayOptions(enabled=True, rehearse_rollback=True),
            fail_on="never",
        )

    # a non-blocking validate-sql plan failure must not suppress rollback rehearsal
    plan_phase = next(p for p in result.phases if p.name == "plan")
    assert plan_phase.status == "PASS"
    rollback = next(p for p in result.phases if p.name == "rollback")
    assert rollback.status == "PASS"
    mock_client.undo.assert_called_once_with(versions="1")


def test_runtime_plan_error_still_skips_replay(tmp_path):
    snapshot = tmp_path / "env.snapshot.json"
    snapshot.write_text("{}")

    plan_result = Mock()
    plan_result.success = False
    plan_result.error_message = "boom"
    plan_result.checksum_drift = []
    plan_result.plan_errors = []
    plan_result.pending_migrations = []
    plan_result.repeatables_pending = []

    docker_runner = Mock(start=Mock(return_value="container-123"), cleanup=Mock())
    orchestrator = _make_orchestrator(
        tmp_path,
        plan_client=Mock(plan=Mock(return_value=plan_result)),
        docker_runner=docker_runner,
        client_factory=lambda config, log: Mock(provider=Mock()),
    )

    result = orchestrator.run(
        snapshot_model=snapshot,
        container_options=ContainerOptions(mode=ContainerMode.MANAGED, image="db:latest"),
        replay_options=ReplayOptions(enabled=True),
        fail_on="never",
    )

    docker_runner.start.assert_not_called()
    assert [phase.name for phase in result.phases] == ["plan"]


def test_rehearse_rollback_undoes_only_plan_pending_migrations(tmp_path):
    undo_result = Mock()
    undo_result.success = True
    undo_result.undone_count = 1
    undo_result.error_message = None

    mock_client = Mock()
    mock_client.provider = Mock()
    mock_client.undo.return_value = undo_result

    # scope=all replays the whole history (V1..V10), but the plan's pending set is the
    # out-of-order pair V2 and V4 (V10 already applied). Rehearsal must undo exactly
    # those two versions — not the latest 2 replayed (V10, V9), not just the last one.
    replay_result = Mock()
    replay_result.success = True
    replay_result.scripts = [f"V{n}__m.sql" for n in range(1, 11)]
    replay_result.error_message = None
    replay_result.scope = "all"

    snapshot, orchestrator = _make_replay_orchestrator(
        tmp_path, mock_client, pending_versions=["2", "4"]
    )

    with patch("core.preflight.orchestrator.MigrationReplayRunner") as MockReplayRunner:
        MockReplayRunner.return_value.replay.return_value = replay_result
        result = orchestrator.run(
            snapshot_model=snapshot,
            container_options=ContainerOptions(mode=ContainerMode.MANAGED, image="db:latest"),
            replay_options=ReplayOptions(enabled=True, rehearse_rollback=True),
            fail_on="error",
        )

    # undo exactly the pending versions, newest first — not the latest replayed versions
    assert mock_client.undo.call_args_list == [call(versions="4"), call(versions="2")]
    rollback = next(p for p in result.phases if p.name == "rollback")
    assert rollback.status == "PASS"
    assert rollback.metadata["undone_count"] == 2
