# Contributing Guide

How to contribute to DBLift.

## Development Workflow

### 1. Create Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Development Cycle

1. Make changes
2. Run tests
3. Check code quality
4. Update documentation
5. Submit pull request

## Code Quality

### Style Guide

- Follow PEP 8
- Use type hints
- Maximum line length: 100 characters (as per pyproject.toml)
- Use descriptive variable names
- Document classes and functions

### Running Checks

```bash
# Run all checks
./scripts/check_code_quality.sh

# Individual checks
mypy .
flake8 .
black . --check
isort . --check-only
```

### Pre-commit Hooks

1. **Install**:
```bash
pip install pre-commit
pre-commit install
```

2. **Run Manually**:
```bash
pre-commit run --all-files
```

## Documentation

Update documentation when you:

- Add new features
- Change existing functionality
- Fix bugs with user-visible impact
- Add new database support

Documentation locations:
- `docs/` - MkDocs documentation
- Docstrings - API documentation
- `CHANGELOG.md` - Release notes

## Pull Request Process

### 1. Prepare Changes

- Complete all TODOs
- Run all tests
- Check code quality
- Update documentation
- Add test cases

### 2. Create Pull Request

- Clear description
- Link related issues
- List breaking changes
- Update CHANGELOG.md

### 3. PR Checklist

The canonical checklist lives in
[`.github/pull_request_template.md`](../../.github/pull_request_template.md)
— it auto-populates when you open a PR. The short version:

- [ ] Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`type(scope): subject`).
- [ ] `pre-commit run --all-files` passes locally (black, isort, flake8, mypy).
- [ ] Coverage did not regress (current floor: 80 % combined; see [Testing Guide](testing.md#coverage)).
- [ ] No new entry added to `.flake8` `ignore` list without a cleanup ticket.
- [ ] If behavior changed, a regression test was added under `tests/`.
- [ ] If architectural decision, an ADR was added under `docs/adr/`.
- [ ] All Bugbot `High` / `Medium` review threads resolved before merge.

### 4. Review Process

- Address review comments
- Keep PR focused
- Maintain clean commit history

## Code Review Guidelines

### Automated gates (must be green before merge)

| Check | Workflow / file | What it enforces |
|---|---|---|
| Formatting | `black`, `isort` (in `code-quality.yml`) | PEP 8, 100-char lines, import order. |
| Linting | `flake8` (`.flake8` config) | Style + simple bug patterns. |
| Type-check | `mypy` (`pyproject.toml`) | Annotations on `api/`, `cli/`, `config/`, `core/`, `db/`. |
| Complexity | `xenon --max-absolute F --max-modules F --max-average A` (`complexity.yml`) | Per-function complexity ceiling. |
| AST patterns | `scripts/lint_patterns.py` | `cli-print-stdout`, `enum-str-conversion`, `dialect-string-literal`. Zero-baseline. |
| Public-API docstrings | `scripts/check_api_docstrings.py` | Every public name under `api/` carries a docstring. |
| Coverage | `scripts/monitor_coverage.py` (`check-coverage.yml`) | Combined unit + integration ≥ 80 %. |
| Cross-cutting regression | `matrix-tests.yml` | Stdout JSON contract, dry-run purity, dialect capability matrix. **Blocking on every PR.** |

### Human review focus

CI catches mechanical issues; reviewers focus on:

1. **Why, not what.** The diff shows *what* changed; the PR description and commit message must explain *why* the change is correct (and why it stops at this scope).
2. **Behavior preservation.** For `refactor`-typed PRs: does any existing test cover the new code path? If not, name the test that *would* have caught a regression.
3. **Stabilization alignment.** New code paths must trace back to a section of [docs/stabilization-plan.md](../stabilization-plan.md). Out-of-plan code requires explicit acknowledgment.
4. **Dialect isolation.** Framework code (`api/`, `cli/`, `config/`, `core/`) must not branch on dialect strings — those belong in `db/plugins/<dialect>/quirks.py`. The `lint_patterns.py` `dialect-string-literal` rule catches the obvious cases; reviewers catch the conceptual ones.
5. **Bugbot threads.** Cursor Bugbot posts inline review comments on every PR. `Low`-severity ones can be deferred with a justification reply; `High` / `Medium` ones must be fixed or explicitly rebutted before merge.

### Review comments

- Be concrete — quote the line, suggest the diff.
- Distinguish `nit`, `consider`, `must-fix`. Reviewers waste cycles when severity is unclear.
- If the change is small, push a fix-up commit instead of leaving a comment.

## CI/CD Workflows

The full table of test workflows (trigger, scope, time budget) lives in
the [Testing Guide → CI workflows](testing.md#ci-workflows) section.
Quality / security / complexity workflows complement those:

- `code-quality.yml` — black, isort, flake8, mypy, `lint_patterns.py`, `check_api_docstrings.py`. Runs on every PR.
- `complexity.yml` — `xenon` per-function ceiling. Runs on every PR.
- `security.yml` — `bandit` static analysis, `pip-audit` dependency vulnerabilities, `gitleaks` secret scanning. Runs on every PR.
- `build.yaml` / `docker-publish.yml` — distribution and container artifacts on release.

The matrix-tests workflow is the practical PR gate (≪ 1 min, blocking).
The full per-dialect integration suite stays on `workflow_dispatch` to
respect the GitHub Actions minutes budget.

## Getting Help

1. Check existing issues
2. Review documentation
3. Ask in pull request
4. Create new issue

## Support

- GitHub Issues: Bug reports, feature requests
- Pull Requests: Code contributions
- Documentation: Usage questions

## Next Steps

- Read [Development Setup](setup.md)
- See [Testing Guide](testing.md)
- Check [Adding Database Support](adding-database-support.md)
