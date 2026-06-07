"""Unit tests for ``scripts/check_line_length`` (action #5).

The script gates ``flake8 E501`` counts via a per-root ratchet. These
tests pin the ratchet semantics — pass-at-cap, fail-when-over, nudge-when-under
— and the JSON validation, so future changes can't silently weaken the
ratchet contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_line_length import _load_ratchet, _normalize, main

pytestmark = [pytest.mark.unit]


def _make_long_lines(tmp_path: Path, root: str, count: int) -> Path:
    """Create *root* under *tmp_path* with *count* files each having one >100-char line."""
    root_dir = tmp_path / root
    root_dir.mkdir(parents=True, exist_ok=True)
    long_line = "x = " + ("'a' " * 30) + "  # " + ("z" * 20) + "\n"
    assert len(long_line) > 100
    for i in range(count):
        (root_dir / f"mod_{i}.py").write_text(long_line, encoding="utf-8")
    return root_dir


def test_ratchet_pass_at_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _make_long_lines(tmp_path, "fake", 3)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps({"fake": 3}), encoding="utf-8")
    rc = main(["--paths", "fake", "--ratchet", str(ratchet)])
    assert rc == 0


def test_ratchet_fail_when_over_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _make_long_lines(tmp_path, "fake", 5)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps({"fake": 3}), encoding="utf-8")
    rc = main(["--paths", "fake", "--ratchet", str(ratchet)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "fake: 5 violation(s), cap is 3" in out
    assert "Net +2" in out


def test_ratchet_pass_under_cap_with_nudge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _make_long_lines(tmp_path, "fake", 2)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps({"fake": 10}), encoding="utf-8")
    rc = main(["--paths", "fake", "--ratchet", str(ratchet)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "consider committing tighter caps" in out
    assert "you can lower the cap by 8" in out


def test_ratchet_missing_root_with_violations_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _make_long_lines(tmp_path, "fake", 1)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps({"other": 0}), encoding="utf-8")
    rc = main(["--paths", "fake", "--ratchet", str(ratchet)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "root not declared in ratchet" in out


def test_ratchet_comment_keys_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _make_long_lines(tmp_path, "fake", 1)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(
        json.dumps({"_comment": "anything", "_policy": "stuff", "fake": 1}),
        encoding="utf-8",
    )
    rc = main(["--paths", "fake", "--ratchet", str(ratchet)])
    assert rc == 0


def test_ratchet_rejects_negative_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _make_long_lines(tmp_path, "fake", 0)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps({"fake": -1}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-negative integer"):
        main(["--paths", "fake", "--ratchet", str(ratchet)])


def test_ratchet_rejects_boolean_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """JSON ``true`` / ``false`` must be rejected — Python's bool subclasses int."""
    monkeypatch.chdir(tmp_path)
    _make_long_lines(tmp_path, "fake", 0)
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps({"fake": True}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-negative integer"):
        main(["--paths", "fake", "--ratchet", str(ratchet)])
    ratchet.write_text(json.dumps({"fake": False}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-negative integer"):
        main(["--paths", "fake", "--ratchet", str(ratchet)])


def test_load_ratchet_rejects_non_object(tmp_path: Path) -> None:
    """Top-level value must be an object — a bare list or scalar is a config error."""
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ValueError, match="expected a top-level JSON object"):
        _load_ratchet(str(ratchet))


def test_normalize_strips_trailing_slashes_and_normalizes_seps() -> None:
    """Path normalization is idempotent across OS separators and trailing slashes."""
    assert _normalize("api") == "api"
    assert _normalize("api/") == "api"
    assert _normalize("api\\") == "api" or _normalize("api\\") == "api\\"  # POSIX vs win


def test_clean_root_with_zero_cap_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A clean root (no E501 violations) at cap=0 passes."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "fake").mkdir()
    (tmp_path / "fake" / "ok.py").write_text("x = 1\n", encoding="utf-8")
    ratchet = tmp_path / "ratchet.json"
    ratchet.write_text(json.dumps({"fake": 0}), encoding="utf-8")
    rc = main(["--paths", "fake", "--ratchet", str(ratchet)])
    assert rc == 0
