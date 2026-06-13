"""Story 23-1: DEAD-NEW-01 — structural guards for dead import removal."""

import pytest

pytestmark = [pytest.mark.unit]


def test_diff_result_still_accessible_from_core_logger():
    """DiffResult must remain re-exported from core.logger (tests depend on this path)."""
    from core.logger import DiffResult

    assert DiffResult is not None
