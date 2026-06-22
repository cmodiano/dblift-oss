from unittest.mock import MagicMock

import core.seams.event_listeners as event_listeners
from api.events import EventEmitter
from core.seams.event_listeners import attach_registered_listeners


def test_attach_no_entrypoints_is_noop():
    emitter = EventEmitter()
    # No dblift.event_listeners entry points installed in the OSS-only test env.
    attach_registered_listeners(emitter)  # must not raise


def test_attach_registered_listeners_loads_entrypoints(monkeypatch):
    emitter = EventEmitter()
    calls = []

    def _register(target):
        calls.append(target)
        target.on("test", lambda payload: None)

    entry_point = MagicMock()
    entry_point.name = "sample_listener"
    entry_point.load.return_value = _register

    monkeypatch.setattr(
        event_listeners,
        "entry_points",
        lambda group: [entry_point] if group == "dblift.event_listeners" else [],
    )

    attach_registered_listeners(emitter)

    assert calls == [emitter]
