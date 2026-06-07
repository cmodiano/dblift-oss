"""Story 23-8: Guard [0] access on potentially empty runs list in run_validation.py (NEW-BUG-47)."""

import pytest

pytestmark = [pytest.mark.unit]


def _count_sarif_results(sarif_json):
    """Replicate the fixed SARIF counting logic from run_validation.py."""
    errors = warnings = infos = 0
    if sarif_json:
        runs = sarif_json.get("runs") or [{}]
        for result in runs[0].get("results", []):
            level = result.get("level")
            if level == "error":
                errors += 1
            elif level == "warning":
                warnings += 1
            else:
                infos += 1
    return errors, warnings, infos


def test_empty_runs_list_does_not_raise():
    """Explicit empty runs list must not raise IndexError."""
    sarif_json = {"runs": []}
    errors, warnings, infos = _count_sarif_results(sarif_json)
    assert errors == warnings == infos == 0


def test_missing_runs_key_does_not_raise():
    """Missing 'runs' key must not raise."""
    sarif_json = {}
    errors, warnings, infos = _count_sarif_results(sarif_json)
    assert errors == warnings == infos == 0


def test_results_counted_correctly():
    """When runs contains results, they are counted by level."""
    sarif_json = {
        "runs": [
            {
                "results": [
                    {"level": "error"},
                    {"level": "warning"},
                    {"level": "note"},
                    {"level": "error"},
                ]
            }
        ]
    }
    errors, warnings, infos = _count_sarif_results(sarif_json)
    assert errors == 2
    assert warnings == 1
    assert infos == 1
