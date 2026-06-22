"""
Concurrency testing helper for integration tests.

CRITICAL: These utilities test that DBLift's locking mechanism works correctly
to prevent concurrent migrations from corrupting the schema history.

This module provides utilities to simulate multiple DBLift sessions
running simultaneously.
"""

import multiprocessing
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List

from .cli_runner import DBLiftCLI as ThreadSafeDBLiftCLI
from .cli_runner_direct import CommandResult
from .cli_runner_direct import DBLiftCLIDirect as DBLiftCLI


@dataclass
class ConcurrentExecutionResult:
    """Result from a concurrent execution test."""

    process_id: int
    result: CommandResult
    start_time: float
    end_time: float
    duration: float
    acquired_lock: bool
    waited_for_lock: bool
    error_message: str = ""


class ConcurrentExecutor:
    """
    Execute multiple DBLift CLI instances concurrently.

    This simulates real-world scenarios where multiple developers
    or CI/CD pipelines might try to migrate the same database simultaneously.

    CRITICAL: Tests using this class verify that the locking mechanism
    prevents race conditions and schema history corruption.
    """

    def __init__(self, config_file: Path, migrations_dir: Path):
        """
        Initialize concurrent executor.

        Args:
            config_file: Path to dblift.yaml
            migrations_dir: Path to migrations directory
        """
        self.config_file = Path(config_file)
        self.migrations_dir = Path(migrations_dir)

    def run_concurrent_migrations(
        self, num_processes: int = 2, command: str = "migrate", **kwargs
    ) -> List[ConcurrentExecutionResult]:
        """
        Run multiple migration processes concurrently.

        This tests the locking mechanism by starting multiple processes
        simultaneously. Only one should succeed in acquiring the lock.

        Args:
            num_processes: Number of concurrent processes
            command: Command to run (migrate, info, etc.)
            **kwargs: Arguments to pass to the command

        Returns:
            List of results, one per process
        """
        results = []
        processes = []

        # Use multiprocessing to simulate truly concurrent sessions
        # (separate processes, separate database connections)
        with multiprocessing.Manager() as manager:
            result_queue = manager.Queue()

            # Start all processes simultaneously
            for i in range(num_processes):
                p = multiprocessing.Process(
                    target=self._run_process,
                    args=(i, command, result_queue, kwargs),
                )
                processes.append(p)
                p.start()

            # Wait for all to complete
            for p in processes:
                p.join(timeout=120)  # 2 minute timeout
                if p.is_alive():
                    p.terminate()
                    p.join()

            # Collect results
            while not result_queue.empty():
                results.append(result_queue.get())

        return sorted(results, key=lambda x: x.process_id)

    def run_sequential_with_delay(
        self,
        num_executions: int = 2,
        delay_seconds: float = 0.5,
        command: str = "migrate",
        **kwargs,
    ) -> List[ConcurrentExecutionResult]:
        """
        Run multiple executions with a small delay between them.

        This tests the scenario where processes start very close together
        but not exactly simultaneously (e.g., rapid CI/CD triggers).

        Args:
            num_executions: Number of executions
            delay_seconds: Delay between process starts
            command: Command to run
            **kwargs: Arguments to pass to the command

        Returns:
            List of results
        """
        results = []
        processes = []

        with multiprocessing.Manager() as manager:
            result_queue = manager.Queue()

            for i in range(num_executions):
                p = multiprocessing.Process(
                    target=self._run_process,
                    args=(i, command, result_queue, kwargs),
                )
                processes.append(p)
                p.start()
                time.sleep(delay_seconds)  # Small delay between starts

            # Wait for all to complete
            for p in processes:
                p.join(timeout=120)
                if p.is_alive():
                    p.terminate()
                    p.join()

            # Collect results
            while not result_queue.empty():
                results.append(result_queue.get())

        return sorted(results, key=lambda x: x.process_id)

    def _run_process(
        self,
        process_id: int,
        command: str,
        result_queue: multiprocessing.Queue,
        kwargs: Dict[str, Any],
    ):
        """
        Execute command in a separate process.

        This is the worker function run in each concurrent process.
        It creates its own CLI instance and database connection.
        """
        start_time = time.time()

        try:
            # Create CLI instance (each process gets its own)
            cli = DBLiftCLI(self.config_file, self.migrations_dir)

            # Run the command
            if command == "migrate":
                result = cli.migrate(**kwargs)
            elif command == "info":
                result = cli.info(**kwargs)
            elif command == "baseline":
                result = cli.baseline(**kwargs)
            elif command == "undo":
                result = cli.undo(**kwargs)
            elif command == "validate":
                result = cli.validate(**kwargs)
            elif command == "clean":
                result = cli.clean(**kwargs)
            else:
                raise ValueError(f"Unsupported command: {command}")

            end_time = time.time()

            # Analyze result to determine if lock was involved
            acquired_lock = result.success
            waited_for_lock = (
                "waiting for lock" in result.stderr.lower()
                or "waiting for lock" in result.stdout.lower()
                or "lock timeout" in result.stderr.lower()
                or "lock timeout" in result.stdout.lower()
            )

            error_message = result.stderr if result.failed else ""

            exec_result = ConcurrentExecutionResult(
                process_id=process_id,
                result=result,
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                acquired_lock=acquired_lock,
                waited_for_lock=waited_for_lock,
                error_message=error_message,
            )

            result_queue.put(exec_result)

        except Exception as e:
            # Handle exceptions in the worker process
            end_time = time.time()
            exec_result = ConcurrentExecutionResult(
                process_id=process_id,
                result=CommandResult(returncode=1, stdout="", stderr=str(e), command=[]),
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                acquired_lock=False,
                waited_for_lock=False,
                error_message=str(e),
            )
            result_queue.put(exec_result)


def simulate_user_sessions(
    config_file: Path,
    migrations_dir: Path,
    num_users: int = 3,
    actions: List[Callable] = None,
) -> List[Dict[str, Any]]:
    """
    Simulate multiple users performing different actions concurrently.

    This is useful for testing realistic scenarios where different users
    perform different operations (e.g., one migrates, one checks info,
    one validates) at the same time.

    Example:
        # User 1 migrates, User 2 checks info, User 3 validates
        results = simulate_user_sessions(
            config, migrations,
            num_users=3,
            actions=[
                lambda cli: cli.migrate(),
                lambda cli: cli.info(),
                lambda cli: cli.validate()
            ]
        )

    Args:
        config_file: Path to configuration file
        migrations_dir: Path to migrations directory
        num_users: Number of concurrent users
        actions: List of actions (functions taking CLI instance)

    Returns:
        List of result dictionaries with user_id, result, and duration
    """
    if not actions:
        actions = [lambda cli: cli.migrate()] * num_users

    results = []
    result_lock = threading.Lock()

    def user_action(user_id: int, action: Callable):
        """Execute user action in thread."""
        start = time.time()

        try:
            cli = ThreadSafeDBLiftCLI(config_file, migrations_dir)
            result = action(cli)
            end = time.time()

            with result_lock:
                results.append(
                    {
                        "user_id": user_id,
                        "result": result,
                        "duration": end - start,
                        "success": result.success,
                    }
                )
        except Exception as e:
            end = time.time()
            with result_lock:
                results.append(
                    {
                        "user_id": user_id,
                        "result": None,
                        "duration": end - start,
                        "success": False,
                        "error": str(e),
                    }
                )

    threads = []
    for i, action in enumerate(actions):
        t = threading.Thread(target=user_action, args=(i, action))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    return sorted(results, key=lambda x: x["user_id"])
