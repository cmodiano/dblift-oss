"""Benchmark suite conftest.

Skips automatically when `pytest-benchmark` is not installed, so a plain
``pytest tests/`` run in a minimal env does not fail. The suite is
intended to run via ``pytest tests/benchmarks/ --benchmark-only`` on
manual dispatch; see ``tests/benchmarks/README.md``.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip benchmark tests unless pytest-benchmark is active.

    Avoids a noisy failure when someone runs ``pytest tests/`` without
    the benchmark plugin (which is bundled with dev deps, but not with
    the runtime install).
    """
    if not config.getoption("--benchmark-only", default=False):
        skip_marker = pytest.mark.skip(
            reason="Benchmark suite runs only with --benchmark-only. "
            "See tests/benchmarks/README.md."
        )
        for item in items:
            if "tests/benchmarks" in str(item.fspath):
                item.add_marker(skip_marker)
