"""Baseline rows expose MigrationDisplayState-aligned status in collector output."""

import pytest

from core.logger import NullLog
from core.migration.migration import Migration
from core.migration.state.migration_state import MigrationState
from core.migration.ui.data_collector import MigrationDataCollector

pytestmark = pytest.mark.unit


def test_migration_data_from_state_successful_baseline_uses_baseline_state():
    collector = MigrationDataCollector(NullLog())
    baseline = Migration.create_baseline_migration(
        content="baseline",
        version="1.0.0",
        description="Production baseline",
    )
    baseline.success = True
    baseline.installed_rank = 1

    state = MigrationState(pending_objects=[])
    rows = collector._get_migration_data_from_state(
        migration_state=state,
        all_applied_migrations=[baseline],
        scripts_dir=None,
    )
    assert len(rows) == 1
    assert rows[0]["state"] == "Baseline"


def test_legacy_migration_data_successful_baseline_uses_baseline_state():
    collector = MigrationDataCollector(NullLog())
    baseline = Migration.create_baseline_migration(
        content="baseline",
        version="1.0.0",
        description="Production baseline",
    )
    baseline.success = True
    baseline.installed_rank = 1

    rows = collector.get_migration_data(
        applied_migrations=[baseline],
        pending_migrations=[],
        scripts_dir=None,
    )
    assert len(rows) == 1
    assert rows[0]["state"] == "Baseline"


def test_find_current_and_baseline_version_uses_is_migration_success():
    """String/integer success values must match status path."""
    collector = MigrationDataCollector(NullLog())
    baseline = Migration.create_baseline_migration(
        content="baseline",
        version="2.1.0",
        description="baseline",
    )
    baseline.success = "true"
    baseline.installed_rank = 3

    current, found_baseline = collector._find_current_and_baseline_version([baseline])
    assert found_baseline == "2.1.0"
    assert current is None


def test_status_to_display_state_baseline():
    assert MigrationDataCollector._status_to_display_state("BASELINE") == "Baseline"
