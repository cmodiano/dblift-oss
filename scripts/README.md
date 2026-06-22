# dblift OSS Scripts

This directory intentionally contains only the scripts used by the public
repository workflow.

## Local Quality Gate

```bash
./scripts/check_code_quality.sh
```

This runs the same formatting, import ordering, flake8, mypy, AST-pattern,
docstring, and line-length checks used by CI.

## Release Build Helper

`build_distributions.py` is used by `.github/workflows/build.yaml` to create
release archives and standalone executables.
