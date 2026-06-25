"""Regression test: provider transport metadata stays native-only.

DBLift v2 removed the JDBC transport family. Unknown providers also report
``native`` so framework code never falls back to a deleted transport path.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from db.provider_registry import ProviderRegistry


def _with_plugins(plugins):
    """Install a canned plugin map so the test doesn't depend on real discovery."""

    def _decorator(fn):
        def _wrapped():
            with (
                patch.object(ProviderRegistry, "_plugins", plugins),
                patch.object(ProviderRegistry, "_discovered", True),
            ):
                fn()

        return _wrapped

    return _decorator


@pytest.mark.unit
class TestProviderTransport:
    def test_known_plugin_returns_registered_transport(self):
        plugins = {"sqlite": SimpleNamespace(transport="native")}
        with (
            patch.object(ProviderRegistry, "_plugins", plugins),
            patch.object(ProviderRegistry, "_discovered", True),
        ):
            assert ProviderRegistry.get_provider_transport("SQLite") == "native"

    def test_unknown_plugin_defaults_to_native_transport(self):
        with (
            patch.object(ProviderRegistry, "_plugins", {}),
            patch.object(ProviderRegistry, "_discovered", True),
        ):
            assert ProviderRegistry.get_provider_transport("not-registered") == "native"
