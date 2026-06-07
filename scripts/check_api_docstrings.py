"""Public-API docstring linter.

Enforces that every module, class, function and method exposed under
``api/`` carries a docstring. ``api/`` is the documented public surface
consumed by IDE integrations, CI/CD pipelines and the rest of the
``DBLift`` test suite — a missing docstring there has the same cost as
a missing type signature.

Scope
=====

Default behaviour scans ``api/``: zero-tolerance, every violation fails
CI. Extended behaviour scans additional roots (``cli/``, ``core/``,
``config/``, ``db/``) under a **count-based ratchet** loaded from
``--ratchet PATH``. The ratchet records a per-root cap on missing
docstrings; new violations push the count above the cap and fail CI,
while removed violations are rewarded with an informational nudge to
commit a tighter cap. The mechanism mirrors the
deferral-with-ratchet style used by ``scripts/lint_patterns.py`` for
``.lint-patterns-baseline.txt``, except the unit of accounting is a
count, not a fingerprinted entry — appropriate when the deferred
violations number in the hundreds and per-line annotations would
flood the source files.

What counts as "public"
=======================

A name is public when it does **not** start with an underscore. Private
names (``_helper``, etc.) are skipped, **with two refinements**:

* ``__init__`` is treated as public on a public class (constructor
  documentation matters). When its enclosing class is private, the
  constructor inherits the class's privacy — a stub on a private
  class doesn't add user-facing value.
* A public-named method on a private class also inherits the class's
  privacy. ``class _Result: def execution_time(self): ...`` is part of
  the private surface; documenting it is busywork.

Exemptions
==========

Four categories of public names are exempt because requiring a
docstring on them is either redundant or actively misleading:

1. **Inner functions / closures.** Decorators using ``functools.wraps``
   inherit the wrapped function's docstring; insisting on a docstring on
   the inner closure produces duplicated, drifting prose. Detection:
   any ``FunctionDef`` whose immediate parent is another ``FunctionDef``
   or ``AsyncFunctionDef``.

2. **Methods on private classes** (see "public" rules above).

3. **Protocol / ABC stubs.** Methods whose body is exactly ``...``
   (``Ellipsis``) or ``pass`` are signature stubs (typing.Protocol,
   abc.abstractmethod, etc.). The class-level docstring documents the
   contract; the stub bodies don't need their own.

4. **Inline-annotated overrides.** A line ending with
   ``# lint: allow-missing-docstring: <reason>`` is treated as an
   intentional deferral, matching the convention from
   ``scripts/lint_patterns.py`` (e.g. ``# lint: allow-print``,
   ``# lint: allow-enum-str``).

Running
=======

::

    python scripts/check_api_docstrings.py                                    # api/ strict
    python scripts/check_api_docstrings.py --paths api cli core               # multi-root strict
    python scripts/check_api_docstrings.py --paths cli core --ratchet F       # ratcheted
    python scripts/check_api_docstrings.py --help

Exit code is ``0`` when no violations remain (or every root is at-or-below
its ratchet cap) and ``1`` otherwise. CI gates the lint job on the
zero-exit (see ``.github/workflows/code-quality.yml``).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple

DEFAULT_ROOTS = ("api",)
ALLOW_ANNOTATION = "# lint: allow-missing-docstring"

Violation = Tuple[str, int, str, str]  # (path, lineno, kind, name)


def _iter_python_files(roots: Iterable[str]) -> Iterable[str]:
    for root in roots:
        if os.path.isfile(root) and root.endswith(".py"):
            yield root
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                if filename.endswith(".py"):
                    yield os.path.join(dirpath, filename)


def _is_public_name(name: str) -> bool:
    """A bare name is public iff it does not start with an underscore."""
    if name == "__init__":
        return True
    return not name.startswith("_")


def _enclosing_classes(node: ast.AST) -> List[ast.ClassDef]:
    """Walk up the AST parent chain and return EVERY enclosing ``ClassDef``.

    Returned innermost-first. For ``class _P: class Q: def m(): ...``, the
    list for ``m`` is ``[Q, _P]``. Returning all ancestors (rather than only
    the nearest) is what lets ``_is_public`` notice that ``m`` lives under
    a private class even though the immediate enclosing class ``Q`` is
    public.
    """
    classes: List[ast.ClassDef] = []
    cur = getattr(node, "_parent", None)
    while cur is not None:
        if isinstance(cur, ast.ClassDef):
            classes.append(cur)
        cur = getattr(cur, "_parent", None)
    return classes


def _is_public(node: ast.AST, name: str) -> bool:
    """Public iff the name AND every enclosing class name are public.

    A public-named method on a private class (``class _R: def m(self): ...``)
    inherits the class's privacy — it is not part of the user-facing API
    surface, so a docstring on it is busywork. Same logic for ``__init__``:
    only flagged when every enclosing class is itself public. The full
    chain is checked, not just the nearest ancestor — otherwise a public
    class nested under a private one (``class _P: class Q: ...``) would
    leak its methods back into the strict gate.
    """
    if not _is_public_name(name):
        return False
    for enclosing in _enclosing_classes(node):
        if not _is_public_name(enclosing.name):
            return False
    return True


def _is_stub_body(node: ast.AST) -> bool:
    """Return True when *node*'s body is a single Ellipsis or ``pass`` statement."""
    body = getattr(node, "body", None)
    if not body or len(body) != 1:
        return False
    only = body[0]
    if isinstance(only, ast.Pass):
        return True
    if isinstance(only, ast.Expr) and isinstance(only.value, ast.Constant):
        return only.value.value is ...
    return False


def _annotated_lines(source: str) -> set[int]:
    """Set of 1-based line numbers carrying the ``allow-missing-docstring`` opt-out."""
    out: set[int] = set()
    for lineno, line in enumerate(source.splitlines(), start=1):
        if ALLOW_ANNOTATION in line:
            out.add(lineno)
    return out


def _attach_parents(tree: ast.AST) -> None:
    """Annotate each node with a ``_parent`` attribute (used to detect inner funcs)."""
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child._parent = parent  # type: ignore[attr-defined]


def _is_inner_function(node: ast.AST) -> bool:
    parent = getattr(node, "_parent", None)
    return isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef))


def scan_file(path: str) -> List[Violation]:
    """Return the list of public-name docstring violations in *path*."""
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    _attach_parents(tree)
    skip_lines = _annotated_lines(source)
    violations: List[Violation] = []

    has_module_doc = bool(
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    )
    if not has_module_doc and 1 not in skip_lines:
        violations.append((path, 1, "module", "<module>"))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not _is_public(node, node.name):
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _is_inner_function(node):
                    continue
                if _is_stub_body(node):
                    continue
            if ast.get_docstring(node):
                continue
            if node.lineno in skip_lines:
                continue
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            violations.append((path, node.lineno, kind, node.name))

    return violations


def _root_of(path: str, roots: Iterable[str]) -> Optional[str]:
    """Match *path* to the most specific configured root prefix."""
    norm = path.replace(os.sep, "/")
    best: Optional[str] = None
    for root in roots:
        rnorm = root.replace(os.sep, "/").rstrip("/")
        if norm == rnorm or norm.startswith(rnorm + "/"):
            if best is None or len(rnorm) > len(best):
                best = rnorm
    return best


def _load_ratchet(path: str) -> Dict[str, int]:
    """Read the per-root caps from *path*. Comment keys (starting with ``_``) are ignored.

    Keep in sync with ``scripts/check_line_length.py::_load_ratchet`` —
    these two are duplicated on purpose (project convention is one
    standalone script per lint rule, with no shared scripts/ package).
    A third ratchet would justify extracting into ``scripts/_ratchet_utils.py``.
    """
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a top-level JSON object, got {type(data).__name__}")
    out: Dict[str, int] = {}
    for key, value in data.items():
        if key.startswith("_"):
            continue
        # ``bool`` is a subclass of ``int`` in Python, so a naive ``isinstance(value, int)``
        # check silently accepts ``true`` / ``false`` from JSON as caps 1 / 0. A literal
        # boolean almost certainly means a typo by the ratchet maintainer — reject it
        # explicitly so the misconfiguration surfaces.
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{path}: ratchet key '{key}' must map to a non-negative integer")
        out[key] = value
    return out


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=list(DEFAULT_ROOTS),
        help=f"Directories or files to scan (default: {' '.join(DEFAULT_ROOTS)})",
    )
    parser.add_argument(
        "--ratchet",
        metavar="PATH",
        default=None,
        help=(
            "Load a per-root cap from a JSON file. With --ratchet, the script "
            "fails only when a root exceeds its recorded cap; counts at or below "
            "the cap pass. Without --ratchet, every violation fails."
        ),
    )
    args = parser.parse_args(argv)

    all_violations: List[Violation] = []
    for path in _iter_python_files(args.paths):
        all_violations.extend(scan_file(path))

    if args.ratchet is None:
        if not all_violations:
            print(f"OK: no missing docstrings in {' '.join(args.paths)}")
            return 0
        print(f"FAIL: {len(all_violations)} missing docstring(s) in public API surface:")
        for path, lineno, kind, name in all_violations:
            print(f"  {path}:{lineno}  {kind}  {name}")
        print(
            "\nFix by adding a docstring, or — if the case is genuinely exempt — "
            f"annotate the def/class line with `{ALLOW_ANNOTATION}: <reason>`."
        )
        return 1

    caps = _load_ratchet(args.ratchet)
    counts: Counter[str] = Counter()
    unmapped: List[Violation] = []
    for v in all_violations:
        root = _root_of(v[0], args.paths)
        if root is None:
            unmapped.append(v)
        else:
            counts[root] += 1

    if unmapped:
        print(
            f"FAIL: {len(unmapped)} violation(s) outside any configured root — "
            "this should not happen, please report:"
        )
        for path, lineno, kind, name in unmapped:
            print(f"  {path}:{lineno}  {kind}  {name}")
        return 1

    failing: List[str] = []
    failing_roots: List[str] = []
    suggest_tighten: List[str] = []
    for root in args.paths:
        rnorm = root.replace(os.sep, "/").rstrip("/")
        current = counts.get(rnorm, 0)
        cap = caps.get(rnorm)
        if cap is None:
            if current > 0:
                failing.append(
                    f"  {rnorm}: {current} violation(s) — root not declared in ratchet "
                    f"{args.ratchet}. Add a cap for it or drop it from --paths."
                )
                failing_roots.append(rnorm)
            continue
        if current > cap:
            failing.append(
                f"  {rnorm}: {current} violation(s), cap is {cap}. Net +{current - cap} "
                "since the last ratchet update — add docstrings or annotate."
            )
            failing_roots.append(rnorm)
        elif current < cap:
            suggest_tighten.append(
                f"  {rnorm}: {current} violation(s), cap is {cap} — you can lower "
                f"the cap by {cap - current} in {args.ratchet}."
            )

    if failing:
        print("FAIL: docstring ratchet exceeded:")
        for line in failing:
            print(line)
        # Help signal: print the actual violations in the first failing root.
        # Use the structured root name captured during the loop above, not a
        # re-parse of the formatted message — the message format and the
        # filter logic should never share a string contract.
        first_root_norm = failing_roots[0]
        print(f"\nViolations in '{first_root_norm}':")
        for path, lineno, kind, name in all_violations:
            if _root_of(path, args.paths) == first_root_norm:
                print(f"  {path}:{lineno}  {kind}  {name}")
        print(
            f"\nFix by adding a docstring, or annotate with "
            f"`{ALLOW_ANNOTATION}: <reason>` on the def/class line."
        )
        return 1

    summary = ", ".join(
        f"{r.replace(os.sep, '/').rstrip('/')}={counts.get(r.replace(os.sep, '/').rstrip('/'), 0)}/{caps.get(r.replace(os.sep, '/').rstrip('/'), 'n/a')}"
        for r in args.paths
    )
    print(f"OK: docstring ratchet respected ({summary})")
    if suggest_tighten:
        print("\nThe ratchet is loose on these roots — consider committing tighter caps:")
        for line in suggest_tighten:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
