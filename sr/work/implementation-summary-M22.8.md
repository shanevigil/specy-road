# Implementation summary: M22.8 — init project ends with the next steps

## Summary

A successful `specy-road init project` now ends stdout, after the `Initialized` line and any `Recorded project_root` line, with a `Next steps (run from <dir>):` block. `<dir>` is the git root that contains the target, or the target itself outside a git repository. The three steps are: set `integration_branch` and `remote` in `<prefix>roadmap/git-workflow.yaml` (the same prefix the `wrote` lines use; `sr/` in a nested layout), `git add -A && git commit -m "specy-road init"`, and `specy-road validate`. Outside a git repository, `git init` is step 1 and the rest are renumbered. `--dry-run` returns before the block. A refused run (existing manifest without `--force`, missing template, bad `--profiles`) still returns earlier, with the same exit code and no stdout.

## Changes

- `specy_road/init_project.py` — `_scaffold` returns whether the target is inside a git repository (`top is not None`). `run_init_project` prints the block only after a real run's closing lines.
- `tests/test_init_project_reports.py` — exact last lines in a repository, the `sr/` prefix and the named git root when the target is not the working directory, the `git init` step outside a repository, and no block for `--dry-run` or a refusal. Existing `wrote` / `would write` listing comparisons are unchanged.
- `tests/test_init_project.py` — the subprocess scaffold run asserts the block.
- `docs/install-and-usage.md` — the new-project line says init prints these steps.
- `CHANGELOG.md` — `[Unreleased]` Added entry.

## Touch zones (final)

`specy_road/init_project.py`, `tests/test_init_project_reports.py`, `tests/test_init_project.py`, `docs/install-and-usage.md`, `CHANGELOG.md`.

Call sites outside the zones import `init_project` but do not compare a successful run's full stdout, so none of them change. `wrote`, `skipped` and dry-run lines are unchanged.

## Verification

- `pytest tests/test_init_project_reports.py tests/test_init_project.py -q` — 15 passed.

## Added

### Helpers

- `_next_steps` in `tests/test_init_project_reports.py`: one exact-text block for the in-repo, nested and outside-a-repository assertions.

### Branches or guards

- `if not in_git` in `run_init_project`: prepend `git init` and renumber when the target is outside a git repository.

### Mocks

- `monkeypatch` of `project_template_root` in `test_a_refused_run_prints_no_next_steps`: the missing-template refusal is otherwise unreachable while the package templates are installed.

### Tests

- `test_a_refused_run_prints_no_next_steps`: an existing manifest, a missing template and a bad `--profiles` value print no block and keep their exit codes.
