"""OSS standalone smoke probes for module discoverability and CLI tier leaks."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OSS_ROOTS = ("api", "cli", "config", "core", "db", "integrations")


def test_oss_roots_discoverable_without_higher_tier_packages(tmp_path):
    oss_source = tmp_path / "oss_source"
    oss_source.mkdir()
    for root in OSS_ROOTS:
        source_root = ROOT / root
        assert source_root.exists(), f"Missing OSS source root: {source_root}"
        (oss_source / root).symlink_to(source_root, target_is_directory=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(oss_source)
    roots = repr(OSS_ROOTS)

    probe = f"""
import importlib.util

missing = []
# find_spec checks OSS-only import-path discoverability without executing package code.
for mod in {roots}:
    if importlib.util.find_spec(mod) is None:
        missing.append(mod)

leaks = []
for mod in ("dblift_pro", "dblift_enterprise"):
    spec = importlib.util.find_spec(mod)
    if spec is not None:
        leaks.append(f"{{mod}}: {{spec.origin}}")

if missing:
    raise SystemExit("OSS modules not importable: " + ", ".join(missing))
if leaks:
    raise SystemExit("higher-tier modules importable: " + ", ".join(leaks))
"""
    out = subprocess.run(
        [sys.executable, "-S", "-c", probe],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr or out.stdout


def _oss_builtin_command_choices(monkeypatch):
    from cli import extensions
    from cli._parser_setup import create_parser

    monkeypatch.setattr(extensions.metadata, "entry_points", lambda group: [])
    parser = create_parser()
    subparser = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    return set(subparser.choices)


def test_oss_builtin_cli_excludes_relocated_paid_commands(monkeypatch):
    choices = _oss_builtin_command_choices(monkeypatch)

    for word in ("diff", "export-schema", "snapshot"):
        assert word not in choices, f"PRO/Enterprise command '{word}' present in OSS CLI"


def test_oss_builtin_cli_excludes_remaining_paid_commands(monkeypatch):
    choices = _oss_builtin_command_choices(monkeypatch)

    for word in ("validate-sql", "plan", "preflight"):
        assert word not in choices, f"PRO/Enterprise command '{word}' present in OSS CLI"
