import sys
from types import ModuleType

from core.seams.introspection import attach_registered_introspection


class _EntryPoint:
    name = "pro"

    def __init__(self, registrar):
        self._registrar = registrar

    def load(self):
        return self._registrar


def test_attach_registered_introspection_loads_entrypoints(monkeypatch):
    calls = []

    def registrar():
        calls.append("registered")

    monkeypatch.setattr(
        "core.seams.introspection.entry_points",
        lambda group: [_EntryPoint(registrar)] if group == "dblift.introspection" else [],
    )
    attach_registered_introspection()

    assert calls == ["registered"]
