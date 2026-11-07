# Implementation summary: M21.39 — Publish, finish's land and reviews copy, the pickup hint refuse any symlink on the path

Branch `feature/rm-ops-writers-refuse-links`. As the planning sheet asks, the first pass was built ahead of M21.37: `feature/rm-safe-write-rule-setup-writers` was merged in (`e10c4597`), and only `safe_write`'s public API is used. Implementation commits: `22473dfe`, plus a one-line test-file spacing fix. M21.37 has since landed on WIP, and WIP is merged into this branch (`56090bc9`, the rework base), so the review diff against WIP holds only this leaf's files. M21.37's files are not edited.

## Rework (on base `56090bc9`)

- **A6, history cache.** The first pass covered `ensure_cache_dir` but not `save_cache`, which still wrote with `tempfile.mkstemp` and `os.replace`. It now writes `roadmap-history.json` with `safe_write.write(root, ...)` from the project root, after `ensure_cache_dir`. A `SafeWriteError` prints one line, `warning: history cache not written: <refusal>`, on stderr and returns `False`. The other failures stay silent, as the module docstring promises. `tempfile` and `os` imports are gone. `history_index` and `digest` are unchanged: digest carries on and exits 0. Commit `e79de2b3`.
- **CHANGELOG.** The WIP merge had put this leaf's `[Unreleased] Fixed` entry in the middle of M21.37's entry, which was duplicating one line and splitting the other. M21.37's text is now byte-identical to WIP, and this leaf's entry follows it with one added sentence for A6.

## What changed

- **A1, Publish.** No code change. After M21.37, `refused_generated_files` refuses any link, so `_regenerate_for_publish` already raises with finish's sentence before anything is written. Only its docstring changed. `tests/test_ops_writers_refuse_links.py::test_publish_refuses_a_linked_generated_file` pins it with two rows: an in-repo `roadmap.md -> payload.md` (committed, so the scope check passes) and a dangling `roadmap-context.md`. Each gets HTTP 400 with `<name> is a symlink (to <readlink>), not a regular file`, and HEAD, the index, the worktree status and every byte under the test's directory (the in-repo target included) are unchanged. `tests/test_pm_publish.py` is back to WIP's, so its link-out test `test_publish_refuses_generated_link_out` is unchanged.
- **A1, land helper.** `finish_land_deterministic._regenerate_generated_files` writes the digest with `safe_write.write`; `roadmap.md` already went through `reexport_roadmap_md`, which uses `safe_write`. `_reconcile_digest` (the post-merge amend) checks and writes through the rule too. The existing `refused_generated_files` pre-check stays, so both names are checked before either is written.
- **A2, finish reviews base.** `write_destinations` now names the untracked-summary copy as `(main checkout's project root, "work/reviews/<node>/<summary>")`, where the root is `reviews_root(root).parents[1]`, the same resolver `worktree_env.main_project_root` uses. As a result `irregular_destination` also walks `work` and `work/reviews`. `irregular_destination` is now `safe_write.refused(base, rel)`, with the same message shape, and its local `_KINDS` table and the `stat` import are gone. `pre_commit_paths` still computes the same relative path. `_keep_untracked_summary` copies with `safe_write.copy` from that project root.
- **A3, cache directory.** `history_cache.ensure_cache_dir` uses `safe_write.mkdirs(root, cache_dir)` with `root = cache_dir.parents[1]`. It checks `.gitignore` with `safe_write.check` (a link is refused, not read as present) and writes it with `safe_write.write`. `search_index` and `context_notice_cache` already catch `OSError` around this call, and `SafeWriteError` is an `OSError`, so they need no change.
- **A3, pickup hint.** `print_orchestration_hint` treats the marker as "already shown" only when `safe_write.check(...)` finds a regular file, which is an `lstat` walk, so any symlink on the path (live or dangling) is a refusal. It writes the marker with `safe_write.write`. A `SafeWriteError` prints one line on stderr, `warning: pickup hint marker not recorded: <refusal>`, and the hint is still printed. Pickup goes on as before. Only `SafeWriteError` is caught, so other `OSError`s behave as before.
- **A3, brainstorm lock.** `session_lock` opens the lock with `safe_write.open_lock` (and `os.fdopen(fd, "r+")`). It wraps both `ensure_cache_dir` and the open so that a `SafeWriteError` is re-raised as `BrainstormError(str(e))`. The callers are unchanged.
- **A4, docs.** `docs/dev-workflow.md` finish step 6 now says the copy goes to the main checkout's `work/reviews/`, and that a symlinked `work`, `work/reviews` or `work/reviews/<node>` refuses finish before any write. CHANGELOG `[Unreleased] Fixed` has a new entry.

## Fix round 1 (on `8f536135`, WIP merged)

`gpt-5.6-sol-high` blocked `078a39c3` with two findings. Both are fixed in `80558bae`:

- **A4 location.** A4 names one module, but the earlier split had put the Publish and finish rows in two other modules and left out the direct `resolve_deterministic_paths` rows. The class is an A4 entry point whose rows live somewhere other than `tests/test_ops_writers_refuse_links.py`. Now every A4 entry point has its test in that module, built only from public helpers: `tests.review_repo_helpers.commit_file`/`git`, `tests.test_finish_merge_mode.merge_mode_finish_repo`, the GUI app's `create_app` through `TestClient`, and `resolve_deterministic_paths`. `tests/test_pm_publish.py` and `tests/test_finish_config_preflight.py` are restored to WIP's, so this leaf no longer changes them and no row exists in two places.
- **`_tree`.** Its absent, symlink and file branches could never run, because every caller passes an existing directory. The class is a test helper with branches no caller reaches. It is now `_snapshot(d)`, a single dict comprehension: a file's bytes, or `None` for a directory, so a directory made through a link shows up too. The other helpers were checked for the same class (see Probes).

## Fix round 2 (on `4ae8b281`, WIP merged)

`gpt-5.6-sol-high` blocked `24f8f4ba` with two prose findings, both fixed in the commit after `4ae8b281`. The class is prose in this leaf's zones that still describes behaviour from before this leaf (a link was skipped, or failed silently) when the code now refuses it or warns.

- **`docs/dev-workflow.md` step 6.** It said a summary under a symlinked `work/` "is skipped with a warning". Finish writes under `work/` (`work/pr-body-<id>.md`, `work/done/`), so a symlinked `work/` is a write destination: preflight refuses it before the first write and names the path. The step now says so, and keeps "a symlinked summary is skipped with a warning", which is still true (the summary is a source, not a destination). A new `work-main` row in `test_finish_refuses_a_linked_reviews_base` pins the `work/` claim from the main checkout; the `work-from-worktree` row already covered a worktree.
- **`history_cache` module docstring.** It said "Every failure here is silent by design." It now says every failure costs a rebuild and never a failed command, and names the one exception that is not silent: `save_cache` warns once, naming the path, for a symlink on the cache path.

## Tests: one module, one test per entry point

All the tests are in `tests/test_ops_writers_refuse_links.py`:

- **Publish:** `test_publish_refuses_a_linked_generated_file` has two rows: `roadmap.md` linked in-repo and `roadmap-context.md` dangling.
- **`resolve_deterministic_paths` called directly:** `test_resolve_deterministic_paths_refuses_a_linked_roadmap_md` has two rows, a link in-repo and a link out. Each checks that `DeterministicResolveError` names the link, that no bytes under the test's directory changed, and that the link is unchanged. M21.37's `finish` writer row in `tests/test_writers_refuse_links_out.py` covers the same function from the outward-only angle. This row is the one A4 asks for here.
- **finish with an untracked summary:** `test_finish_refuses_a_linked_reviews_base` has five rows: `work/reviews` in the main checkout, `work/reviews` from a linked worktree, `work/reviews/M1.1`, `work` in the main checkout, and `work` from a linked worktree. Each checks exit 1, the refusal naming the link, `nothing was changed`, and no traceback. HEAD, the index and the status of both checkouts, the outside directory and the summary's bytes are all unchanged.
- **pickup hint:** `test_pickup_hint_refuses_a_linked_marker_path` has four rows.
- **brainstorm lock:** `test_brainstorm_add_idea_refuses_a_linked_lock`.
- **history cache (A6):** `test_digest_carries_on_past_a_linked_history_cache` has three rows: `.specyrd/cache` linked out, a dangling `.gitignore`, and `roadmap-history.json` linked to an outside file. Each checks exit 0, exactly one warning naming the link, the outside tree unchanged, and the link still a link.

## Probes

- Fix round 2, symlinked summary file under finish (a throwaway script on `merge_mode_finish_repo`): exit 0 with `[warn] work/implementation-summary-M1.1.md is a symlink or resolves outside the repo; not copying it`. So "skipped with a warning" is still true for the file.
- Fix round 2, symlinked `work/` in the checkout finish runs from (same script): exit 1 with `error: finish-this-task writes there, but <repo>/work is a symlink (to …), not a directory`. So the doc now says refused, and the `work-main` row pins it.
- Fix round 2, stale-prose audit of every docstring and comment in the seven package files that mentions symlinks, silence, skipping or outside paths (`grep -n "silent|skipped|resolves outside|outside the|symlink"`): only `history_cache`'s module docstring was stale. `ensure_cache_dir`, `save_cache`, `print_orchestration_hint`, `session_lock`, `write_destinations`, `irregular_destination`, `_regenerate_for_publish` and `_regenerate_generated_files` already describe the refusal.
- Fix round 2, `_keep_untracked_summary`'s warning text ("is a symlink or resolves outside the repo"): left unchanged. It is the pre-existing message. From finish, its "resolves outside" half is now refused earlier by preflight, which the docs say.
- Fix round 2, the CHANGELOG entry: it already says a symlinked `work`, `work/reviews` or `work/reviews/<node>` refuses finish before any write, and that a linked history cache warns. Not stale.
- Fix round 2, docs outside the zones (`grep` of `docs/` and `README.md` for `.specyrd/cache` with silent/warn/link, and for `work/reviews` with symlink/skipped): no other stale statement.
- Fix round 2, targeted suites (the seven listed below plus `test_finish_work_cleanup`): 120 passed. `ruff check specy_road tests scripts` is clean. `specy-road file-limits` is OK.
- Every A4 and A6 entry point (Publish, the direct resolve, finish's reviews base, pickup, brainstorm, digest's cache): each has its test in `tests/test_ops_writers_refuse_links.py`. `git diff origin/WIP/improvements-0-3-1 --stat -- tests` lists only that file.
- No `_`-prefixed name is imported from another module. Checked with grep on the file's imports: it imports only `DeterministicResolveError`, `resolve_deterministic_paths`, `print_orchestration_hint`, `DOGFOOD`, `REPO`, `script_subprocess_env`, `commit_file`, `git`, `merge_mode_finish_repo` and `create_app`.
- No row is duplicated: the two moved tests are gone from `tests/test_pm_publish.py` and `tests/test_finish_config_preflight.py`, which are byte-identical to WIP's.
- Helpers with unreachable branches: `_snapshot` has no branch beyond file versus directory, and both happen (`.specyrd` linked would get a `cache/` directory made through it). `_refusal`, `_cache_out`, `_specyrd_out`, `_history_file`, `_ignore_dangling`, `_git_state`, `_committed_dogfood` and `_cli` have no branches. `_marker` has one, and both of its targets are used by rows. Result: no other unreachable branch.
- Red-green: with the seven package files reverted to `origin/WIP/improvements-0-3-1`, 11 of the 16 rows fail: pickup ×4, brainstorm, digest ×3, and finish `reviews-main`, `reviews-from-worktree` and `work-from-worktree`. The other 5 pass because M21.37's rule already guards them, so they are regression pins: finish `node`, the 2 Publish rows and the 2 resolve rows.
- Targeted suites (`test_ops_writers_refuse_links`, `test_pm_publish`, `test_finish_config_preflight`, `test_history_cache`, `test_writers_refuse_links_out`, `test_pickup_orchestration_hint`, `test_finish_land_deterministic`): 106 passed.
- `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK.

## Touch zones (final)

These are as listed, with no additions. The callers outside the zones need no change: `search_index`, `context_notice_cache`, the brainstorm CLIs and the GUI routes all inherit the behaviour through `OSError` or `BrainstormError`. `tests/test_ops_writers_refuse_links.py` stays within the file-limits caps, and `specy-road file-limits` is OK.

## Verification

- `python -m pytest -q -n 6` (rework, on `56090bc9` plus `e79de2b3`): 6197 passed.
- Fix round 1: the targeted suites, 106 passed; `ruff check specy_road tests scripts` clean.
- `specy-road file-limits`: OK.

## Added

- `specy_road/finish_land_deterministic.py`: the `safe_write.write` digest write in `_regenerate_generated_files`, and `safe_write.check`/`write` in `_reconcile_digest`. A1: a caller that skips finish's preflight cannot write through a link.
- `specy_road/finish_bookkeeping_undo.py`: `summary` local in `write_destinations`, and the base changed to the main project root. A2: walk `work` and `work/reviews`.
- `specy_road/history_cache.py`: `root = cache_dir.parents[1]`, plus the `safe_write.check` guard on `.gitignore`. A3: a link is never read as present or written through.
- `specy_road/on_complete_pickup.py`: a `try/except SafeWriteError` printing one warning line. A3: best-effort marker.
- `specy_road/bundled_scripts/brainstorm_session.py`: a `try/except SafeWriteError` re-raising as `BrainstormError`. A3: callers report it with no traceback.
- `tests/test_ops_writers_refuse_links.py`: `_snapshot`, `_git_state`, `_committed_dogfood`, `_cli`, `_refusal`, `_cache_out`, `_specyrd_out`, `_marker`. These are the inspect and arrange helpers shared by the rows.
- `tests/test_ops_writers_refuse_links.py`: `test_publish_refuses_a_linked_generated_file`, 2 rows. A1/A4.
- `tests/test_ops_writers_refuse_links.py`: `test_resolve_deterministic_paths_refuses_a_linked_roadmap_md`, 2 rows. A1/A4.
- `tests/test_ops_writers_refuse_links.py`: `test_finish_refuses_a_linked_reviews_base`, 5 rows (`work-main` in fix round 2, with its arrange step that moves main's existing `work/` contents to the link's target). A2/A4: a distinct regression, since the reviews base was never walked.
- `tests/test_ops_writers_refuse_links.py`: `test_pickup_hint_refuses_a_linked_marker_path`, 4 rows. A3/A4.
- `tests/test_ops_writers_refuse_links.py`: `test_brainstorm_add_idea_refuses_a_linked_lock`. A3/A4.
- `specy_road/history_cache.py`: `save_cache` writes through `safe_write.write`, with an `except SafeWriteError` branch that prints one warning. A6: no write through a link, and a refused cache path is named.
- `tests/test_ops_writers_refuse_links.py`: `_history_file` and `_ignore_dangling` arrange helpers, and `test_digest_carries_on_past_a_linked_history_cache` with 3 rows. A6: the final-link and linked-folder rows.
- Mocks: none.
