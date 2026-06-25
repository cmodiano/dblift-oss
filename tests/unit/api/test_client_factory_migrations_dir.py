"""BUG-07 regression: from_config() with migrations_dir kwarg raises TypeError.

Before this fix, client_from_config() passed migrations_dir as an explicit
named argument AND left it in **kwargs, so the DBLiftClient constructor
received the same keyword twice → TypeError.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_config(directory="migrations"):
    config = MagicMock()
    config.migrations.directory = directory
    config.migrations.directories = []
    config.log_format = None
    config.log_level = None
    config.log_file = None
    config.log_dir = None
    config.logging = MagicMock()
    config.logging.directory = None
    config.logging.file = None
    config.database.type = "postgresql"
    return config


@pytest.mark.unit
class TestClientFactoryMigrationsDir:
    def test_caller_migrations_dir_takes_priority(self):
        from api._client_factory import client_from_config

        config = _make_config(directory="from_config")

        captured = {}

        def fake_ctor(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        with (
            patch("api._client_factory.ProviderRegistry.create_provider", return_value=MagicMock()),
            patch("api._client_factory.DbliftLogger", return_value=MagicMock()),
        ):
            client_from_config(
                config,
                client_cls=fake_ctor,
                migrations_dir="/caller/path",
            )

        assert captured["migrations_dir"] == "/caller/path"

    def test_config_migrations_dir_used_when_no_kwarg(self):
        from api._client_factory import client_from_config

        config = _make_config(directory="from_config_dir")
        captured = {}

        def fake_ctor(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        with (
            patch("api._client_factory.ProviderRegistry.create_provider", return_value=MagicMock()),
            patch("api._client_factory.DbliftLogger", return_value=MagicMock()),
        ):
            client_from_config(config, client_cls=fake_ctor)

        assert captured["migrations_dir"] == "from_config_dir"

    def test_migrations_dir_kwarg_not_duplicated(self):
        """migrations_dir must appear exactly once in the constructor call."""
        from api._client_factory import client_from_config

        config = _make_config()
        call_count = {"n": 0}

        def fake_ctor(**kwargs):
            call_count["n"] += 1
            # If migrations_dir were duplicated Python would raise TypeError before here
            return MagicMock()

        with (
            patch("api._client_factory.ProviderRegistry.create_provider", return_value=MagicMock()),
            patch("api._client_factory.DbliftLogger", return_value=MagicMock()),
        ):
            # Should not raise TypeError
            client_from_config(config, client_cls=fake_ctor, migrations_dir="/some/path")

        assert call_count["n"] == 1
