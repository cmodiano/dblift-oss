from core.preflight.models import (
    ContainerMode,
    ContainerOptions,
    PreflightPhase,
    PreflightResult,
    ReplayOptions,
)


def test_result_succeeds_when_all_phases_pass():
    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="error",
        phases=[
            PreflightPhase(name="plan", status="PASS"),
            PreflightPhase(name="replay", status="PASS"),
        ],
    )

    assert result.success is True


def test_result_fails_when_phase_fails():
    result = PreflightResult(
        snapshot_model="env.snapshot.json",
        fail_on="error",
        phases=[
            PreflightPhase(name="plan", status="PASS"),
            PreflightPhase(name="replay", status="FAIL", message="syntax error"),
        ],
    )

    assert result.success is False


def test_container_options_default_to_no_container():
    options = ContainerOptions()

    assert options.mode == ContainerMode.NONE
    assert options.managed is False


def test_replay_options_default_to_all_scope():
    options = ReplayOptions()

    assert options.enabled is True
    assert options.scope == "all"
