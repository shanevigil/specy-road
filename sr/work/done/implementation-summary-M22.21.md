# Implementation summary for M22.21

## Summary

Three places where a preview, a rollback or a matcher did not match the real thing now do.

- **A1, verify brackets.** `brainstorm verify` drops a citation marker only from the page, and only where the quote leaves it out. A quote with no marker is compared exactly as before. A marker the quote keeps must sit at that place on the page, among any others there. `[44]` against `[43]` and `[b]` against `[a]` are `not-found`.
- **A2, dry-run digest.** Once validate has passed on the copy, the scratch repository takes the checkout's `HEAD`, refs, remote names and shallow boundary, and reads objects through `objects/info/alternates`. The digest then renders from the same history as the real run, so a current digest with Quality by area is predicted as no write, and the real run writes none.
- **A3, apply rollback.** The batch snapshot records a link as its text. It also records an in-repo target wherever that target lives, because `safe_write.moving` renames the target and unlinks the link. A refused batch recreates the link and puts the target back at its old path with its old bytes.
- **A4.** `docs/brainstorming.md` verify paragraph and CHANGELOG [Unreleased] Fixed are updated.
- **A5.** Not binding: `tests/parity/` does not exist on this branch, so no golden transcript was captured or changed.
- **A6.** Informational. Package is +85 net against the +40 estimate, because the digest reads more git state than the planning sheet assumed (see below).

## Decisions a reviewer should check

1. **An existing test's expectation changed, because A1 requires it.** `test_check_source_matches_page_text_variants_both_ways` asserted that the eight citation rows match in both directions. The reverse direction (a quote with a marker against a page without one) contradicts A1: "drops a bracket only when it is a citation marker on the page" and "a quote that keeps a bracket must match it exactly". I moved those eight rows to a `_CITED` list and a new test, `test_a_citation_marker_is_dropped_from_the_page_only`. It still asserts the page-side match and now asserts `not-found` for the reverse. No row was dropped, and the typographic rows stay in the both-ways test. If the reverse direction was meant to keep matching, A1's text needs changing.
2. **The history source is the copy's own repository, not a parameter to rendering.** The planning sheet suggests "a separate history source passed to rendering". That needs `digest.py` and `review_tally.py`, which are outside the touch zones, and `load_roadmap`'s milestone demotion reads git through the same directory. Alternates are the read-only link: git writes new objects only to the local object directory. The test snapshots every file under the live `.git` around the dry run and asserts they are unchanged.
3. **Refs and remotes had to come too, not only commits.** Moving `HEAD` alone was not enough. `demote_pending_milestone_rollups` resolves the integration ref through `policy_source`, so a milestone rendered Complete in the copy and In Progress in the checkout, which is a digest difference. The copy's remotes carry only the name (their URL is the checkout path) and are never fetched.
4. **The copy keeps its synthetic commit for validate.** The history step runs after validate, so validate sees exactly what it saw before.

## Known limits, left as they are

- `upgrade`'s copy skips `work/`, so review records are absent there. A milestone approved but not yet closed could render held in the dry run and released in the real run. I read this from `Mirror` and the gate and did not reproduce it. Fixing it means changing what the mirror copies, outside this leaf.
- A checkout with an invalid graph keeps the synthetic history for the dry run's `digest --check` line. Nothing is regenerated from an invalid graph, and the exit code is 1 either way. This is the previous behaviour.
- A non-git checkout with a valid graph still exits 2, but the message now reads `git rev-parse failed in the checkout`, not `git ls-files failed in the temporary copy`.
- A reftable checkout is not handled: `.git/HEAD` is copied as a file, and under reftable that file is a stub. Not tested.
- A quote that keeps a marker, against a page with a marker right after an opening bracket (`([43] foo`), does not get the space folding the markerless path gets. A quote with no marker is unaffected.

## Changes

- `specy_road/bundled_scripts/brainstorm_verify.py`: `_norm(citations=)`, `_on_page`.
- `specy_road/bundled_scripts/upgrade_generated.py`: `use_live_history`; `regenerate` docstring.
- `specy_road/bundled_scripts/upgrade.py`: `_check(before_digest=)`, `_dry_run` passes it; module docstring.
- `specy_road/bundled_scripts/roadmap_crud_dependency_ops.py`: `_snapshot`, `_restore`.
- `tests/test_brainstorm_verify.py`, `tests/test_upgrade_preview.py`, `tests/test_roadmap_apply.py`.
- `docs/brainstorming.md`, `CHANGELOG.md`.

**Final touch zones:** the listed zones are accurate, and no path outside them changed. `specy_road/archive_ops.py` is listed but needed no change: the rollback fix is entirely in the snapshot. Its descriptor work moved to M22.29.

The planning sheet's fifth table row (a parent swapped between walk and replace) moved to M22.29 and is not in this leaf.

## Verification

- `python -m pytest tests/test_brainstorm_verify.py tests/test_roadmap_apply.py tests/test_upgrade_preview.py`: recorded in READY.
- `python -m pytest -n 4` (whole suite, at the final code): 6440 passed in 10m31s. Too long for one `--run`, so it is recorded with `--verify`.
- `specy-road file-limits`: recorded in READY. `ruff check` on the touched package and tests: passed.
- `specy-road validate`, `export --check` and `digest --check` on the dogfood fixture: passed.
- Red checks, each by reverting one fix and running the file:
  - `brainstorm_verify.py` at base: 11 failed, in the page-only test and the new not-found rows.
  - `roadmap_crud_dependency_ops.py` at base: both sheet-link rows failed.
  - `before_digest()` call removed: the digest parity rows and the failed-history-step rows failed.
  - `shallow` copy disabled: the `shallow` row failed, the `full` row passed.
- A non-git checkout, compared with the base commit by script: invalid graph exits 1 and valid graph exits 2, on both.

## Added

Helpers and branches:

- `_on_page` (`brainstorm_verify.py`): the A1 rule; `check_source` needs one place that knows a quote's markers.
- `_norm(citations=)`: keeps markers for the positional comparison; the default is the old behaviour.
- `_KEPT`, `_SKIPPED` regexes: a marker the quote keeps, and the page markers a quote may skip.
- `if not words` in `_on_page`: a quote of markers alone (`[43]`) stays `not-found`, pinned by the existing `test_check_source_still_needs_the_same_words` row.
- `if kept == words` in `_on_page`: a quote with no marker takes the old comparison exactly, so nothing regresses for it.
- `use_live_history` (`upgrade_generated.py`): A2.
- `ask` inner function: three checkout questions share one `checked` call.
- `if shallow.is_file()`: without the boundary the copy's log fails on missing parents; reached by the `shallow` test row.
- `for name in remotes`: `policy_source` reads `git remote`; reached by the `shallow` row (its clone has `origin`) and the `remote-add` failure row.
- `before_digest` parameter on `_check`: the step must run between validate and the digest render.
- `_snapshot` (`roadmap_crud_dependency_ops.py`): A3.
- `target.is_relative_to(root.resolve())`: a target outside the repo is never read or written back.
- `isinstance(was, str)` branch in `_restore`: recreates a link as a link.

Tests:

- `test_a_citation_marker_is_dropped_from_the_page_only`: page-side match and the reverse `not-found`; takes the eight rows from the both-ways test (decision 1).
- `test_a_quote_that_keeps_a_bracket_matches_it_on_the_page`: a kept marker matches, including among others and with `[sic]`.
- Three rows on `test_check_source_still_needs_the_same_words`: `[43]`/`[44]`, `[a]`/`[b]`, and a marker at the wrong place.
- `test_dry_run_and_real_run_agree_on_a_current_digest` (`full`, `shallow`): the A2 case, and that live `.git` is unchanged.
- `test_a_failed_history_step_stops_the_dry_run`: each `checked` call in `use_live_history` is reachable and exits 2.
- `test_a_refused_entry_after_an_archive_restores_a_sheet_link` (target inside and outside the snapshot paths): the A3 case.
- Test helpers `_landed_leaf`, `_shallow_clone`, `_snapshot_git`: setup for the above.

Mocks:

- A local `git_subprocess.run` stub in `test_a_failed_history_step_stops_the_dry_run`: forces a failed or timed-out git call, which a real repository will not produce on demand. The existing `_stub_git` could not be used because these commands are also called earlier by other code.
