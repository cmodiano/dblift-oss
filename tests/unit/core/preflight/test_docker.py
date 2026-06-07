import subprocess
from unittest.mock import Mock

import pytest

from core.preflight.docker import DockerRunner
from core.preflight.models import ContainerMode, ContainerOptions


def test_start_managed_container_builds_docker_run_command():
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        result = Mock()
        result.stdout = "container-123\n"
        result.returncode = 0
        return result

    options = ContainerOptions(
        mode=ContainerMode.MANAGED,
        image="artifactory/db/postgres-validation:latest",
        name="dblift-preflight-test",
        ports=["15432:5432"],
        env=["POSTGRES_PASSWORD=secret"],
    )

    container_id = DockerRunner(run=run).start(options)

    assert container_id == "container-123"
    assert calls[0][:4] == ["docker", "run", "-d", "--rm"]
    assert "--name" in calls[0]
    assert "dblift-preflight-test" in calls[0]
    assert "-p" in calls[0]
    assert "15432:5432" in calls[0]
    assert "-e" in calls[0]
    assert "POSTGRES_PASSWORD=secret" in calls[0]
    assert calls[0][-1] == "artifactory/db/postgres-validation:latest"


def test_start_managed_container_omits_rm_when_kept():
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        result = Mock()
        result.stdout = "container-123\n"
        result.returncode = 0
        return result

    options = ContainerOptions(
        mode=ContainerMode.MANAGED,
        image="artifactory/db/postgres-validation:latest",
        keep=True,
    )

    DockerRunner(run=run).start(options)

    assert "--rm" not in calls[0]
    assert calls[0][:3] == ["docker", "run", "-d"]


def test_existing_container_returns_name_without_docker_run():
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        raise AssertionError("docker run should not be called for existing container")

    options = ContainerOptions(mode=ContainerMode.EXISTING, existing_name="ci-db")

    container_id = DockerRunner(run=run).start(options)

    assert container_id == "ci-db"
    assert calls == []


def test_cleanup_removes_managed_container_when_not_kept():
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        result = Mock()
        result.stdout = ""
        result.returncode = 0
        return result

    runner = DockerRunner(run=run)
    options = ContainerOptions(mode=ContainerMode.MANAGED, keep=False)

    runner.cleanup("container-123", options)

    assert calls == [["docker", "rm", "-f", "container-123"]]


def test_cleanup_skips_existing_container():
    calls = []
    runner = DockerRunner(run=lambda cmd, **kwargs: calls.append(cmd))
    options = ContainerOptions(mode=ContainerMode.EXISTING, existing_name="ci-db")

    runner.cleanup("ci-db", options)

    assert calls == []


def test_check_docker_available_raises_when_docker_info_fails():
    def run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    runner = DockerRunner(run=run)

    with pytest.raises(RuntimeError, match="Docker daemon is not available"):
        runner.check_docker_available()


def test_check_container_running_raises_when_not_running():
    result = Mock()
    result.stdout = "false\n"

    runner = DockerRunner(run=lambda cmd, **kwargs: result)

    with pytest.raises(RuntimeError, match="my-container.*not running"):
        runner.check_container_running("my-container")


def test_check_container_running_raises_when_inspect_fails():
    def run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    runner = DockerRunner(run=run)

    with pytest.raises(RuntimeError, match="missing-container.*not running"):
        runner.check_container_running("missing-container")


def test_check_docker_available_raises_when_binary_missing():
    def run(cmd, **kwargs):
        raise FileNotFoundError("docker: command not found")

    runner = DockerRunner(run=run)

    with pytest.raises(RuntimeError, match="Docker daemon is not available"):
        runner.check_docker_available()


def test_check_container_running_passes_when_running():
    result = Mock()
    result.stdout = "true\n"

    runner = DockerRunner(run=lambda cmd, **kwargs: result)

    # Should not raise
    runner.check_container_running("my-container")


def test_start_passes_env_file_flag_when_set():
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        result = Mock()
        result.stdout = "container-abc\n"
        result.returncode = 0
        return result

    options = ContainerOptions(
        mode=ContainerMode.MANAGED,
        image="db:latest",
        env_file="/run/secrets/db.env",
    )

    DockerRunner(run=run).start(options)

    assert "--env-file" in calls[0]
    assert "/run/secrets/db.env" in calls[0]


def test_start_omits_env_file_flag_when_not_set():
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        result = Mock()
        result.stdout = "container-abc\n"
        result.returncode = 0
        return result

    options = ContainerOptions(
        mode=ContainerMode.MANAGED,
        image="db:latest",
    )

    DockerRunner(run=run).start(options)

    assert "--env-file" not in calls[0]
