SHELL := /bin/bash

# ── Directories ──────────────────────────────────────────────────────────────
TESTS_CORE := tests/unit/core
TESTS_DB   := tests/unit/db
TESTS_API  := tests/unit/api tests/unit/cli tests/unit/config tests/unit/scripts tests/unit/sqlite
TESTS_ROOT := $(shell find tests/unit -maxdepth 1 -name 'test_*.py')

PY       := python3
PYTEST   := $(PY) -m pytest
COVERAGE := $(PY) -m coverage

PYTEST_FLAGS := -q --tb=short --import-mode=importlib
COV_FLAGS    := --cov=. --no-cov-on-fail

# ── Default ──────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo "Targets:"
	@echo "  test       Run all unit tests in parallel (no coverage)"
	@echo "  cov        Full parallel coverage run  →  coverage.json"
	@echo "  baseline   Save .coverage  →  .coverage.base"
	@echo "  cov-new    Incremental: make cov-new FILES='tests/...'"
	@echo "  cov-report Regenerate coverage.json from .coverage"
	@echo "  cov-summary Top 40 files by missing lines"

# ── Fast test run (no coverage) ──────────────────────────────────────────────
.PHONY: test
test:
	$(PYTEST) tests/unit/ -n auto $(PYTEST_FLAGS)

# ── Full parallel coverage ───────────────────────────────────────────────────
# 4 groups run concurrently; each writes its own .coverage.<group>; combined at end.
.PHONY: cov
cov:
	@rm -f .coverage .coverage.* /tmp/cov_*.log
	@echo "Starting 4 parallel coverage groups..."
	@( COVERAGE_FILE=.coverage.core  $(PYTEST) $(TESTS_CORE) -n auto $(PYTEST_FLAGS) $(COV_FLAGS) > /tmp/cov_core.log  2>&1; echo "core  done ($$?)" ) & \
	 ( COVERAGE_FILE=.coverage.db    $(PYTEST) $(TESTS_DB)   -n auto $(PYTEST_FLAGS) $(COV_FLAGS) > /tmp/cov_db.log    2>&1; echo "db    done ($$?)" ) & \
	 ( COVERAGE_FILE=.coverage.api   $(PYTEST) $(TESTS_API)  -n auto $(PYTEST_FLAGS) $(COV_FLAGS) > /tmp/cov_api.log   2>&1; echo "api   done ($$?)" ) & \
	 ( COVERAGE_FILE=.coverage.root  $(PYTEST) $(TESTS_ROOT) -n auto $(PYTEST_FLAGS) $(COV_FLAGS) > /tmp/cov_root.log  2>&1; echo "root  done ($$?)" ) & \
	 wait
	@echo "Combining coverage files..."
	@$(COVERAGE) combine .coverage.core .coverage.db .coverage.api .coverage.root
	@$(MAKE) -s cov-report
	@echo "--- Failures (if any) ---"
	@grep -lE "FAILED|ERROR" /tmp/cov_core.log /tmp/cov_db.log /tmp/cov_api.log /tmp/cov_root.log 2>/dev/null \
		| xargs -I{} sh -c 'echo "=== {} ==="; grep -E "FAILED|ERROR" {}' || true

# ── Save baseline ────────────────────────────────────────────────────────────
.PHONY: baseline
baseline:
	@cp .coverage .coverage.base
	@$(PY) -c "import json; d=json.load(open('coverage.json')); print('Saved .coverage.base at', str(round(d['totals']['percent_covered'],1)) + '%')"

# ── Incremental run ───────────────────────────────────────────────────────────
# Usage: make cov-new FILES="tests/unit/core/foo.py tests/unit/db/bar.py"
# Uses -p no:xdist so coverage run --append works (xdist workers ignore COVERAGE_FILE).
.PHONY: cov-new
cov-new:
	@[ -n "$(FILES)" ] || { echo "Usage: make cov-new FILES='path/to/test_*.py'"; exit 1; }
	@[ -f .coverage.base ] || { echo "No .coverage.base — run 'make cov && make baseline' first"; exit 1; }
	@echo "Incremental coverage: $(FILES)"
	@cp .coverage.base .coverage
	@$(COVERAGE) run --append -m pytest $(FILES) -p no:xdist $(PYTEST_FLAGS)
	@$(MAKE) -s cov-report

# ── Regenerate coverage.json from .coverage ──────────────────────────────────
.PHONY: cov-report
cov-report:
	@$(COVERAGE) json -o coverage.json -q
	@$(PY) -c "import json; d=json.load(open('coverage.json')); t=d['totals']; print(f'Coverage: {t[\"percent_covered\"]:.1f}%  ({t[\"covered_lines\"]}/{t[\"num_statements\"]} lines, {t[\"missing_lines\"]} missing)')"

# ── Top 40 files by missing lines ────────────────────────────────────────────
.PHONY: cov-summary
cov-summary:
	@$(PY) -c "import json; d=json.load(open('coverage.json')); rows=sorted([(f['summary']['missing_lines'],f['summary']['percent_covered'],n) for n,f in d['files'].items() if f['summary']['missing_lines']>0],reverse=True); [print(f'{miss:5d} miss  {pct:5.1f}%  {name}') for miss,pct,name in rows[:40]]"
