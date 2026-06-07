"""BUG-03 regression: ``DBLiftClient.export_schema(options=...)`` is honored.

Before this fix, ``options=`` landed in ``**kwargs`` and was silently
discarded. Callers who had a pre-built ``ExportSchemaOptions`` instance
(e.g. from a config layer) had to either copy every field into individual
kwargs or accept that their options object was ignored. The fix adds an
explicit ``options`` parameter that takes precedence over the individual
kwargs when provided.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestExportSchemaOptionsParameter:
    def _make_client(self):
        from api.client import DBLiftClient

        client = DBLiftClient.__new__(DBLiftClient)
        client.config = MagicMock()
        client.config.migrations.directories = []
        client.config.migrations.recursive = True
        client.executor = MagicMock()
        client.logger = MagicMock()
        client.events = MagicMock()
        client._get_scripts_dir = MagicMock(return_value=None)
        return client

    def test_options_parameter_is_forwarded_to_impl(self):
        """When ``options=`` is passed, that exact object is sent to the impl
        — no rebuilding from individual kwargs."""
        from core.migration.commands.export_schema_command import ExportSchemaOptions

        client = self._make_client()
        prebuilt = ExportSchemaOptions(output="/tmp/out.sql", schema="app")

        with patch("core.migration.commands.export_schema_command.export_schema") as mock_impl:
            mock_impl.return_value = True
            client.export_schema(options=prebuilt)

        assert mock_impl.called
        sent_opts = mock_impl.call_args.kwargs["options"]
        assert sent_opts is prebuilt  # same object, not a copy

    def test_options_takes_precedence_over_individual_kwargs(self):
        """If ``options`` is provided, individual kwargs are NOT merged into
        it — the user explicitly chose the options object, so honor it."""
        from core.migration.commands.export_schema_command import ExportSchemaOptions

        client = self._make_client()
        prebuilt = ExportSchemaOptions(output="/from/options.sql", schema="from_opts")

        with patch("core.migration.commands.export_schema_command.export_schema") as mock_impl:
            mock_impl.return_value = True
            client.export_schema(
                options=prebuilt,
                output="/from/kwarg.sql",  # ignored because options wins
                schema="from_kwarg",
            )

        sent_opts = mock_impl.call_args.kwargs["options"]
        assert sent_opts.output == "/from/options.sql"
        assert sent_opts.schema == "from_opts"

    def test_without_options_builds_from_kwargs_as_before(self):
        """Back-compat: the old per-kwarg path still works unchanged when
        ``options`` is omitted."""
        client = self._make_client()

        with patch("core.migration.commands.export_schema_command.export_schema") as mock_impl:
            mock_impl.return_value = True
            client.export_schema(output="/tmp/kwarg.sql", schema="app")

        sent_opts = mock_impl.call_args.kwargs["options"]
        assert sent_opts.output == "/tmp/kwarg.sql"
        assert sent_opts.schema == "app"

    def test_invalid_options_type_raises_typeerror(self):
        """A non-ExportSchemaOptions value under ``options=`` is a user error
        and must fail loudly instead of being silently ignored."""
        client = self._make_client()
        with pytest.raises(TypeError, match="ExportSchemaOptions"):
            client.export_schema(options={"output": "/tmp/dict.sql"})
