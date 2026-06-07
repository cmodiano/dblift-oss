"""Tests for MigrationDataService."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from core.migration.state.migration_data_service import MigrationDataService
from core.migration.state.migration_display_state import MigrationDisplayState


def make_migration(
    version="1",
    type="SQL",
    script_name="V1__test.sql",
    success=True,
    installed_rank=1,
    description="test",
    checksum="abc",
    installed_on=None,
    installed_by="user",
    execution_time=100,
    resolved=True,
):
    m = Mock()
    m.version = version
    m.type = type
    m.script_name = script_name
    m.success = success
    m.installed_rank = installed_rank
    m.description = description
    m.checksum = checksum
    m.installed_on = installed_on
    m.installed_by = installed_by
    m.execution_time = execution_time
    m.resolved = resolved
    return m


@pytest.fixture
def logger():
    return MagicMock()


@pytest.fixture
def service(logger):
    return MigrationDataService(logger, scripts_dir=Path("/tmp/scripts"), target_version="5")


# ---------- _format_version ----------


@pytest.mark.unit
class TestFormatVersion:
    def test_none_returns_empty(self, service):
        assert service._format_version(None) == ""

    def test_empty_string_returns_empty(self, service):
        assert service._format_version("") == ""

    def test_underscores_replaced_with_dots(self, service):
        assert service._format_version("1_2") == "1.2"

    def test_no_underscores_unchanged(self, service):
        assert service._format_version("1") == "1"

    def test_multiple_underscores(self, service):
        assert service._format_version("1_2_3") == "1.2.3"


# ---------- _get_migration_category ----------


@pytest.mark.unit
class TestGetMigrationCategory:
    def test_sql_returns_versioned(self, service):
        m = make_migration(type="SQL")
        assert service._get_migration_category(m) == "Versioned"

    def test_repeatable(self, service):
        m = make_migration(type="REPEATABLE")
        assert service._get_migration_category(m) == "Repeatable"

    def test_undo_sql(self, service):
        m = make_migration(type="UNDO_SQL")
        assert service._get_migration_category(m) == "Undo"

    def test_baseline(self, service):
        m = make_migration(type="BASELINE")
        assert service._get_migration_category(m) == "Baseline"

    def test_delete_with_description_tag_sql(self, service):
        m = make_migration(
            type="DELETE", description="[DELETE:SQL] removed", script_name="V1__x.sql"
        )
        assert service._get_migration_category(m) == "Versioned"

    def test_delete_with_description_tag_repeatable(self, service):
        m = make_migration(
            type="DELETE", description="[DELETE:REPEATABLE] removed", script_name="R__x.sql"
        )
        assert service._get_migration_category(m) == "Repeatable"

    def test_delete_with_description_tag_undo_sql(self, service):
        m = make_migration(
            type="DELETE", description="[DELETE:UNDO_SQL] removed", script_name="U1__x.sql"
        )
        assert service._get_migration_category(m) == "Undo"

    def test_delete_with_description_tag_other(self, service):
        m = make_migration(
            type="DELETE", description="[DELETE:CUSTOM] removed", script_name="X.sql"
        )
        assert service._get_migration_category(m) == "Custom"

    def test_delete_fallback_script_prefix_v(self, service):
        m = make_migration(type="DELETE", description="no tag", script_name="V1__init.sql")
        assert service._get_migration_category(m) == "Versioned"

    def test_delete_fallback_script_prefix_r(self, service):
        m = make_migration(type="DELETE", description="no tag", script_name="R__seed.sql")
        assert service._get_migration_category(m) == "Repeatable"

    def test_delete_fallback_script_prefix_u(self, service):
        m = make_migration(type="DELETE", description="no tag", script_name="U1__undo.sql")
        assert service._get_migration_category(m) == "Undo"

    def test_delete_no_tag_no_prefix_returns_deleted(self, service):
        m = make_migration(type="DELETE", description="no tag", script_name="x.sql")
        assert service._get_migration_category(m) == "Deleted"

    def test_unknown_type_capitalized(self, service):
        m = make_migration(type="SPECIAL")
        assert service._get_migration_category(m) == "Special"

    def test_empty_type_returns_unknown(self, service):
        m = make_migration(type="")
        assert service._get_migration_category(m) == "Unknown"


# ---------- _get_migration_type ----------


@pytest.mark.unit
class TestGetMigrationType:
    def test_string_type(self, service):
        m = make_migration(type="SQL")
        assert service._get_migration_type(m) == "SQL"

    def test_string_lowercase_uppercased(self, service):
        m = make_migration(type="sql")
        assert service._get_migration_type(m) == "SQL"

    def test_enum_type_with_name(self, service):
        enum_type = Mock()
        enum_type.name = "REPEATABLE"
        m = make_migration()
        m.type = enum_type
        assert service._get_migration_type(m) == "REPEATABLE"

    def test_empty_type(self, service):
        m = make_migration(type="")
        assert service._get_migration_type(m) == ""


# ---------- _is_migration_successful ----------


@pytest.mark.unit
class TestIsMigrationSuccessful:
    def test_true_success(self, service):
        m = make_migration(success=True)
        assert service._is_migration_successful(m) is True

    def test_false_success(self, service):
        m = make_migration(success=False)
        assert service._is_migration_successful(m) is False


# ---------- _get_undone_versions ----------


@pytest.mark.unit
class TestGetUndoneVersions:
    def test_finds_successful_undo_sql(self, service):
        migrations = [
            make_migration(version="1", type="SQL", installed_rank=1),
            make_migration(version="1", type="UNDO_SQL", success=True, installed_rank=2),
        ]
        result = service._get_undone_versions(migrations)
        assert result == {"1"}

    def test_ignores_failed_undo(self, service):
        migrations = [
            make_migration(version="1", type="UNDO_SQL", success=False, installed_rank=2),
        ]
        result = service._get_undone_versions(migrations)
        assert result == set()

    def test_ignores_non_undo(self, service):
        migrations = [
            make_migration(version="1", type="SQL", success=True, installed_rank=1),
        ]
        result = service._get_undone_versions(migrations)
        assert result == set()

    def test_empty_list(self, service):
        assert service._get_undone_versions([]) == set()


# ---------- _get_reapplied_versions ----------


@pytest.mark.unit
class TestGetReappliedVersions:
    def test_reapplied_after_undo(self, service):
        migrations = [
            make_migration(version="1", type="SQL", success=True, installed_rank=1),
            make_migration(version="1", type="UNDO_SQL", success=True, installed_rank=2),
            make_migration(version="1", type="SQL", success=True, installed_rank=3),
        ]
        result = service._get_reapplied_versions(migrations)
        assert result == {"1"}

    def test_not_reapplied_if_no_sql_after_undo(self, service):
        migrations = [
            make_migration(version="1", type="SQL", success=True, installed_rank=1),
            make_migration(version="1", type="UNDO_SQL", success=True, installed_rank=2),
        ]
        result = service._get_reapplied_versions(migrations)
        assert result == set()


# ---------- _is_version_reapplied / _get_undo_rank ----------


@pytest.mark.unit
class TestIsVersionReapplied:
    def test_reapplied_when_sql_rank_higher_than_undo(self, service):
        migrations = [
            make_migration(version="1", type="UNDO_SQL", success=True, installed_rank=2),
            make_migration(version="1", type="SQL", success=True, installed_rank=3),
        ]
        assert service._is_version_reapplied(migrations, "1") is True

    def test_not_reapplied_when_no_undo(self, service):
        migrations = [
            make_migration(version="1", type="SQL", success=True, installed_rank=1),
        ]
        assert service._is_version_reapplied(migrations, "1") is False

    def test_not_reapplied_when_sql_rank_lower(self, service):
        migrations = [
            make_migration(version="1", type="SQL", success=True, installed_rank=1),
            make_migration(version="1", type="UNDO_SQL", success=True, installed_rank=5),
        ]
        assert service._is_version_reapplied(migrations, "1") is False


@pytest.mark.unit
class TestGetUndoRank:
    def test_returns_rank_of_successful_undo(self, service):
        migrations = [
            make_migration(version="1", type="UNDO_SQL", success=True, installed_rank=7),
        ]
        assert service._get_undo_rank(migrations, "1") == 7

    def test_returns_minus_one_when_no_undo(self, service):
        migrations = [
            make_migration(version="1", type="SQL", success=True, installed_rank=1),
        ]
        assert service._get_undo_rank(migrations, "1") == -1

    def test_ignores_failed_undo(self, service):
        migrations = [
            make_migration(version="1", type="UNDO_SQL", success=False, installed_rank=3),
        ]
        assert service._get_undo_rank(migrations, "1") == -1


# ---------- _get_baseline_version ----------


@pytest.mark.unit
class TestGetBaselineVersion:
    def test_returns_first_baseline(self, service):
        migrations = [
            make_migration(version="1", type="BASELINE", installed_rank=1),
            make_migration(version="2", type="SQL", installed_rank=2),
        ]
        assert service._get_baseline_version(migrations) == "1"

    def test_no_baseline_returns_none(self, service):
        migrations = [
            make_migration(version="1", type="SQL", installed_rank=1),
        ]
        assert service._get_baseline_version(migrations) is None

    def test_empty_list(self, service):
        assert service._get_baseline_version([]) is None


# ---------- _detect_out_of_order_migrations ----------


@pytest.mark.unit
class TestDetectOutOfOrderMigrations:
    def test_in_order_returns_empty(self, service):
        migrations = [
            make_migration(version="1", type="SQL", installed_rank=1),
            make_migration(version="2", type="SQL", installed_rank=2),
            make_migration(version="3", type="SQL", installed_rank=3),
        ]
        assert service._detect_out_of_order_migrations(migrations) == set()

    def test_out_of_order_detected(self, service):
        migrations = [
            make_migration(version="1", type="SQL", installed_rank=1),
            make_migration(version="3", type="SQL", installed_rank=2),
            make_migration(version="2", type="SQL", installed_rank=3),
        ]
        result = service._detect_out_of_order_migrations(migrations)
        assert "2" in result

    def test_skips_non_sql(self, service):
        migrations = [
            make_migration(version="1", type="SQL", installed_rank=1),
            make_migration(version=None, type="REPEATABLE", installed_rank=2),
            make_migration(version="2", type="SQL", installed_rank=3),
        ]
        assert service._detect_out_of_order_migrations(migrations) == set()

    def test_multipart_versions(self, service):
        migrations = [
            make_migration(version="1_1", type="SQL", installed_rank=1),
            make_migration(version="2_0", type="SQL", installed_rank=2),
            make_migration(version="1_2", type="SQL", installed_rank=3),
        ]
        result = service._detect_out_of_order_migrations(migrations)
        assert "1_2" in result


# ---------- _compare_version_parts ----------


@pytest.mark.unit
class TestCompareVersionParts:
    def test_equal(self, service):
        assert service._compare_version_parts([1, 2], [1, 2]) == 0

    def test_less_than(self, service):
        assert service._compare_version_parts([1, 0], [1, 2]) == -1

    def test_greater_than(self, service):
        assert service._compare_version_parts([2, 0], [1, 9]) == 1

    def test_different_lengths_padded(self, service):
        assert service._compare_version_parts([1], [1, 0]) == 0

    def test_shorter_less_than_longer(self, service):
        assert service._compare_version_parts([1], [1, 1]) == -1


# ---------- _build_repeatable_checksums ----------


@pytest.mark.unit
class TestBuildRepeatableChecksums:
    def test_maps_script_to_checksum(self, service):
        migrations = [
            make_migration(type="REPEATABLE", script_name="R__seed.sql", checksum="abc123"),
            make_migration(type="REPEATABLE", script_name="R__ref.sql", checksum="def456"),
        ]
        result = service._build_repeatable_checksums(migrations)
        assert result == {"R__seed.sql": "abc123", "R__ref.sql": "def456"}

    def test_ignores_non_repeatable(self, service):
        migrations = [
            make_migration(type="SQL", script_name="V1__init.sql", checksum="aaa"),
        ]
        assert service._build_repeatable_checksums(migrations) == {}

    def test_latest_checksum_wins(self, service):
        migrations = [
            make_migration(type="REPEATABLE", script_name="R__seed.sql", checksum="old"),
            make_migration(type="REPEATABLE", script_name="R__seed.sql", checksum="new"),
        ]
        result = service._build_repeatable_checksums(migrations)
        assert result == {"R__seed.sql": "new"}

    def test_empty_list(self, service):
        assert service._build_repeatable_checksums([]) == {}


# ---------- _sort_applied_migrations ----------


@pytest.mark.unit
class TestSortAppliedMigrations:
    def test_sorted_by_installed_rank(self, service):
        m1 = make_migration(version="1", installed_rank=3)
        m2 = make_migration(version="2", installed_rank=1)
        m3 = make_migration(version="3", installed_rank=2)
        result = service._sort_applied_migrations([m1, m2, m3])
        assert [m.installed_rank for m in result] == [1, 2, 3]


# ---------- _get_current_version ----------


@pytest.mark.unit
class TestGetCurrentVersion:
    def test_returns_highest_successful_sql(self, service):
        migrations = [
            make_migration(version="1", type="SQL", success=True, installed_rank=1),
            make_migration(version="3", type="SQL", success=True, installed_rank=2),
            make_migration(version="2", type="SQL", success=True, installed_rank=3),
        ]
        assert service._get_current_version(migrations) == "3"

    def test_ignores_failed(self, service):
        migrations = [
            make_migration(version="1", type="SQL", success=True, installed_rank=1),
            make_migration(version="2", type="SQL", success=False, installed_rank=2),
        ]
        assert service._get_current_version(migrations) == "1"

    def test_ignores_non_sql(self, service):
        migrations = [
            make_migration(version="1", type="SQL", success=True, installed_rank=1),
            make_migration(version=None, type="REPEATABLE", success=True, installed_rank=2),
        ]
        assert service._get_current_version(migrations) == "1"

    def test_empty_returns_none(self, service):
        assert service._get_current_version([]) is None


# ---------- _version_has_undo_script ----------


@pytest.mark.unit
class TestVersionHasUndoScript:
    def test_returns_true_when_file_exists(self, service):
        mock_dir = MagicMock(spec=Path)
        mock_dir.glob.return_value = [Path("/tmp/scripts/U1__undo.sql")]
        assert service._version_has_undo_script("1", mock_dir) is True
        mock_dir.glob.assert_called_once_with("U1*.sql")

    def test_returns_false_when_no_file(self, service):
        mock_dir = MagicMock(spec=Path)
        mock_dir.glob.return_value = []
        assert service._version_has_undo_script("1", mock_dir) is False

    def test_returns_false_when_no_scripts_dir(self, service):
        assert service._version_has_undo_script("1", None) is False

    def test_returns_false_when_no_version(self, service):
        mock_dir = MagicMock(spec=Path)
        assert service._version_has_undo_script("", mock_dir) is False

    def test_glob_exception_returns_false(self, service):
        mock_dir = MagicMock(spec=Path)
        mock_dir.glob.side_effect = OSError("permission denied")
        assert service._version_has_undo_script("1", mock_dir) is False


# ---------- _build_analysis_context ----------


@pytest.mark.unit
class TestBuildAnalysisContext:
    def test_returns_all_context_keys(self, service):
        migrations = [
            make_migration(version="1", type="SQL", success=True, installed_rank=1),
        ]
        ctx = service._build_analysis_context(migrations)
        expected_keys = {
            "undone_versions",
            "reapplied_versions",
            "baseline_version",
            "out_of_order_migrations",
            "repeatable_checksums",
            "current_version",
            "target_version",
            "scripts_dir",
        }
        assert set(ctx.keys()) == expected_keys

    def test_includes_target_version_and_scripts_dir(self, service):
        ctx = service._build_analysis_context([])
        assert ctx["target_version"] == "5"
        assert ctx["scripts_dir"] == Path("/tmp/scripts")


# ---------- prepare_migration_data ----------


@pytest.mark.unit
class TestPrepareMigrationData:
    def test_applied_migration_processed(self, service):
        m = make_migration(version="1", type="SQL", description="init", installed_rank=1)
        with patch.object(
            service.state_service, "determine_state", return_value=MigrationDisplayState.SUCCESS
        ):
            result = service.prepare_migration_data([m])
        assert len(result) == 1
        assert result[0]["source"] == "applied"
        assert result[0]["version"] == "1"
        assert result[0]["state"] == "Success"
        assert result[0]["category"] == "Versioned"

    def test_pending_migration_processed(self, service):
        applied = make_migration(version="1", type="SQL", installed_rank=1)
        pending = make_migration(
            version="2", type="SQL", script_name="V2__add.sql", description="add table"
        )
        with (
            patch.object(
                service.state_service, "determine_state", return_value=MigrationDisplayState.SUCCESS
            ),
            patch.object(
                service.state_service,
                "determine_pending_state",
                return_value=MigrationDisplayState.PENDING,
            ),
        ):
            result = service.prepare_migration_data([applied], pending_migrations=[pending])
        pending_items = [r for r in result if r["source"] == "pending"]
        assert len(pending_items) == 1
        assert pending_items[0]["state"] == "Pending"
        assert pending_items[0]["installed_on"] is None

    def test_error_in_applied_logs_warning_and_continues(self, service):
        good = make_migration(version="1", type="SQL", installed_rank=1)
        bad = make_migration(version="2", type="SQL", installed_rank=2)
        with patch.object(service.state_service, "determine_state") as mock_state:
            mock_state.side_effect = [RuntimeError("boom"), MigrationDisplayState.SUCCESS]
            # bad is first in list but has lower rank — doesn't matter, iteration order is list order
            result = service.prepare_migration_data([bad, good])
        assert len(result) == 1
        service.logger.warning.assert_called_once()

    def test_delete_description_cleaned(self, service):
        m = make_migration(
            version="1",
            type="DELETE",
            description="[DELETE:SQL] original desc",
            script_name="V1__init.sql",
            installed_rank=1,
        )
        with patch.object(
            service.state_service, "determine_state", return_value=MigrationDisplayState.DELETED
        ):
            result = service.prepare_migration_data([m])
        assert result[0]["description"] == "original desc"

    def test_empty_applied_and_pending(self, service):
        result = service.prepare_migration_data([])
        assert result == []


# ---------- _ensure_undone_migrations_in_pending ----------


@pytest.mark.unit
class TestEnsureUndoneMigrationsInPending:
    def test_adds_undo_when_script_exists(self, service):
        context = {
            "undone_versions": {"1"},
            "scripts_dir": MagicMock(spec=Path),
        }
        context["scripts_dir"].glob.return_value = [Path("/tmp/U1__undo.sql")]
        migration_data = [
            {"version": "1", "type": "SQL", "source": "applied", "description": "init"},
        ]
        result = service._ensure_undone_migrations_in_pending(migration_data, context)
        undo_items = [r for r in result if r.get("category") == "Undo" and r["source"] == "pending"]
        assert len(undo_items) == 1
        assert undo_items[0]["state"] == MigrationDisplayState.AVAILABLE.value
        assert undo_items[0]["description"] == "init"

    def test_skips_when_already_pending(self, service):
        context = {
            "undone_versions": {"1"},
            "scripts_dir": MagicMock(spec=Path),
        }
        context["scripts_dir"].glob.return_value = [Path("/tmp/U1__undo.sql")]
        migration_data = [
            {"version": "1", "type": "SQL", "source": "applied", "description": "init"},
            {"version": "1", "source": "pending", "category": "Undo"},
        ]
        result = service._ensure_undone_migrations_in_pending(migration_data, context)
        undo_pending = [r for r in result if r.get("source") == "pending"]
        assert len(undo_pending) == 1  # no duplicate added

    def test_no_undone_versions_returns_unchanged(self, service):
        context = {"undone_versions": set(), "scripts_dir": Path("/tmp")}
        data = [{"version": "1", "source": "applied"}]
        result = service._ensure_undone_migrations_in_pending(data, context)
        assert result == data

    def test_no_scripts_dir_returns_unchanged(self, service):
        context = {"undone_versions": {"1"}, "scripts_dir": None}
        data = [{"version": "1", "source": "applied"}]
        result = service._ensure_undone_migrations_in_pending(data, context)
        assert result == data

    def test_no_undo_script_file_skips(self, service):
        context = {
            "undone_versions": {"1"},
            "scripts_dir": MagicMock(spec=Path),
        }
        context["scripts_dir"].glob.return_value = []
        data = [{"version": "1", "type": "SQL", "source": "applied"}]
        result = service._ensure_undone_migrations_in_pending(data, context)
        assert len(result) == 1  # nothing added

    def test_fallback_description_when_no_original(self, service):
        context = {
            "undone_versions": {"1"},
            "scripts_dir": MagicMock(spec=Path),
        }
        context["scripts_dir"].glob.return_value = [Path("/tmp/U1__undo.sql")]
        migration_data = []  # no original migration to reference
        result = service._ensure_undone_migrations_in_pending(migration_data, context)
        assert len(result) == 1
        assert result[0]["description"] == "Undo migration 1"


# ---------- Constructor ----------


@pytest.mark.unit
class TestConstructor:
    def test_stores_attributes(self, logger):
        svc = MigrationDataService(logger, scripts_dir=Path("/scripts"), target_version="3")
        assert svc.logger is logger
        assert svc.scripts_dir == Path("/scripts")
        assert svc.target_version == "3"

    def test_defaults(self, logger):
        svc = MigrationDataService(logger)
        assert svc.scripts_dir is None
        assert svc.target_version is None

    def test_state_service_created(self, logger):
        svc = MigrationDataService(logger)
        assert isinstance(svc.state_service, MigrationStateService)


# Need import for isinstance check
from core.migration.state.migration_state_service import MigrationStateService
