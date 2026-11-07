# M22.11 — Reports say what happened

Three reports now say what happened.

A review tally that cannot be read no longer looks like a leaf that landed before tallies existed. `tally_trailers` still lets `mark-implementation-reviewed` close. On an exception it prints one stderr line, `review tally: <type>: <message>; the leaf's quality numbers will be missing`, and returns `Review-tally: <ID> unreadable`. `parse_tally` reads that as unreadable. `area_quality` counts it on `unreadable`, apart from `no_tally` (no trailer). Both stay in the leaf total and out of the rates. The digest names the unreadable count on its own line, and only when it is non-zero, so a history with no unreadable tally keeps the same rows. The footnote about leaves landed before tallies were recorded stays on `no_tally` only.

`rename-refs` protects backtick and tilde fences. An opening fence has at most three spaces of indent and three or more of one character. It closes only on a line of the same character, at least as long, with at most three spaces of indent and nothing after it but spaces. An unclosed fence still runs to the end of the text. `docs/roadmap-authoring.md` states that rule.

A real `specy-road upgrade` takes the ignore note from the checkout, observed just before the `.gitignore` write and read just after, so a tracked file a new rule matches is reported as still tracked and the `git rm --cached` command is printed. The plan is still decided on a mirror whose git index is empty; that mirror's note is not printed on a real run. `--dry-run` keeps the mirror's note and labels it with `ignore_report`'s estimate header. `agent_ignores.py` is outside the touch zones and is not edited: `make_plan` replaces its `print_matches` for the mirror run and puts the original back.

Touch zones, unchanged: `specy_road/review_tally.py`, `tests/test_review_tally.py`, `tests/test_digest_quality.py`, `specy_road/bundled_scripts/planning_rename.py`, `tests/test_rename_refs.py`, `docs/roadmap-authoring.md`, `specy_road/bundled_scripts/upgrade.py`, `specy_road/bundled_scripts/upgrade_plan.py`, `tests/test_upgrade_preview.py`, `CHANGELOG.md`, `specy_road/digest.py`.

A6 is not binding: `M16.1.1` and `M16.1.2` are Not Started. No file under `tests/parity/` changed, and no `--help` text changed.

Verified with `pytest tests/test_review_tally.py`, `pytest tests/test_digest_quality.py`, `pytest tests/test_rename_refs.py`, and `pytest tests/test_upgrade_preview.py`. Related upgrade and dogfood-digest checks passed as well. File-limits, the clone gate, and the private-import gate passed.

## Added

- `UNREADABLE` — the trailer field `parse_tally` and `area_quality` share for a tally that was written and could not be read
- `parse_tally` branch for that field — a missing trailer stays `None`, so unreadable is not `no_tally`
- `area_quality` branch for `UNREADABLE` — counts it on `unreadable` and leaves it out of the rates
- `AreaQuality.unreadable` — the count the digest shows apart from `no_tally`
- digest branch that prints the unreadable line only when the count is non-zero — existing quality rows stay the same
- `_fence` — an opening or closing backtick or tilde fence (at most three spaces of indent, three or more of one character)
- `_closes` — same character, at least as long, nothing after it but spaces; keeps the span scanner under the complexity cap
- `notice` in `make_plan` — labels the mirror's ignore note as an estimate, or prints nothing when the checkout reports
- `_writes_gitignore` — the checkout note runs only when the plan writes `.gitignore`
- `_checkout_ignore_note` — `observe` just before that write and `observed` just after, on the checkout
- `test_a_failed_tally_is_visible_and_the_gate_still_closes` — a raising `leaf_tally` prints the stderr line and the unreadable trailer, and the gate still commits
- `test_an_unreadable_tally_is_counted_apart_from_no_tally` — normal, absent, and unreadable tallies in one digest, with the rates excluding the unreadable leaf
- rename-refs rows `tilde-block`, `four-backtick-holds-three`, `unclosed-tilde`, `three-space-indent`, `trailing-words-do-not-close` — the fence cases this leaf adds to the existing whole-id test
- `test_a_tracked_file_a_new_rule_matches_is_reported_from_the_checkout` — through `run_upgrade`, the real run says the file stays tracked and prints the untrack command; the dry run prints the estimate header
- mocks: none
