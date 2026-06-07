# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) in
[MADR](https://adr.github.io/madr/) format.

## Filename convention

```
NNNN-short-kebab-case-title.md
```

Numbers are assigned sequentially and never reused. Once an ADR is
merged, it is immutable. To change a decision, write a new ADR that
supersedes the previous one.

## Index

| # | Title | Status |
|---|---|---|
| 0001 | Adopt MADR format for ADRs | Accepted |
| 0002 | Stabilization program instead of new features until v2.0 | Accepted |
| 0003 | Drop Python 3.8 support | Superseded by 0004 |
| 0004 | Bump minimum Python to 3.11 | Accepted |
| 0005 | stdout is machine-readable when --format is machine-readable | Partially superseded by 0008 |
| 0006 | MigrationType matching helpers | Accepted |
| 0007 | Dialect capabilities matrix | Accepted |
| 0008 | CommandOutput abstraction | Accepted |
| 0009 | Argparse parent parsers for shared flag clusters | Accepted |
| 0010 | Migration._sql_statements cache immutability | Accepted |
| 0011 | _run_preflight() centralises connect/history/populate | Accepted |
| 0012 | Oracle parser split (Phase Oracle scoping) | Accepted |
| 0013 | OperationResult CLI reporting contract | Accepted |
| 0015 | History-table identifier normalization | Accepted |
| 0016 | Rich console output | Accepted |
| 0026 | Dialect plugin isolation (DialectQuirks boundary) | Accepted |
| 0027 | Generator isolation | Accepted |
| 0028 | Introspection architecture | Accepted |

## Template

Copy `0000-template.md` for new ADRs.
