"""Unit tests for ``scripts/check_api_docstrings`` (PR-E1, action #4).

The linter gates the ``api/`` + ``cli/`` + ``core/`` public surface in
CI; these tests pin the detection rules, exemption mechanisms, and
ratchet semantics so future changes can't silently weaken the contract.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from scripts.check_api_docstrings import main, scan_file

pytestmark = [pytest.mark.unit]


def _write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "mod.py"
    path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
    return path


def test_clean_file_has_zero_violations(tmp_path: Path) -> None:
    """Module + class + function + method all documented → no violations."""
    path = _write(
        tmp_path,
        '''
        """Module doc."""

        class Foo:
            """Class doc."""

            def __init__(self) -> None:
                """Init doc."""
                self.x = 1

            def method(self) -> int:
                """Method doc."""
                return self.x


        def helper() -> int:
            """Helper doc."""
            return 1
        ''',
    )
    assert scan_file(str(path)) == []


def test_missing_module_docstring_flagged(tmp_path: Path) -> None:
    path = _write(tmp_path, 'def f():\n    """doc."""\n    pass\n')
    violations = scan_file(str(path))
    assert ("module", "<module>") in [(v[2], v[3]) for v in violations]


def test_missing_function_docstring_flagged(tmp_path: Path) -> None:
    path = _write(tmp_path, '"""mod."""\n\ndef public_no_doc():\n    return 1\n')
    violations = scan_file(str(path))
    assert ("function", "public_no_doc") in [(v[2], v[3]) for v in violations]


def test_missing_class_docstring_flagged(tmp_path: Path) -> None:
    path = _write(tmp_path, '"""mod."""\n\nclass PublicNoDoc:\n    pass\n')
    violations = scan_file(str(path))
    kinds_names = [(v[2], v[3]) for v in violations]
    assert ("class", "PublicNoDoc") in kinds_names


def test_private_names_ignored(tmp_path: Path) -> None:
    """Names starting with ``_`` are exempt (except ``__init__``)."""
    path = _write(
        tmp_path,
        '''
        """mod."""

        def _private_helper():
            return 1


        class _PrivateClass:
            pass
        ''',
    )
    assert scan_file(str(path)) == []


def test_dunder_init_is_public(tmp_path: Path) -> None:
    """``__init__`` is treated as public because constructor docs matter."""
    path = _write(
        tmp_path,
        '''
        """mod."""

        class Foo:
            """Class doc."""

            def __init__(self) -> None:
                # No docstring — should still be flagged because the body
                # does work (assignment), so the stub-body exemption does
                # not apply.
                self.x = 1
        ''',
    )
    violations = scan_file(str(path))
    assert any(v[3] == "__init__" for v in violations)


def test_stub_body_ellipsis_exempt(tmp_path: Path) -> None:
    """Single-statement ``...`` body is treated as a protocol stub."""
    path = _write(
        tmp_path,
        '''
        """mod."""

        from typing import Protocol


        class P(Protocol):
            """Protocol doc."""

            def method(self) -> int: ...
        ''',
    )
    assert scan_file(str(path)) == []


def test_stub_body_pass_exempt(tmp_path: Path) -> None:
    """Single-statement ``pass`` body is treated as a stub."""
    path = _write(
        tmp_path,
        '''
        """mod."""


        def stub():
            pass
        ''',
    )
    assert scan_file(str(path)) == []


def test_inner_functions_exempt(tmp_path: Path) -> None:
    """Closures defined inside another function inherit the outer docstring."""
    path = _write(
        tmp_path,
        '''
        """mod."""

        from functools import wraps


        def decorator(fn):
            """Outer doc."""

            @wraps(fn)
            def wrapper(*args, **kwargs):
                return fn(*args, **kwargs)

            return wrapper
        ''',
    )
    assert scan_file(str(path)) == []


def test_inline_annotation_exempts_function(tmp_path: Path) -> None:
    """``# lint: allow-missing-docstring: <reason>`` is honored on def lines."""
    path = _write(
        tmp_path,
        '''
        """mod."""


        def public_no_doc():  # lint: allow-missing-docstring: legacy entrypoint
            return 1
        ''',
    )
    assert scan_file(str(path)) == []


def test_bare_none_body_is_not_a_stub(tmp_path: Path) -> None:
    """A body of literal ``None`` is not a stub — it must still be flagged.

    Regression for cursor[bot] review on PR #279: an earlier version of
    ``_is_stub_body`` accepted ``def foo(): None`` as a stub alongside
    ``...`` / ``pass``. Only ``...`` and ``pass`` are documented stub
    forms; ``None`` returned implicitly from an expression statement is
    not a Protocol/ABC idiom and must not bypass the docstring rule.
    """
    path = _write(
        tmp_path,
        '''
        """mod."""


        def public_returns_none():
            None
        ''',
    )
    violations = scan_file(str(path))
    assert any(v[3] == "public_returns_none" for v in violations)


def test_inline_annotation_exempts_class(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '''
        """mod."""


        class Legacy:  # lint: allow-missing-docstring: pre-2026 holdover
            x = 1
        ''',
    )
    assert scan_file(str(path)) == []


# ---------------------------------------------------------------------------
# Private-class heuristic (action #4)
# ---------------------------------------------------------------------------


def test_private_class_method_exempt(tmp_path: Path) -> None:
    """Public-named methods on private classes inherit the class's privacy."""
    path = _write(
        tmp_path,
        '''
        """mod."""


        def _make_result():
            """Factory doc."""

            class _Result:
                def __init__(self) -> None:
                    self.x = 1

                def execution_time(self) -> int:
                    return 0

            return _Result()
        ''',
    )
    # ``_make_result`` is private; ``_Result`` is private; methods of
    # ``_Result`` must NOT be flagged. The decorator/closure pattern is
    # widespread (factories, context managers, internal builders).
    assert scan_file(str(path)) == []


def test_private_class_init_exempt(tmp_path: Path) -> None:
    """``__init__`` on a private class does not need a docstring."""
    path = _write(
        tmp_path,
        '''
        """mod."""


        class _Internal:
            def __init__(self, x: int) -> None:
                self.x = x
        ''',
    )
    assert scan_file(str(path)) == []


def test_public_class_init_still_flagged(tmp_path: Path) -> None:
    """The heuristic must not regress: ``__init__`` on a public class is still flagged."""
    path = _write(
        tmp_path,
        '''
        """mod."""


        class Public:
            """Class doc."""

            def __init__(self, x: int) -> None:
                self.x = x
        ''',
    )
    violations = scan_file(str(path))
    assert any(v[3] == "__init__" for v in violations)


def test_public_method_on_public_class_still_flagged(tmp_path: Path) -> None:
    """Counter-test: public method on a public class is NOT exempted."""
    path = _write(
        tmp_path,
        '''
        """mod."""


        class Public:
            """Class doc."""

            def method(self) -> int:
                return 0
        ''',
    )
    violations = scan_file(str(path))
    assert any(v[3] == "method" for v in violations)


def test_public_class_nested_under_private_class_inherits_privacy(tmp_path: Path) -> None:
    """``class _P: class Q: def m(): ...`` — ``m`` is private, not flagged.

    Regression for Bugbot #340: an earlier version of ``_enclosing_classes``
    walked up only to the nearest ``ClassDef``, missing the outer ``_P``.
    ``Q`` is public-named but lives entirely inside the private surface of
    ``_P``; its methods should inherit that privacy.
    """
    path = _write(
        tmp_path,
        '''
        """mod."""


        class _Private:
            class Inner:
                def method(self) -> int:
                    return 0

                def __init__(self) -> None:
                    self.x = 1
        ''',
    )
    assert scan_file(str(path)) == []


def test_deeply_nested_private_chain(tmp_path: Path) -> None:
    """``_A.B.C.method`` is private when *any* ancestor class is private."""
    path = _write(
        tmp_path,
        '''
        """mod."""


        class _A:
            class B:
                class C:
                    def method(self) -> int:
                        return 0
        ''',
    )
    assert scan_file(str(path)) == []


# ---------------------------------------------------------------------------
# Ratchet mode (action #4)
# ---------------------------------------------------------------------------


def _make_violator_tree(tmp_path: Path, root: str, count: int) -> Path:
    """Create *count* files under *tmp_path*/*root*/ each missing a module docstring."""
    root_dir = tmp_path / root
    root_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (root_dir / f"mod_{i}.py").write_text("def f():\n    pass\n", encoding="utf-8")
    return root_dir


def test_ratchet_pass_at_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """count == cap exits 0."""
    monkeypatch.chdir(tmp_path)
    _make_violator_tree(tmp_path, "fake", 5)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps({"fake": 5}), encoding="utf-8")
    rc = main(["--paths", "fake", "--ratchet", str(ratchet)])
    assert rc == 0


def test_ratchet_fail_when_over_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """count > cap exits 1 and lists the delta."""
    monkeypatch.chdir(tmp_path)
    _make_violator_tree(tmp_path, "fake", 6)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps({"fake": 5}), encoding="utf-8")
    rc = main(["--paths", "fake", "--ratchet", str(ratchet)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "fake: 6 violation(s), cap is 5" in out
    assert "Net +1" in out


def test_ratchet_pass_under_cap_with_nudge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """count < cap exits 0 with a tightening suggestion."""
    monkeypatch.chdir(tmp_path)
    _make_violator_tree(tmp_path, "fake", 3)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps({"fake": 10}), encoding="utf-8")
    rc = main(["--paths", "fake", "--ratchet", str(ratchet)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "consider committing tighter caps" in out
    assert "you can lower the cap by 7" in out


def test_ratchet_missing_root_with_violations_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A root listed in --paths but absent from the ratchet must be declared."""
    monkeypatch.chdir(tmp_path)
    _make_violator_tree(tmp_path, "fake", 2)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps({"other": 0}), encoding="utf-8")
    rc = main(["--paths", "fake", "--ratchet", str(ratchet)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "root not declared in ratchet" in out


def test_ratchet_comment_keys_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Underscore-prefixed top-level keys are comments — never treated as roots."""
    monkeypatch.chdir(tmp_path)
    _make_violator_tree(tmp_path, "fake", 1)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(
        json.dumps({"_comment": "anything", "_policy": "stuff", "fake": 1}),
        encoding="utf-8",
    )
    rc = main(["--paths", "fake", "--ratchet", str(ratchet)])
    assert rc == 0


def test_ratchet_rejects_negative_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A negative cap is a config error — propagate as a hard failure."""
    monkeypatch.chdir(tmp_path)
    _make_violator_tree(tmp_path, "fake", 0)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps({"fake": -1}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-negative integer"):
        main(["--paths", "fake", "--ratchet", str(ratchet)])


def test_ratchet_rejects_boolean_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``true`` / ``false`` are JSON booleans, not integer caps — reject explicitly.

    Regression for Bugbot review on PR #340: Python's ``bool`` is a subclass
    of ``int``, so ``isinstance(True, int)`` is True. A naive int-only check
    silently accepts ``"api": true`` as cap=1, which almost certainly means
    the ratchet maintainer typed a bare ``true`` instead of ``1``.
    """
    monkeypatch.chdir(tmp_path)
    _make_violator_tree(tmp_path, "fake", 0)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps({"fake": True}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-negative integer"):
        main(["--paths", "fake", "--ratchet", str(ratchet)])
    ratchet.write_text(json.dumps({"fake": False}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-negative integer"):
        main(["--paths", "fake", "--ratchet", str(ratchet)])


def test_no_ratchet_keeps_strict_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Default (no --ratchet) is unchanged: any violation fails."""
    monkeypatch.chdir(tmp_path)
    _make_violator_tree(tmp_path, "fake", 1)
    rc = main(["--paths", "fake"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "missing docstring" in out
