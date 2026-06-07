# Testing Guide

How to run, write, and reason about the DBLift test suite.

The intended audience is a contributor who has never opened the test
tree. Reads top-to-bottom; each section is a runbook, not a tutorial.

## Layout

```
tests/
├── unit/                    # Fast, no network/filesystem outside tmp_path
│   ├── conftest.py          # Auto-bypass license guard for every unit test
│   ├── api/, cli/, config/, core/, db/, scripts/, sqlite/
│   └── (mirrors the source tree under each top-level package)
├── integration/             # Real databases via Docker (or external hosts)
│   ├── conftest.py          # Container readiness, dialect fixtures, env vars
│   ├── db/conftest.py       # Introspection-test fixtures
│   ├── matrix/              # Cross-cutting regression invariants (DB-free)
│   ├── commands/, features/, parsers/, concurrency/
│   └── docker-compose.yml + setup_test_env.sh
├── benchmarks/
└── utils/
```

The unit tree mirrors the source tree path-for-path: a test for
``api/_client_factory.py`` lives at ``tests/unit/api/test_client_factory*.py``.
This convention is enforced by code review — it makes "where is the
test for X?" a one-step grep instead of a fishing expedition.

### Layered conftests

There is no top-level ``tests/conftest.py``; fixtures are scoped to
the layer that needs them so ``unit/`` cannot accidentally inherit
Docker/networking dependencies from ``integration/``.

| Conftest | Provides |
|---|---|
| ``tests/unit/conftest.py`` | Auto-bypass of the runtime license guard (see *Gotchas*). |
| ``tests/unit/cli/conftest.py`` | CLI runner + stdout/stderr capture helpers. |
| ``tests/integration/conftest.py`` | Docker container spin-up, ``DBLIFT_*`` env-var resolution, dialect fixtures, ``require_license_key``. |
| ``tests/integration/db/conftest.py`` | Introspection schema generators per dialect. |
| ``tests/benchmarks/conftest.py`` | ``pytest-benchmark`` configuration. |

## Markers

All markers are declared in ``pytest.ini``. Use them — CI selects on them.

| Marker | When to apply |
|---|---|
| ``unit`` | Default for ``tests/unit/``. Used by some workflows for selection. |
| ``integration`` | Default for ``tests/integration/``. Skips on PR unit-test job. |
| ``slow`` | > 5 s. Excluded from default local runs (``-m "not slow"``). |
| ``postgresql``, ``mysql``, ``oracle``, ``sqlserver``, ``db2``, ``sqlite``, ``cosmosdb`` | Test requires that dialect. Integration runner sets ``DBLIFT_CORE_TEST_DB`` per matrix entry; unselected dialects are skipped. |
| ``no_db`` | Test must not touch any database — used for pure-logic integration helpers. |
| ``no_auto_setup``, ``no_cleanup`` | Opt out of the integration fixture's automatic create/drop cycle. |
| ``cli`` | Exercises a CLI entry point (Click ``CliRunner``). |
| ``migration`` | Touches the migration applier (state-machine tests). |
| ``asyncio`` | Required for ``pytest-asyncio`` discovery. |

Apply a marker via the module-level idiom:

```python
import pytest
pytestmark = [pytest.mark.unit]
```

or per-function ``@pytest.mark.<name>`` for single-test selection.

## Running tests

DBLift uses pytest directly — there is no project-specific runner module.

### Common invocations

```bash
# Whole unit tree (matches CI)
python -m pytest tests/unit/ -n auto --dist=loadscope -p no:benchmark --timeout=120

# A single file
python -m pytest tests/unit/api/test_client_extended.py -v

# A single test
python -m pytest tests/unit/api/test_client_extended.py::TestX::test_y -v

# Only fast tests (excludes slow)
python -m pytest tests/unit/ -m "not slow"

# Only one dialect's integration tests
DBLIFT_CORE_TEST_DB=postgresql python -m pytest tests/integration/commands/

# Cross-cutting matrix regression (DB-free, < 1 min — same as PR matrix-tests job)
python -m pytest tests/integration/matrix/

# Coverage locally (matches CI flags)
python -m pytest tests/unit/ --cov --cov-report=term-missing --cov-report=html
```

### Database integration setup

```bash
# 1. Bring up the dialect containers (PostgreSQL, MySQL, etc.)
cd tests/integration && ./setup_test_env.sh

# 2. Run the suite against a single dialect
DBLIFT_CORE_TEST_DB=postgresql python -m pytest tests/integration/commands/

# 3. Tear down
docker compose -f tests/integration/docker-compose.yml down
```

**External hosts.** When Docker is unavailable, the integration conftest
resolves connection details from ``DBLIFT_<DIALECT>_HOST`` /
``DBLIFT_<DIALECT>_PORT`` / ``DBLIFT_<DIALECT>_USERNAME`` /
``DBLIFT_<DIALECT>_PASSWORD`` / ``DBLIFT_<DIALECT>_DATABASE``
environment variables (and a few legacy aliases like
``MYSQL_ROOT_PASSWORD``). See ``tests/integration/conftest.py`` for the
full list.

## CI workflows

Five test workflows exist under ``.github/workflows/``. Each has a
distinct trigger and budget — knowing which one a PR will fire is part
of writing a good test.

| Workflow | Trigger | Scope | Budget |
|---|---|---|---|
| ``unit-tests.yml`` | push to ``main`` / ``develop`` / ``release/**`` | ``tests/unit/`` on Python 3.11 + 3.12 | ~5 min |
| ``matrix-tests.yml`` | every ``pull_request`` | ``tests/integration/matrix/`` (DB-free regression invariants) | < 1 min — **blocking on every PR** |
| ``integration-tests-new.yml`` | ``workflow_dispatch`` | Full integration suite per dialect (PG, MySQL, Oracle, SQL Server, DB2, CosmosDB) — boots Docker | ~20 min |
| ``check-coverage.yml`` | ``workflow_run`` after Unit + Integration | Combined coverage threshold gate | ~3 min |
| ``code-quality.yml`` | every ``pull_request`` | black, isort, flake8, mypy, ``lint_patterns.py``, ``check_api_docstrings.py`` | ~2 min |

Practical consequences:

- **Unit tests do not block PRs from external contributors** — they
  fire on push to protected branches, not on ``pull_request``. The
  matrix-tests job is the blocking PR gate.
- **Integration tests are gated on ``workflow_dispatch``** to respect
  the GitHub Actions minutes budget. Run them manually before merging
  anything that touches the dialect plugins.
- **Coverage is checked combined** (unit + integration), via
  ``check-coverage.yml`` triggered after both upstream workflows
  complete. Local ``--cov`` runs only see the unit slice.

## Coverage

Project floor: **80 % combined unit + integration coverage**.

```bash
# Local coverage report (unit only)
python -m pytest tests/unit/ --cov --cov-report=term-missing

# Track trend + fail on drop (used by check-coverage.yml)
python scripts/monitor_coverage.py
```

``scripts/monitor_coverage.py`` reads the floor from
``COVERAGE_THRESHOLD = 80.0`` and writes a history file
(``coverage_history.json``). It alerts on drops and emits an HTML
report under ``htmlcov/``.

The coverage source paths are configured under ``[tool.coverage]`` in
``pyproject.toml``. Tests, docs and scripts are excluded.

## Writing a new test

1. **Pick the layer.** Pure-logic, no external dependency → ``tests/unit/<mirror_path>/``. Touches a database, network, or Docker → ``tests/integration/``.
2. **Pick the marker.** ``pytestmark = [pytest.mark.unit]`` (or ``integration``). Add dialect markers when the test only makes sense for one dialect.
3. **Mirror the source path.** Test for ``core/sql_parser/foo.py`` lives at ``tests/unit/core/sql_parser/test_foo*.py``.
4. **Use ``tmp_path``.** Never write to the project root or the user's filesystem. ``tmp_path`` is an auto-cleaned fixture.
5. **Keep tests independent.** No ordering dependencies, no shared mutable state. The unit suite runs with ``-n auto --dist=loadscope`` (workers per module).
6. **Avoid mocking what you own.** Mock external services (databases, HTTP). Don't mock internal classes — instantiate them with the same constructor a real caller would use; that catches refactor breakage instead of hiding it.
7. **Document the *why*, not the *what*.** Test names already describe the *what*; the docstring is for the regression context (PR number, ticket, behavior the test pins).

Example unit test (matches the project style):

```python
"""Unit tests for ``api._client_factory.normalize_migrations_dirs`` (PR-D4)."""

from pathlib import Path

import pytest

from api._client_factory import normalize_migrations_dirs
from config import DbliftConfig
from config.database_config import DatabaseConfig

pytestmark = [pytest.mark.unit]


def _config():
    return DbliftConfig(database=DatabaseConfig(url="postgresql+psycopg://u:p@h:5432/n"))


def test_str_path_is_assigned_as_primary_directory():
    cfg = _config()
    normalize_migrations_dirs(cfg, "/tmp/migrations")
    assert cfg.migrations.directory == "/tmp/migrations"


def test_list_first_entry_is_primary_rest_extras():
    cfg = _config()
    normalize_migrations_dirs(cfg, ["/tmp/a", "/tmp/b", "/tmp/c"])
    assert cfg.migrations.directory == "/tmp/a"
    assert cfg.migrations.directories == ["/tmp/b", "/tmp/c"]
```

## Gotchas

### License guard auto-bypass (unit tests)

The runtime license guard (``core.licensing._guard._refresh_state``)
calls ``sys.exit(78)`` when no valid license is present. The unit
conftest patches this to a no-op for every unit test (autouse fixture
``_bypass_license_guard``). If you bypass the conftest — for instance
by importing the module via ``importlib`` outside the test runner —
the guard will fire and the process will exit cleanly with no
traceback. If a unit test seems to hang or vanish, that is the cause.

Integration tests, by contrast, *require* a real license key. They
read it from the ``DBLIFT_LICENSE_KEY`` environment variable (set in
CI from the ``DBLIFT_LICENSE_KEY`` repository secret). Locally, set
it before invoking pytest:

```bash
export DBLIFT_LICENSE_KEY=...
python -m pytest tests/integration/...
```

### MacOS + Colima + ARM

The integration helpers in
``tests/integration/_container_readiness.py`` detect Colima and ARM
architectures and adapt the docker run flags
(``MYSQL_DOCKER_COMMAND``, ``_apply_mysql_docker_run_options``). If
container startup fails on a Mac, check those branches before blaming
the test.

### Logs

CLI logs are *off by default* in pytest (``log_cli = false`` in
``pytest.ini``) — streaming every INFO line during a 1000-test run was
adding 2-3× overhead. To see them while debugging, re-enable for a
single invocation:

```bash
python -m pytest tests/unit/foo.py -o log_cli=true
```

Captured logs from failing tests are still printed by pytest's default
capture mechanism.

## Continuous Integration

| Trigger | Workflows fired |
|---|---|
| Open a PR | ``code-quality``, ``matrix-tests`` (blocking) |
| Push to ``develop`` / ``main`` / ``release/**`` | ``unit-tests``, ``code-quality`` |
| Manual via Actions UI | ``integration-tests-new`` (per-dialect, ~20 min) |
| After Unit + Integration succeed | ``check-coverage`` (combined gate) |

The matrix-tests workflow is the practical PR gate: it boots no
containers, finishes in under a minute, and pins the cross-cutting
invariants surfaced during the stabilization program (stdout JSON
contract, dry-run purity, argparse global-flag preservation, dialect
capability matrix, schema-SQL fan-out).

## Next steps

- Read [Contributing Guidelines](contributing.md)
- See [Development Setup](setup.md)
- Check [Adding Database Support](adding-database-support.md)
