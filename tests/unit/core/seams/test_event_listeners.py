import importlib
from unittest.mock import MagicMock

import core.seams.event_listeners as event_listeners
from api.events import EventEmitter
from core.seams.event_listeners import attach_registered_listeners


def test_attach_no_entrypoints_is_noop():
    emitter = EventEmitter()
    # No dblift.event_listeners entry points installed in the OSS-only test env.
    attach_registered_listeners(emitter)  # must not raise
