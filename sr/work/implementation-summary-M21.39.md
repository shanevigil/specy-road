# Implementation summary: M21.39 — Publish, finish's land and reviews copy, the pickup hint refuse any symlink on the path

Branch `feature/rm-ops-writers-refuse-links`, base `1be0ac40`. As the planning sheet asks, this is built ahead of M21.37: `feature/rm-safe-write-rule-setup-writers` is merged in (`e10c4597`), and only `safe_write`'s public API is used. Implementation commits: `22473dfe`, plus a one-line test-file spacing fix. M21.37's files are not edited. The review diff includes M21.37's files until that leaf lands on WIP; that is expected.

## What changed

- **A1, Publish.** No code change. After M21.37, `refused_generated_files` refuses any link, so `_regenerate_for_publish` already raises with finish's sentence before anything is written. Only its docstring changed. `tests/test_pm_publish.py::test_publish_refuses_a_linked_generated_file` (was `test_publish_refuses_generated_link_out`, now parametrized) pins three cases: an in-repo `roadmap.md -> payload.md` (committed, so the scope check passes), a dangling `roadmap-context.md`, and a `roadmap-context.md` linked out. Each gets HTTP 400 with `<name> is a symlink (to <readlink>), not a regular file`. HEAD, the index, both files' bytes, the link and its target (bytes, or absence) are all unchanged.
- **A1, land helper.** `finish_land_deterministic._regenerate_generated_files` writes the digest with `safe_write.write`; `roadmap.md` already went through `reexport_roadmap_md`, which uses `safe_write`. `_reconcile_digest` (the post-merge amend) checks and writes through the rule too. The existing `refused_generated_files` pre-check stays, so both names are checked before either is written.
- **A2, finish reviews base.** `write_destinations` now names the untracked-summary copy as `(main checkout's project root, "work/reviews/<node>/<summary>")`, where the root is `reviews_root(root).parents[1]`, the same resolver `worktree_env.main_project_root` uses. As a result `irregular_destination` also walks `work` and `work/reviews`. `irregular_destination` is now `safe_write.refused(base, rel)`, with the same message shape, and its local `_KINDS` table and the `stat` import are gone. `pre_commit_paths` still computes the same relative path. `_keep_untracked_summary` copies with `safe_write.copy` from that project root.
- **A3, cache directory.** `history_cache.ensure_cache_dir` uses `safe_write.mkdirs(root, cache_dir)` with `root = cache_dir.parents[1]`. It checks `.gitignore` with `safe_write.check` (a link is refused, not read as present) and writes it with `safe_write.write`. `search_index` and `context_notice_cache` already catch `OSError` around this call, and `SafeWriteError` is an `OSError`, so they need no change.
- **A3, pickup hint.** `print_orchestration_hint` treats the marker as "already shown" only when `safe_write.check(...)` finds a regular file, which is an `lstat` walk, so any symlink on the path (live or dangling) is a refusal. It writes the marker with `safe_write.write`. A `SafeWriteError` prints one line on stderr, `warning: pickup hint marker not recorded: <refusal>`, and the hint is still printed. Pickup goes on as before. Only `SafeWriteError` is caught, so other `OSError`s behave as before.
- **A3, brainstorm lock.** `session_lock` opens the lock with `safe_write.open_lock` (and `os.fdopen(fd, "r+")`). It wraps both `ensure_cache_dir` and the open so that a `SafeWriteError` is re-raised as `BrainstormError(str(e))`. The callers are unchanged.
- **A4, docs.** `docs/dev-workflow.md` finish step 6 now says the copy goes to the main checkout's `work/reviews/`, and that a symlinked `work`, `work/reviews` or `work/reviews/<node>` refuses finish before any write. CHANGELOG `[Unreleased] Fixed` has a new entry.

## Where the A4 rows live (deviation from "tests/test_ops_writers_refuse_links.py rows per entry point")

The test rules forbid importing `_`-prefixed names, and they say to extend an existing test before adding one. So the rows are split by where their helpers already live:

- **Publish:** `tests/test_pm_publish.py::test_publish_refuses_a_linked_generated_file`. This extends the existing link-out test and uses that file's `dogfood_repo`, `_post_publish` and `_state`.
- **finish with an untracked summary:** `tests/test_finish_config_preflight.py::test_finish_refuses_a_linked_reviews_base`. It uses that file's `_repo`, `_run` and `_state`, and has four rows:
  - `work/reviews` linked out in the main checkout;
  - the same link, with finish run from a linked worktree;
  - `work/reviews/M1.1` linked;
  - the main checkout's `work` linked, with finish run from a linked worktree.

  Each row checks exit 1, the refusal naming the link, `nothing was changed`, no traceback, the worktree, index and HEAD of both checkouts unchanged, and the outside directory's contents unchanged.
- **`resolve_deterministic_paths` called directly:** not duplicated. The `finish` writer row of `tests/test_writers_refuse_links_out.py::test_writer_refuses_a_link_out_of_its_root` (outside the zones; from M21.37) already calls it directly with `link_in` and `link_out`, among other layouts, and checks that the exception names the refusal and that the target bytes are unchanged.
- **pickup and brainstorm:** `tests/test_ops_writers_refuse_links.py` (new).

## Red-green

With the seven package files reverted to the merged base and the tests kept, these fail:

- `test_pickup_hint_refuses_a_linked_marker_path`: all four rows;
- `test_brainstorm_add_idea_refuses_a_linked_lock`;
- `test_finish_refuses_a_linked_reviews_base`: the `reviews-main`, `reviews-from-worktree` and `work-from-worktree` rows.

That is 8 in all. They pass with the fix. The `node` row and the three Publish rows already passed on the merged base, through the old reviews-root walk and M21.37's `refused_generated_files`, so they pin existing behaviour.

## Touch zones (final)

These are as listed, with no additions. The callers outside the zones need no change: `search_index`, `context_notice_cache`, the brainstorm CLIs and the GUI routes all inherit the behaviour through `OSError` or `BrainstormError`. `tests/test_ops_writers_refuse_links.py` and `tests/test_finish_config_preflight.py` stay within the file-limits caps, and `specy-road file-limits` is OK.

## Verification

- `python -m pytest -q -n 4`: 6047 passed.
- `specy-road file-limits`: OK.
- `python -m ruff check specy_road tests/test_ops_writers_refuse_links.py tests/test_finish_config_preflight.py tests/test_pm_publish.py`: clean.

## Added

- `specy_road/finish_land_deterministic.py`: the `safe_write.write` digest write in `_regenerate_generated_files`, and `safe_write.check`/`write` in `_reconcile_digest`. A1: a caller that skips finish's preflight cannot write through a link.
- `specy_road/finish_bookkeeping_undo.py`: `summary` local in `write_destinations`, and the base changed to the main project root. A2: walk `work` and `work/reviews`.
- `specy_road/history_cache.py`: `root = cache_dir.parents[1]`, plus the `safe_write.check` guard on `.gitignore`. A3: a link is never read as present or written through.
- `specy_road/on_complete_pickup.py`: a `try/except SafeWriteError` printing one warning line. A3: best-effort marker.
- `specy_road/bundled_scripts/brainstorm_session.py`: a `try/except SafeWriteError` re-raising as `BrainstormError`. A3: callers report it with no traceback.
- `tests/test_pm_publish.py`: `test_publish_refuses_a_linked_generated_file`, a parametrization of the existing link-out test with the in-repo and dangling rows. A1/A4.
- `tests/test_finish_config_preflight.py`: `_entries`, a directory-contents helper, so the outside directory can be compared without following links. A4.
- `tests/test_finish_config_preflight.py`: `test_finish_refuses_a_linked_reviews_base`, 4 rows. A2/A4: a distinct regression (the reviews base was never walked).
- `tests/test_ops_writers_refuse_links.py`: `_tree`, `_refusal`, `_cache_out`, `_specyrd_out`, `_marker`. These are the arrange and inspect helpers for the rows.
- `tests/test_ops_writers_refuse_links.py`: `test_pickup_hint_refuses_a_linked_marker_path`, 4 rows. A3/A4.
- `tests/test_ops_writers_refuse_links.py`: `test_brainstorm_add_idea_refuses_a_linked_lock`. A3/A4.
- Mocks: none.
