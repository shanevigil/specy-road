# Implementation summary: M22.43 (digest-is-the-same-cold-or-warm)

## What changed

A cold `digest` and one resumed from a cache written on a side branch disagreed. The cold walk follows `--first-parent`, so a dependency removed on the side branch and kept by a non-fast-forward merge is one event, dated with the merge commit. The cache was appended whenever `last_indexed_commit` was any ancestor of `HEAD`. A merged side-branch tip is an ancestor, so resume kept that branch's removal (dated with the side-branch commit) instead of the merge step. When main had also moved, applying main's later commit on top of the side-branch seed could record the removal twice.

`history_index` now appends only when the cached commit is on `HEAD`'s first-parent line. Any other ancestor, including a merged side-branch tip, is a full rebuild, which is the same walk as a missing cache. `CACHE_VERSION` is 2, so a cache already sitting at `HEAD` from before this change — including one with no removal event — is discarded and rebuilt. `docs/roadmap-history.md` states the two cases.

`digest.py` was read and not changed. The cold walk already dates the removal with the merge; the mismatch was the resume rule. `history_walk.py` was not changed: its `--first-parent` walk is the result both cache states now share.

## Touch zones

Final list, unchanged: `specy_road/history_index.py`, `specy_road/history_cache.py`, `tests/test_digest_cold_warm.py`, `CHANGELOG.md`, `specy_road/history_git.py`, `specy_road/history_walk.py`, `docs/roadmap-history.md`. `history_walk.py` needed no edit.

## Verification

- `python -m pytest tests/test_digest_cold_warm.py -q --tb=short -p no:cacheprovider`: 5 passed.
- `python -m pytest tests/test_history_cache.py tests/test_history_walk.py tests/test_digest.py tests/test_history_cli.py tests/test_digest_quality.py -n 4 -q --tb=line -p no:cacheprovider`: 78 passed.
- `specy-road file-limits`: OK (existing warnings on other files only). `ruff check` on the touched modules: clean.

## Added

Helpers and branches:

- `_full_sha` (`history_git.py`): resolve a rev to the full commit SHA `git log --format=%P` prints, so the first-parent check does not miss on an abbreviated name.
- `is_first_parent_ancestor` (`history_git.py`): true only when the cached commit is on `HEAD`'s first-parent line. A merged side-branch tip is an ancestor and must not be appended to.
- Unresolved rev returns false: git cannot answer, so the index rebuilds rather than appending.
- Equal commits return true: a cache already at `HEAD` has nothing new to walk; the caller reuses it when `head` matches, and this keeps a same-commit resume from rebuilding.
- Not an ancestor returns false: a rebase, amend or force-push still rebuilds, as before.
- Empty first-parent log returns false: no next mainline step was found, so rebuild.
- First parent of the oldest commit in `older..HEAD --first-parent` equals `older`: that is the append case. Any other parent is a fork, so rebuild.
- `_resume_point` calls `is_first_parent_ancestor` instead of `is_ancestor`: this is the rule above.
- `CACHE_VERSION` is 2: `load_cache` already rejects a different version, so every cache from before this change is rebuilt, including one whose `head` is already the merge and whose events omit the removal.

Tests:

- `test_each_cache_state_matches_the_cold_digest` (`absent`, `side-branch`, `main-before-merge`): one table. Each state renders the same `roadmap-context.md` as a cacheless walk, with exactly one `stopped depending on` line dated `2026-04-01` (the merge). `clear_memo` runs before each render. `digest` then `digest --check` exits 0 and leaves the file bytes unchanged. A marker on the cached events is gone after the side-branch state (that row rebuilds; it failed before the fix, which appended and dated the line `2026-02-01`) and still present after the main-before-merge state (that row appends).
- `test_an_older_cache_at_the_merge_without_the_removal_is_rebuilt`: a version-1 cache at the merge commit with no events is rebuilt to that same file, and the stored cache is `CACHE_VERSION` and contains `dep_removed`.
- `test_a_second_checkout_without_a_cache_matches`: a second checkout of the merge commit, with no history cache, renders the same file.
- `_dated`, `_commit`, `_repo`, `_remove_dependency`, `_main_commit`, `_merge`, `_index`, `_prepare`: build that history with fixed commit dates and leave the cache in one of the three states.
- `_stamp_cache`: writes the marker the append-versus-rebuild assertions read.
- `_assert_check_keeps_bytes`: `digest` / `digest --check` and the unchanged file.
- `_cold`: the cacheless render the other states are compared to.

Mocks:

- none
