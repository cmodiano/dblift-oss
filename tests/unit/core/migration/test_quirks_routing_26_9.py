"""Story 26-9: Verify dialect branches in engine + undo generators route through quirks."""

import pytest

from db.provider_registry import ProviderRegistry

pytestmark = [pytest.mark.unit]


class TestSelectSupportsLimit:
    """AC#1: select_supports_limit quirks property drives post-commit verification."""

    @pytest.mark.parametrize(
        "dialect, expected",
        [
            ("postgresql", True),
            ("mysql", True),
            ("sqlite", True),
            ("oracle", False),
            ("db2", False),
            ("sqlserver", False),
        ],
    )
    def test_select_supports_limit_per_dialect(self, dialect, expected):
        quirks = ProviderRegistry.get_quirks(dialect)
        assert quirks.select_supports_limit is expected


class TestUndoDropIfExistsRoutedThroughQuirks:
    """AC#2: Undo _generate_drop_statement IF EXISTS routes through quirks."""

    @pytest.mark.parametrize(
        "dialect, expect_if_exists",
        [
            ("postgresql", True),
            ("mysql", True),
            ("sqlite", True),
            ("sqlserver", True),
            ("oracle", False),
            ("db2", False),
        ],
    )
    def test_extractors_mixin_if_exists(self, dialect, expect_if_exists):
        from core.migration.scripting.undo_script_generator._extractors import (
            UndoStatementEmitter,
        )

        emitter = UndoStatementEmitter(dialect=dialect)
        sql = emitter._generate_drop_statement("TABLE", "users", None)
        if expect_if_exists:
            assert "IF EXISTS" in sql
        else:
            assert "IF EXISTS" not in sql

    @pytest.mark.parametrize(
        "dialect, expect_if_exists",
        [
            ("postgresql", True),
            ("mysql", True),
            ("oracle", False),
            ("db2", False),
        ],
    )
    def test_helpers_mixin_if_exists(self, dialect, expect_if_exists):
        from core.migration.scripting.undo_script_generator._helpers import (
            _UndoHelpersMixin,
        )

        class _Stub(_UndoHelpersMixin):
            def __init__(self, d):
                self.dialect = d
                self.logger = None

        stub = _Stub(dialect)
        sql = stub._generate_drop_statement("TABLE", "users", None)
        if expect_if_exists:
            assert "IF EXISTS" in sql
        else:
            assert "IF EXISTS" not in sql


class TestNoHardcodedDialectStringsInDropGeneration:
    """AC#3: No hardcoded dialect string checks remain in undo drop generation."""

    def test_extractors_no_hardcoded_dialect_check(self):
        import inspect

        from core.migration.scripting.undo_script_generator._extractors import (
            _UndoExtractorsMixin,
        )

        src = inspect.getsource(_UndoExtractorsMixin._generate_drop_statement)
        assert '"postgresql"' not in src
        assert '"mysql"' not in src

    def test_helpers_no_hardcoded_dialect_check(self):
        import inspect

        from core.migration.scripting.undo_script_generator._helpers import (
            _UndoHelpersMixin,
        )

        src = inspect.getsource(_UndoHelpersMixin._generate_drop_statement)
        assert '"postgresql"' not in src
        assert '"mysql"' not in src
