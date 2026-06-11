"""Contract test for the public API surface (PR-F5).

The public surface — everything reachable from ``api/__init__.py`` —
must not change silently. Renaming a kwarg on ``DBLiftClient.migrate``
or removing an entry from ``EventType`` is a breaking change that
deserves an explicit reviewer decision, not a quiet diff hidden inside
a refactor PR.

How it works
============

At test time the suite reflects on:

- ``api.__all__`` (the documented re-export list).
- Each class in ``__all__``: the ``__init__`` signature plus every
  public method's ``inspect.signature`` (including the return
  annotation when present).
- ``EventType`` enum: every member's name and string value.

The rendered surface is compared byte-for-byte against
``tests/unit/api/api_public_surface.txt`` (the golden snapshot,
version-controlled). Any drift fails the test with a readable unified
diff. The failure message includes the command that regenerates the
snapshot — intended drift is then a one-keystroke acknowledgement.

Regenerating the snapshot
=========================

::

    UPDATE_API_SURFACE=1 pytest tests/unit/api/test_public_surface_contract.py

This is a deliberate action: the snapshot lives in version control so
the diff is the reviewer's evidence that the breakage is intentional.
"""

from __future__ import annotations

import difflib
import inspect
import os
from enum import Enum
from pathlib import Path
from typing import Any, List

import pytest

pytestmark = [pytest.mark.unit]


SURFACE_PATH = Path(__file__).parent / "api_public_surface.txt"
UPDATE_ENV_VAR = "UPDATE_API_SURFACE"


def _render_callable(qualname: str, fn: Any) -> str:
    """Render a callable as ``qualname(signature) -> return_annotation`` (single line)."""
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        return f"{qualname}(<unintrospectable>)"
    return f"{qualname}{sig}"


def _public_methods(cls: type) -> List[str]:
    """Return public (non-``_``) method names declared on *cls*, sorted.

    ``__init__`` is included because constructor signatures are part of
    the contract; other dunders are excluded because they are framework
    plumbing (``__enter__``, ``__exit__``, ``__repr__``) whose churn is
    not user-visible.
    """
    names: List[str] = []
    for name, member in inspect.getmembers(cls):
        if not callable(member):
            continue
        if name == "__init__":
            names.append(name)
            continue
        if name.startswith("_"):
            continue
        # Only methods defined on the class itself (not inherited from object).
        if name not in cls.__dict__ and not any(
            name in base.__dict__ for base in cls.__mro__ if base is not object
        ):
            continue
        names.append(name)
    return sorted(names)


def _render_class(cls: type) -> List[str]:
    """Render a class's public surface as a list of lines."""
    out = [f"class {cls.__module__}.{cls.__name__}:"]
    for name in _public_methods(cls):
        try:
            member = inspect.getattr_static(cls, name)
        except AttributeError:
            member = getattr(cls, name)
        # Unwrap classmethod / staticmethod for signature inspection.
        if isinstance(member, (classmethod, staticmethod)):
            fn = member.__func__
        else:
            fn = member
        out.append("  " + _render_callable(name, fn))
    return out


def _render_enum(cls: type) -> List[str]:
    """Render an ``Enum`` as ``name = value`` lines, sorted by name."""
    out = [f"enum {cls.__module__}.{cls.__name__}:"]
    members = sorted((m.name, m.value) for m in cls)  # type: ignore[attr-defined]
    for name, value in members:
        out.append(f"  {name} = {value!r}")
    return out


def _render_api_surface() -> str:
    """Build the full public-surface fingerprint as a sorted, deterministic string."""
    import api

    sections: List[str] = []

    # __all__ — the documented entry-point set.
    all_names = sorted(getattr(api, "__all__", []))
    sections.append("api.__all__ = " + repr(all_names))
    sections.append("")

    # Each re-exported name: render based on kind.
    for name in all_names:
        obj = getattr(api, name)
        if isinstance(obj, type) and issubclass(obj, Enum):
            sections.extend(_render_enum(obj))
        elif isinstance(obj, type):
            sections.extend(_render_class(obj))
        else:
            sections.append(f"{name}: {obj!r}")
        sections.append("")

    return "\n".join(sections).rstrip() + "\n"


def test_public_api_surface_matches_snapshot() -> None:
    """The public surface must match ``api_public_surface.txt`` byte-for-byte."""
    current = _render_api_surface()

    if os.environ.get(UPDATE_ENV_VAR):
        SURFACE_PATH.write_text(current, encoding="utf-8")
        pytest.skip(
            f"Surface fixture regenerated at {SURFACE_PATH}. "
            "Review the diff in git, commit it, then rerun without "
            f"{UPDATE_ENV_VAR}=1."
        )

    if not SURFACE_PATH.exists():
        pytest.fail(
            f"Surface fixture missing: {SURFACE_PATH}\n"
            f"Run `{UPDATE_ENV_VAR}=1 pytest "
            "tests/unit/api/test_public_surface_contract.py` to create it."
        )

    expected = SURFACE_PATH.read_text(encoding="utf-8")
    if current == expected:
        return

    diff = "\n".join(
        difflib.unified_diff(
            expected.splitlines(),
            current.splitlines(),
            fromfile="api_public_surface.txt (committed)",
            tofile="<live api surface>",
            lineterm="",
        )
    )
    pytest.fail(
        "Public API surface drifted from the committed snapshot.\n\n"
        + diff
        + "\n\n"
        + "If the change is intentional, regenerate the snapshot:\n"
        + f"    {UPDATE_ENV_VAR}=1 pytest tests/unit/api/test_public_surface_contract.py\n"
        + "and commit the updated `tests/unit/api/api_public_surface.txt`."
    )
