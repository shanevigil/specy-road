# Implementation summary: M15.17 — review packet and record friction

Base `4a8d93bb`; code commit `d5f88a7b`.

## What changed, per acceptance item

- **A1:** New `specy_road/review_delegate_packet.py` (`ensure_packet`). If `PACKET.md` is missing, or its `**Commit under review:**` names a different commit, it builds the packet with `review_packet.build_packet` for the commit under review. It then prints `review packet is missing|was built for <sha>, not <sha>: built <path> (<n> bytes) for <sha>` to stderr and the run continues. If the packet names no commit, it is left alone, because nothing shows it is for another commit (the existing test fixtures' stub packets are like this). `review_delegate.py` calls it once, inside the leaf's run lock, for a roadmap review that is not a `--resume` (a chore reviewer and a resumed session do not read the packet). The file is 382 lines.
- **A2:** `review_packet_uncommitted_refs.py`: `_missing_refs` now skips two kinds of path that are not at the commit: one that `git check-ignore` reports as ignored (checked from the project root and from the git top), and a glob (`*?[`) that matches no file at the commit or on disk. It prints one count line (`note: N path(s) named in the packet but not at commit … are not warned about …`) instead of a warning per path. A glob that does match a committed file now counts as present and is no longer warned about.
- **A3:** `integrity.py` is **unchanged**. I tried several cases against the current mapping: lines added and removed before the suppression in an earlier commit, a suppression added to an existing line, a rename, and CRLF content. In every case `new-suppression` already gave the line number at the commit under review (`_hunk_additions` reads the `+` side of a `-U0` blob diff). I could not reproduce the mismatch the adopter reported. A new test pins the numbers for that scenario. One thing that may explain the report: `compare_integrity` sorts findings by their printed line as text, so `x.py:11` comes before `x.py:6`. That is an ordering issue, not a numbering one, and I left it unchanged.
- **A4:** `review_record_rules.py`: a new `offending_lines` returns `(where and why, text)` for each finding; `unexplained_defects` is now built from it and returns the same output as before. The `approve_defect_problem` refusal is now `verdict: approve refused: <the rule in one sentence>`, followed by one line per offence: `  notes line N <why>: <line text>` or `  findings.<key>[i] <why>: <entry>`. The rule sentence keeps the phrases existing tests check for.
- **A5:** New `specy_road/review_run_status.py` (`superseded_by`). A run that did not complete is superseded when, at the same commit, there is a valid `REVIEW-<model>.md` for the same model and node whose mtime is no earlier than the run's `ended_at` (or `started_at`), compared in whole seconds. `review_delegate.run_states` adds `superseded` to each run, and both `review list` and `handoff status` render from it. `run_lines` appends `— superseded: REVIEW-<model>.md was filed later at this commit`. `run_problems` no longer reports a superseded run, and the `handoff status` policy line no longer names it as a reviewer failure: `review_delegate.gate_policy_summary` now wraps `reviewer_run_failure.gate_policy_summary` and leaves superseded runs out. `review_cli.py` (400 lines) is unchanged.
- **A6:** `_second_observation` splits with a new `_parts`, which does not split on a separator inside a double-quoted, single-quoted or backtick span. A single quote only counts as a quote when it sits next to a non-word character, so apostrophes are not treated as quotes. The refusal now names the joining word and quotes both parts: `<why>, two observations joined by "and": "<first>" and "<second>"` (for a comma: `"<first>", "<second>"`). The explanation rule is otherwise unchanged.

## Test changes

- `tests/test_review_record_rules.py`: in `test_clause_problem`, the expected strings for the four joined-observation cases now include the A6 suffix (joining word and both parts). The cases, and the verdict for each (refused), are the same; no case was removed.
- New `tests/test_review_friction_m15_17.py` (17 tests, plus 4 added later on real refused answers). Run against the base source, 13 fail. The 4 that pass without the fix are expected to: the A3 pin, the keep-current-packet case, the backtick span (code spans were already stripped), and a conjunction inside the reason.

## Real refusals (coordinator context, round 1)

The coordinator pointed to refused reviewer answers in the main checkout's `RUN-*.log` files (M12.5, M13.12 and M14.1 ×2; the M15.2 log has no refusal, and the M8.3 logs' refusals come from test repos inside those runs). I ran each final answer through `approve_defect_problem`. Each one is still refused, so the rules are not widened, and each refusal now names its trigger (`"and"`/`"plus"` with both parts, or the defect word in the reason) and quotes the line. Four of them are verbatim cases in `test_a_real_refusal_names_its_trigger_and_quotes_the_line`. The M12.5 run was first refused with `verdict: approve with required_changes listed; use block`. That message comes from `specy_road/review_files.py` (`review_semantic_errors`), which is outside the touch zones and is a different rule from A4's, so I left it unchanged.

## Fix round 1 (gpt-6.1-sol-low)

Required change: `test_two_independent_observations_joined_by_and_are_still_refused` duplicated `test_clause_problem`. I moved its input, with its expected refusal unchanged, into `test_clause_problem` in `tests/test_review_record_rules.py` as a new row (that input was not already a row there) and deleted the standalone test. I made no other changes.

## Probes

- Class: a standalone single-input `clause_problem` assertion in the new file that duplicates a row class of `test_clause_problem`.
- `test_two_independent_observations_joined_by_and_are_still_refused`: its input was not already a row, so I added it to `test_clause_problem` and removed the standalone test. Both files pass (120 tests).
- `test_the_reported_shape_is_refused_with_the_word_and_both_parts`: this is A6's named reported shape (`base and HEAD`) and is not a row of `test_clause_problem`. I kept it, because the coordinator said to make no other changes; it could move into `test_clause_problem` the same way if reviewers want that.
- `test_a_conjunction_inside_quotes_is_not_a_split_point` (4 inputs): these test quoted spans (A6), which no `test_clause_problem` row covers. I kept them.
- `test_a_real_refusal_names_its_trigger_and_quotes_the_line`: this checks the whole `approve_defect_problem` message, not `clause_problem`, so it is not a duplicate. I kept it.

## Fix round 2 (gpt-6.1-sol-low)

Required change (A2): path extraction dropped planning globs that contain `?`, so an unmatched `?` pattern never reached the summary count. `review_packet_uncommitted_refs.py` now has one predicate, `is_glob` (`*`, `?` or `[...]`), used both when extracting a path and when matching it against files. As a result:
- A `?` is split off as a query string only when it starts one (`?name=`), via `_QUERY`.
- A glob in the last segment passes the extension check.
- A glob is kept without being looked up as a literal path, both at the top level (no `/`) and under a directory outside `_TOP`.

The existing empty-glob test now cites `*`, `?`, `[ab]`, a glob extension and a top-level glob, and asserts the count of 6 (1 ignored path + 5 globs). Run against the round-1 source it fails; with the fix it passes.

## Probes (fix round 2)

- Class: a glob token that path extraction drops or treats as a literal before the glob check runs.
- `raw.split("?")` (query stripping): it dropped every `?` glob. Fixed: only a `?name=` query is stripped. Tested with `planning/M9_?.md`.
- The extension check `ext.isalpha()`: it dropped a glob extension (`planning/M9.m?`). Fixed with `is_glob(last)`. Tested.
- A top-level token with no `/`: it was looked up as a literal and dropped (`NOTES?.md`). Fixed: a glob is kept. Tested.
- A directory outside `_TOP`: the glob was looked up as a literal path, so a glob under a directory present on disk was dropped. Fixed: a glob is kept once its directory is present. Not tested, but it is the same predicate on the same line pattern.
- `[...]`: it already survived extraction, because `_LINK` and `_CODE` keep `[`. It is now asserted (`planning/M9_[ab].md`).
- `_missing_refs`: now uses the same `is_glob`. A matching glob is still present (`test_a_glob_that_matches_a_committed_file_is_not_missing` passes).
- Existing path-noise tests (`test_review_packet.py`, including `docs/x.md#anchor`): pass. `#` stripping is unchanged.

## Fix round 3 (gpt-6.1-sol-low)

Required change (A2): a packet pattern such as `planning/**draft.md` made `Path.glob` raise `ValueError` in `_glob_matches`. Patterns come from packet text, so matching must work on any input. `_glob_matches` now matches only with `fnmatch.fnmatchcase`, which accepts any string without raising. It checks git's file lists: `ls-tree -r` at the commit, plus `ls-files -co --exclude-standard` for files on disk, from the project root and from the git top. The module has no `Path.glob` left. A pattern that is invalid or matches nothing is skipped and adds to the count. One behaviour change: a glob that matches only gitignored files on disk is no longer present, so it adds to the count. Either way it is never warned about.

## Probes (fix round 3)

- Class: a pattern from packet text reaching a matcher that raises on some inputs.
- `planning/**draft.md` (which `Path.glob` refuses): it now adds to the count. Tested; the test raises `ValueError` on the round-2 source.
- A lone `[` (`planning/M9_[.md`): `fnmatch` reads it as a literal, it matches nothing and adds to the count. Tested.
- A pattern with no wildcard (`shared/missing.md`): it is a path, not a glob, and is still warned about and listed. Tested.
- Other pattern matchers in the module: there is only `fnmatch.fnmatchcase` in `_glob_matches`. `grep` finds no `glob(` or `match(`.
- Other places a text token reaches the filesystem or argv (`_present`'s `Path.exists`, git `cat-file`/`check-ignore`/`ls-tree`): a token with a NUL byte is dropped by `_named_paths` without raising (probed by hand). Other tokens are plain strings that git rejects with a non-zero exit, which the code handles.
- A matching glob is still present: `test_a_glob_that_matches_a_committed_file_is_not_missing` passes.

## Touch zones (final)

These are the zones as listed. I edited `review_delegate.py`, `review_delegate_packet.py` (new), `review_run_status.py` (new), `review_record_rules.py`, `bundled_scripts/review_packet_uncommitted_refs.py` and `tests/`. I did not need to change `integrity.py`, `review_record_write.py` or `bundled_scripts/review_cli.py`. Note that `file_review` in `review_record_write.py` still keeps only the last 400 characters of a refusal in the run reason, so a delegated run's reason shows the quoted lines but may cut off the rule sentence.

## Verification

- `python -m pytest -q -n 4`: 4878 passed.
- `specy-road file-limits`: OK.
- `ruff check` on the changed files: clean.

## Added

- `review_delegate_packet.ensure_packet`: builds a missing or other-commit packet before a delegated review (A1).
- `review_delegate_packet.packet_commit` / `_COMMIT`: reads the commit a packet's header names, to detect a stale packet (A1).
- Guard in `ensure_packet`: a packet that names no commit is kept, because nothing shows it is stale and the existing fixtures' stubs have no commit line (A1).
- Branch in `review_delegate.delegate`: `ensure_packet` runs only for a roadmap review that is not a resume, since chores and resumes read no packet (A1).
- `review_packet_uncommitted_refs._ignored`: `git check-ignore` filter (A2).
- `review_packet_uncommitted_refs._glob_matches` / `_GLOB`: a glob that matches no file is skipped and one that matches is present (A2).
- Summary count line in `uncommitted_refs_section`: one note in place of the skipped warnings (A2).
- `review_record_rules.offending_lines`: each offence with its own text (A4).
- `review_record_rules.NOT_A_DEFECT_RULE`: the rule in one sentence for the refusal (A4).
- `review_record_rules._QUOTED` / `_parts`: quoted spans are not split points; returns the joining word (A6).
- `_second_observation` return text: names the joining word and both parts, with trailing punctuation removed from the parts (A6).
- `review_run_status.superseded_by` / `_run_time`: decides whether a failed run is superseded (A5).
- `run_states` `superseded` key, the `run_lines` suffix and the `run_problems` exclusion: mark superseded runs in review list and handoff status (A5).
- `review_delegate.gate_policy_summary` wrapper: a superseded run is no reviewer failure on the policy line (A5).
- Tests: the 20 in `tests/test_review_friction_m15_17.py` (16, plus 4 on real refused answers; the independent-observations case moved into `test_clause_problem` in fix round 1), one or more per acceptance item, including a negative A5 case (a record filed before the run does not supersede it) and an A2 case (a matching glob is present).
- Mocks: none (the tests reuse the existing fake reviewer harness from `tests/review_delegate_helpers.py`).
