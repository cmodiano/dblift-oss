<!--
Thank you for contributing to dblift.
A project is in an active stabilization program (v1.3.x → v2.0). Only
fixes, tests, docs, and items planned in docs/stabilization-plan.md are
accepted. New features are on hold.
-->

## Summary

<!-- What does this PR do, in 1-3 sentences. Focus on the "why". -->

## Type

- [ ] `fix`: bug fix
- [ ] `refactor`: no behavior change, planned in stabilization program
- [ ] `test`: adds/updates tests
- [ ] `docs`: documentation only
- [ ] `ci`/`build`/`chore`: tooling
- [ ] `style`: formatting only
- [ ] `feat`: **frozen during stabilization**. Requires explicit approval.

## Checklist

- [ ] Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`type(scope): subject`)
- [ ] `pre-commit run --all-files` passes locally (black, isort, flake8, mypy)
- [ ] Coverage did not regress (current floor: 77 %)
- [ ] No new entry added to `.flake8` `ignore` list without a cleanup ticket
- [ ] If behavior changed, a regression test was added under `tests/`
- [ ] If architectural decision, an ADR was added under `docs/adr/`
- [ ] All Bugbot `High`/`Medium` review threads resolved before merge

## Test plan

<!-- Commands run or scenarios exercised. For CLI: include the subprocess command. -->

## Related

<!-- Issue, ADR, or prior PR this depends on. -->
