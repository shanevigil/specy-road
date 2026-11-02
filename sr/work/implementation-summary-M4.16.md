# Implementation summary for M4.16

## Summary

- **A1:** `handoff status` (text and `--json`) and `review list` now report, per leaf, the number of review rounds (distinct reviewed commits) and the time from the first filed review to the latest, as `rounds: N, first to latest: 1d 2h 5m` (`n/a` with fewer than two reviews, `under 1m` below a minute). The values are derived, not stored. They come from `history/`, where each copy is written once by `review record`, so its mtime is its filing time, plus each `REVIEW-*.md` that has no copy there: `REVIEW-human.md`, which `mark-implementation-reviewed` writes without archiving, or a record written by hand. A live `REVIEW-<model>.md` that duplicates an archived record (same model, same commit) is not counted twice. A short SHA and a full SHA of one commit are one round, the same folding `review_rca.review_rounds` uses. `--json` carries `review_rounds: {rounds, elapsed_seconds, line}` on each node, including unclaimed and `complete_no_claim` nodes.
- **A2:** `docs/orchestration.md` (after the `review record` paragraph) says that both commands report this, that two or more review rounds per leaf are normal under a two-family policy, and that escalation is what marks a loop that is not converging.
- **A3:** `doctor` now lists every detached linked worktree, not only those whose HEAD the integration branch contains or whose patch it has. A review recipe's worktree, detached at an unmerged commit, shows as `detached at <sha>`. With `--fix` it removes clean detached worktrees. It leaves, and prints a `[kept]` line for, a detached worktree with uncommitted changes (`git status --porcelain` not empty, so untracked files count) and any clean one whose HEAD no local or remote-tracking ref holds, whatever its merge reason. That includes a patch that landed on the integration branch under another SHA: the content landed, but the commits did not, and removing the worktree would make them unreachable. This follows A3 as clarified on WIP in f2099fb. These kept items are not failures, so the exit code is unchanged. Main, current and locked worktrees are still skipped. A worktree that is on a branch keeps its old treatment.

## Changes

- `specy_road/review_files.py`: `round_span()`. I dropped a redundant local `import yaml` in `render_front_matter` to stay within the 400-line file cap.
- `specy_road/bundled_scripts/review_cli.py`: `review_rounds` on each node status (claimed and unclaimed), a rendered line before `policy:`, and a line in `review list` after the records. The module docstring now mentions it.
- `specy_road/bundled_scripts/doctor.py`: unmerged detached worktrees are now listed. `_keep_detached` decides what `--fix` leaves. `Finding.remove` may be `None`, and `_fix` prints `[kept]` for those items and asks only about removable ones. The worktree section heading, the module docstring and `--help` mention detached worktrees. To stay at 400 lines I reflowed the docstring, a heading, an import and a print, with no behaviour change.
- `docs/orchestration.md`: A2 paragraph.
- `tests/test_review_cli.py`, `tests/test_doctor.py`: see Added.

**Touch zones:** the files above. `docs/pm-llm-review.md` covers LLM review of planning sheets, not the implementation review gate, so it got no change. **Outside the zones, not changed:** `docs/git-workflow.md` § "Finding leftovers: `doctor`" still describes worktrees as "whose branch is gone or merged". It should gain a clause about other detached worktrees and about `--fix` leaving dirty ones. A follow-up can make that one-sentence edit; it is not needed for A1–A3.

**Existing test changed because A3 changes the behaviour it pinned:** in the `doctor_repo` fixture, `wt-wip` (detached at the unmerged `feature/rm-open`) was a look-alike that doctor did not list. Under A3 it is listed. I gave it an uncommitted file, so it stays the look-alike `--fix` leaves. The dry run now asserts that it is listed with "uncommitted changes, so --fix leaves it" (`wt-locked` is still asserted absent). The fix test asserts its `[kept]` line. The re-run after `--fix` asserts that only `wt-wip` is listed, where before it asserted "Nothing to tidy". No assertion was dropped.

## Verification

- `pytest tests/test_doctor.py tests/test_review_cli.py`: 11 and 18 passed.
- `ruff check specy_road tests scripts`: all checks passed.
- `specy-road file-limits`: OK (`doctor.py` is at 400 and `review_files.py` at 397).
- `python scripts/check_clones.py` (pylint 4.1.3 from a scratch venv): 0 new. `python scripts/check_test_private_imports.py`: 0 new. The stale baseline entries reported by both predate this change.
- `specy-road validate` and `specy-road export --check` on the dogfood fixture: OK.
- Full `pytest` at 3ce77b4: 2643 passed, 2 skipped (16m16s).
- Round 2 (gpt-6.1-sol P1 fix): `pytest tests/test_doctor.py tests/test_review_cli.py`: 30 passed. The new regression fails with the old reason-gated check and passes with the fix. `ruff check specy_road tests scripts` and `specy-road file-limits` pass. Per the coordinator, I did not rerun the full suite.

## Walkthrough

1. `specy-road handoff status <ID>` shows `  rounds: N, first to latest: …` above `policy:`. `review list <ID>` prints the same line after the records.
2. `specy-road doctor` in a repo with `git worktree add --detach ../x <unmerged branch>` lists `../x  — detached at <sha>`. `--fix --yes` removes it. If `../x` has an untracked file, the row ends `; uncommitted changes, so --fix leaves it`, and `--fix` prints `[kept] …`.

## Added

- `review_files.round_span`: computes rounds and elapsed time once, for both commands (A1).
- `round_span` branch that skips a live `REVIEW-*.md` duplicating an archived (model, commit): `history/` already holds a copy of every `review record` filing, so without the skip each record would count twice and the live file's mtime would distort the span. `_relabel_independence` rewrites the live file later.
- `round_span` short/full SHA folding via `git rev-parse`: one commit quoted two ways is one round, matching `review_rca.review_rounds`.
- `round_span` `under 1m` / `n/a` formatting: a sub-minute span would otherwise print empty; `n/a` with a single review, as the planning sheet asks.
- `review_rounds` key in `handoff status --json` (claimed and unclaimed nodes): machine-readable A1 for polling scripts.
- `doctor._keep_detached`: the A3 rule that `--fix` removes only clean detached worktrees.
- `_keep_detached` guard for "commits no branch holds": removing a clean detached worktree whose HEAD no ref contains would orphan those commits, because the worktree's reflog goes with it. It applies to every clean detached worktree, including those listed as merged by patch content (round 2: it used to be skipped unless the reason began with `detached`).
- `Finding.remove = None` and the `[kept]` lines in `_fix`: the A3 "report the rest" without counting those items as failures or prompting for them.
- `doctor_repo` fixture: `wt-wip` gets an uncommitted file (see above).
- `test_detached_worktrees_are_listed_and_fix_removes_only_clean_ones` (A3): a clean review-recipe worktree is listed and removed; a dirty one and one with commits on no branch are listed and kept, and the dirty file survives.
- `test_fix_keeps_a_landed_patch_whose_commit_no_ref_holds` (A3, round 2): regression for gpt-6.1-sol's P1. A detached worktree's commit is cherry-picked with `-x` onto `origin/dev`, so the patch is upstream but no ref holds the original commit. `--fix --yes` prints `[kept] … merged (same patch content); commits no branch holds, so --fix leaves it` and leaves the worktree at that HEAD.
- `test_rounds_and_elapsed_time_count_distinct_reviewed_commits` (A1): reviews at two commits give 2 rounds and `1d 2h 5m` in `--json`, `handoff status` and `review list`. History mtimes are set with `os.utime`, and the live copy is set far in the past to prove it is not counted.
- `test_a_single_review_has_no_elapsed_time` (A1): `rounds: 0` / `n/a` before any review, then `rounds: 1` / `n/a` with one.
- `test_a_review_with_no_history_copy_counts_and_a_short_sha_is_the_same_round` (A1): a hand-written `REVIEW-human.md` quoting a short SHA counts as a record in the same round.
- Test helpers `_record`, `_rounds_lines` in `tests/test_review_cli.py`: file a review and read the rounds line from each command.
- Mocks: none.
