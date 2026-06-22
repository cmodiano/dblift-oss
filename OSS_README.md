# DBLift OSS Repository

Public DBLift package repository.

## Boundaries

Internal packaging and sync notes are maintained outside this tree.

## Regenerate (initial)

```bash
python3 scripts/export_oss_repo.py /path/to/empty/dblift-oss
```

## Sync (existing checkout)

```bash
python3 scripts/export_oss_repo.py /path/to/dblift-oss --update --no-git-init
cd /path/to/dblift-oss
python3 -m pytest tests/unit/ -n auto --dist=loadscope -q --no-header
git status
```

Check the internal release runbook before the first incremental sync.

## Tests

```bash
python3 -m pytest tests/unit/ -n auto --dist=loadscope -q --no-header
```
