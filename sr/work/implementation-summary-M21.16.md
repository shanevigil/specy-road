# Implementation summary: M21.16 `upgrade-scratch-git-and-regen`

## What changed

- **A1, scratch git env.** `ignore_report.scratch_git_env()` (public) returns `os.environ` minus `_REPO_ENV`. `ignore_report._git` uses it. So do `Mirror.build`'s `git init` (upgrade_plan.py) and both `git -C copy.repo` calls in `upgrade._dry_run`. After `Mirror.build`, if `copy.repo/.git` is not a directory, `_dry_run` prints `error: git init failed in the temporary copy …; nothing was validated` and returns 2 without validating.
- **Beyond the literal A1 list (needed for A2):** with `GIT_DIR`+`GIT_WORK_TREE` inherited, `validate_at` on the copy ran its own git calls against the caller's repository. It crashed in `validate_stale_commands.warn_unregistered_commands` (`relative_to` ValueError). So `_dry_run` runs its whole copy block inside `upgrade_generated.scratch_environ()`, which strips the same variables from `os.environ` for the duration and restores them afterwards. Without it, the GIT_DIR row of A2 raises instead of completing.
- **A3, regeneration.** `_check(project, tracked_in, verb)` runs validate. When validate passed, it prints `== generated files` and calls `upgrade_generated.regenerate()`, then runs `digest --check`. `regenerate` writes `roadmap-context.md` (`render_digest`) when it is missing or drifted. It writes `roadmap.md` (`export_markdown(load_roadmap(...))`) when `git ls-files --error-unmatch roadmap.md` succeeds in the checkout and the file is drifted. Any path that `resolves_outside(project, path)` is refused. Lines printed: `wrote|would write <rel> (specy-road digest|export)`, `refused <rel> (a symlink leads outside the project)`, or `generated files already current`. The `== next` digest line now appears only when `digest --check` still fails or a write was refused (an invalid graph regenerates nothing, so the line stays).
- **Dry run.** The same comparison runs on the copy and writes into the copy only, with `would write` wording. The tracked check reads the real checkout, because the copy's single commit tracks everything. **Limitation:** the copy has no git history, so the history-derived digest sections (Quality by area) render empty there. A dry run on a checkout whose committed digest carries such a section reports `would write roadmap-context.md`, and the copy's `digest --check` reports drift. The copy's `digest --check` already had that property before this leaf. Rendering from the real checkout instead was tried and rejected: `render_digest` saves `.specyrd/cache/roadmap-history.json` into the checkout, which the dry-run guard (correctly) flags. The A4 dry-run row therefore uses a hand-drifted digest.
- Docstring step 5 and the trailing paragraph of `upgrade.py`, the upgrade paragraph in `docs/install-and-usage.md`, and two `[Unreleased] Fixed` bullets in `CHANGELOG.md`. `UPGRADE_STEP_LABELS` is unchanged; step 5's first line keeps the ``validate``, then ``digest --check`` shape the parser reads.

## Fix round 1 (gpt-6.1-sol-low, P2)

**Class:** upgrade read a generated file before checking the project boundary. A link out was opened, and a target that is not UTF-8 raised `UnicodeDecodeError` before the refusal printed. The related inside-project case is a non-UTF-8 generated file, which also raised instead of being treated as drifted.

**Rule (one, in `regenerate`'s docstring):** a generated path that leads out of the project is refused before it is read; anything else is compared as bytes. `regenerate` now checks `resolves_outside` first. A link out is refused even when its target's bytes happen to match. It compares `read_bytes()` with the UTF-8 render. `_check` applies the same boundary to `digest --check`: an outside digest is reported not current and `cmd_digest` (which uses `read_text`) is never called on it. That holds when validate failed and nothing was regenerated, too. This is folded into the return expression, so `_check` gains no branch.

## Probes

- `regenerate`, tracked `roadmap.md` linked to an outside file with bytes `ff fe 00`: refused, outside bytes kept, digest written. Was `UnicodeDecodeError` (new row `tracked-roadmap-md-link-to-outside-file`; fails before the fix).
- `regenerate` and `_check`'s `digest --check`, `roadmap-context.md` linked to an outside `ff fe 00` file: refused, `cmd_digest` not reached, outside bytes kept. Was `UnicodeDecodeError` (existing `link-to-outside-file` row now uses those bytes; fails before the fix).
- `regenerate`, a non-UTF-8 `roadmap-context.md` inside the project: rewritten, `digest --check` OK. Was `UnicodeDecodeError` (new row `non-utf8-digest`; fails before the fix).
- `_dry_run`, both generated files linked to outside `ff fe 00` files: exit 0, two `refused` lines, outside bytes unchanged (one-off probe, not a test). The copy maps links out to its sandbox outside, so the same rule refuses them.
- Other reads in this change: the tracked check (`git ls-files`) reads no file content. `render_digest`/`load_roadmap` read the graph, not the targets. `Mirror` and `_dry_run`'s scratch git do not read the generated files. No other instance found.
- Merged `origin/WIP/improvements-0-3-1` first (it brings M21.17's writers-refuse-links-out work); `tests/test_writers_refuse_links_out.py` passes alongside.

## Fix round 2 (gpt-6.1-sol-low, P2)

**Class:** `_check`'s second value is "nothing is left for `specy-road digest`", and it was computed from `digest --check` alone. A state where regeneration never ran (validate failed) but the digest happened to be current dropped the next-step line, although A3 keeps it whenever validate fails.

**Rule (one, in `_check`'s docstring):** the generated files are done only when validate passed (so they were regenerated), nothing was refused, and `digest --check` passes. `digest --check` still runs and prints when validate fails. Only the returned value changed (`valid and current and not refused`); `_check` gains no branch.

## Probes (round 2)

- Invalid graph with an already-current digest: `digest --check` prints OK, and the next-step line is kept with exit 1. The line was dropped before the fix (the `invalid-graph` row now writes a current digest and asserts both lines; it fails against 20bc1f17).
- Invalid graph, current digest, tracked drifted `roadmap.md`: next-step line kept, `roadmap.md` not written, exit 1 (one-off probe; the same rule covers it).
- Other readers of the value: only `run_upgrade`'s `== next` step. `_dry_run` ignores it (prints no next steps). The "Fix the validate errors" step is unchanged.
- Merged `origin/WIP/improvements-0-3-1` first; no conflicts.

## Touch zones: final list

The brief's seven zones, **plus a new module `specy_road/bundled_scripts/upgrade_generated.py`**. The new code pushed `upgrade.py` to 426 lines, over its 400-line cap. Following the prompt's file-limits rule, `regenerate()` and `scratch_environ()` moved into that module. Please add it to the touch zones. No other file outside the zones was edited.

## Verification

- `pytest -n 4` full suite: 5431 passed.
- `specy-road validate / export --check / digest --check --repo-root tests/fixtures/specy_road_dogfood`: OK. `specy-road file-limits`: OK. `ruff check` on the changed files: clean.
- Red-green: with `scratch_git_env()` temporarily returning `dict(os.environ)`, the A2 rows GIT_DIR+GIT_WORK_TREE, GIT_INDEX_FILE and GIT_OBJECT_DIRECTORY fail. The GIT_COMMON_DIR row passes even unfixed: git honours it only together with a git dir, so a scratch `git init`/`add` does not reach R through it alone. The row is kept because A2 requires one row per `_REPO_ENV` name.

## Added

### Helpers / branches / guards
- `ignore_report.scratch_git_env()`: the one stripped-environment helper A1 requires, shared with `ignore_report._git`.
- `upgrade_generated.scratch_environ()`: the copy's `validate` must not follow the caller's `GIT_DIR` (crash, and git reads against the caller's repository otherwise).
- `upgrade_generated.regenerate()`: A3 writes, refusal and output lines; it lives in a new module because of the file-limits cap.
- `_dry_run` guard `if not (copy.repo / ".git").is_dir(): … return 2`: A1 says a dry run with no scratch `.git` validates nothing.
- `_check` now takes `tracked_in` and `verb` and runs the `generated files` section between validate and digest --check, only when validate passed (A3).

### Mocks
- `monkeypatch.setattr(upgrade.Mirror, "build", …)` wrapping the real build and deleting `.git`: the only way to reach the no-`.git` guard without breaking git itself.
- `monkeypatch.setattr(upgrade, "validate_at", validated.append)`: records that nothing was validated (same pattern as the existing preview tests).

### Fix round 1
- `regenerate`: the boundary check moved before the read and the comparison became bytes; no new branch.
- `_check`: `not resolves_outside(...)` short-circuits `cmd_digest` for a digest that is a link out; no new branch.

### Fix round 2
- `_check`: the returned "generated files done" is `valid and current and not refused`; no new branch.

### Tests
- `tests/test_upgrade.py::test_upgrade_regenerates_the_drifted_generated_files`: the A4 table, 10 rows after fix round 1 (fix round 2: the `invalid-graph` row starts from an already-current digest) (`tracked-roadmap-md-link-to-outside-file` and `non-utf8-digest` added; `link-to-outside-file` uses non-UTF-8 bytes). It replaces `test_a_missing_digest_is_a_next_step_not_a_failure`, whose expectation (a missing digest stays a next step) A3 changes; that expectation is now the invalid-graph and link rows.
- `tests/test_upgrade.py` helpers `_finished_leaf`, `_hand_drifted_digest`, `_tracked_index`, `_untracked_index`, `_invalid_graph`, `_dangling_link_out`, `_link_to_outside_file`, `_tracked_index_link_to_outside_file`, `_non_utf8_digest`, `_state`, `_files`: row setups and the byte or link state each row asserts. `_finished_leaf` reuses `land` from `tests/test_digest_quality.py` and `commit`/`git` from `tests/test_history_walk.py`.
- `tests/test_upgrade_preview.py::test_dry_run_never_touches_the_repository_a_git_variable_names`: the A2 table, one row per `_REPO_ENV` name. Each row checks HEAD, commit count, object count, index bytes, staged names and working files of a second repository.
- `tests/test_upgrade_preview.py::_repo_state`: the snapshot that A2 compares.
- `tests/test_upgrade_preview.py::test_a_dry_run_whose_copy_has_no_git_validates_nothing`: the A1 no-`.git` guard, a distinct regression not covered by either table.
