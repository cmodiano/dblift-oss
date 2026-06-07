"""Small Docker CLI wrapper used by preflight."""

from __future__ import annotations

import subprocess
from typing import Any, Callable, List, Optional

from core.preflight.models import ContainerMode, ContainerOptions


class DockerRunner:
    """Run the Docker commands needed by preflight."""

    def __init__(self, run: Optional[Callable[..., Any]] = None) -> None:
        """Inject subprocess runner for unit tests."""
        self._run = run or subprocess.run

    def start(self, options: ContainerOptions) -> Optional[str]:
        """Start or resolve the validation container."""
        if options.mode == ContainerMode.NONE:
            return None
        if options.mode == ContainerMode.EXISTING:
            return options.existing_name

        if not options.image:
            raise ValueError("--container-image is required for managed container mode")

        cmd: List[str] = ["docker", "run", "-d"]
        if not options.keep:
            cmd.append("--rm")
        if options.name:
            cmd.extend(["--name", options.name])
        for port in options.ports:
            cmd.extend(["-p", port])
        for env in options.env:
            cmd.extend(["-e", env])
        if options.env_file:
            cmd.extend(["--env-file", options.env_file])
        cmd.append(options.image)

        result = self._run(cmd, check=True, capture_output=True, text=True)
        return str(result.stdout).strip()

    def check_docker_available(self) -> None:
        """Raise RuntimeError if the Docker daemon cannot be reached."""
        try:
            self._run(["docker", "info"], check=True, capture_output=True, text=True)
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            raise RuntimeError(f"Docker daemon is not available: {exc}") from exc

    def check_container_running(self, name: str) -> None:
        """Raise RuntimeError if the named container is not running."""
        try:
            result = self._run(
                ["docker", "inspect", "--format={{.State.Running}}", name],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            raise RuntimeError(f"Container '{name}' is not running: {exc}") from exc
        if str(result.stdout).strip() != "true":
            raise RuntimeError(f"Container '{name}' is not running")

    def cleanup(self, container_id: Optional[str], options: ContainerOptions) -> None:
        """Remove a managed container unless the user asked to keep it."""
        if not container_id or not options.managed or options.keep:
            return
        self._run(["docker", "rm", "-f", container_id], check=False, capture_output=True, text=True)
