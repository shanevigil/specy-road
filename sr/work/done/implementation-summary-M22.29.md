# Implementation summary: M22.29 (safe-write-directory-descriptors)

## What changed

- `specy_road/safe_write.py`: where the platform has directory descriptors, `write`, `copy`, `mkdirs` and the new
  `move` walk with `_held`. `_held` opens the resolved root by its path, then each directory below it relative to
  the one above. Every open, **the root's included** (fix round 1), uses `O_RDONLY | O_DIRECTORY | O_NOFOLLOW`. A
  missing directory below the root is created first with `os.mkdir(name, dir_fd=parent)`. A link or
  non-directory that fails the open is refused with M21.37's sentence. The temp file is created with
  `O_CREAT | O_EXCL | O_NOFOLLOW` in the held parent. Right before `os.replace(..., src_dir_fd, dst_dir_fd)`,
  `_recheck(full, held)` compares each held descriptor's identity (`fstat`) with an `lstat` of its path, the root
  included, and `lstat`s the final name relative to the parent. A swap is refused, and the temp file is unlinked
  through the parent descriptor. Where `os.supports_dir_fd` lacks `os.open`, `os.rename`, `os.stat`, `os.mkdir`
  or `os.unlink`, or `O_DIRECTORY`/`O_NOFOLLOW` are missing (Windows), the M21.37 code path runs unchanged.
- `specy_road/archive_ops.py` and `safe_write.moving` (fix round 2): `apply_archive` walks to every planning sheet
  and its archived place **before its first change**, using `safe_write.moving(root, origin, stored)` in an
  `ExitStack`, and renames through the held directories only after the chunk edits. `moving` follows one bounded
  rule. A link below the root on either path, the sheet's own included, is followed during the descriptor walk
  itself: its target is read with `os.readlink(name, dir_fd=<held dir>)` and spelled lexically from there. A `..`
  may not climb above the root, at most `MAX_LINKS` (40) links are followed per step, and a link out of the root
  is refused (`<link> is a symlink (to X), not a link to a path under <root>`). No `resolve()` runs before the
  walk. The walk ends with the identity re-check, so a swap during it is refused before the roadmap changes; the
  rename re-checks again. When the origin is a link, the rename unlinks that entry through its held parent. The
  public `move` from rounds 0 and 1 is replaced by `moving`. Without `dir_fd` (Windows), `moving` resolves names
  when it renames and applies M21.37's re-check. Destination directories (`roadmap/archive/planning/<id>/`) are
  made during the walk, so a refusal can leave that empty directory behind.
- CHANGELOG `[Unreleased]` Fixed: one **Security** entry, updated to the rule above.

## Fix round 1 (review `gpt-5.6-sol-high` at `0969d830`)

- **Finding 1, root opened by following a link.** The class is any open or create in the descriptor path that
  follows a link at its final component. Fix: the root is no longer opened separately. It is the first step of
  the same walk, with the same `O_NOFOLLOW` open and the same refusal, so no step of the walk can follow a link.
  Tests: `test_a_root_swapped_for_a_link_before_it_is_opened_is_refused[write|mkdirs]` (a public `write` into a
  new subdirectory, and `mkdirs`). Both are refused, and nothing appears outside or in the real root.
- **Finding 2, linked-sheet regression.** The class is in-repo links on any archive name (source, destination,
  origin link). Fix: one rule resolves every name once, then moves by descriptor; no per-shape branch was added.
  The `os.readlink` join from round 0 is gone. Tests: `test_planning_sheets_move_out_of_the_flat_planning_dir`
  parametrized `link-chain` and `linked-dir`, through public `archive_node`.

## Fix round 2 (review `gpt-5.6-sol-high` at `84a5a37b`)

- **Finding 1, archive operands resolved before the walk.** The class is any name on an archive move path that
  was resolved or followed by path outside the descriptor walk: source, destination, the origin link, and that
  link's parent. Fix: one rule in `safe_write.moving`, described above. Following links is now part of the walk,
  so no operand is resolved beforehand, and the origin link is unlinked through its held parent.
- **Finding 2, refusal before any archive mutation.** Fix: the sheets are walked and checked before the archive
  chunk is written. Test: `test_a_directory_swapped_for_a_link_before_a_sheet_moves_is_refused` now covers five
  cases: sheet parent, archive directory, linked sheet's parent, linked target's parent, and the linked sheet's
  parent swapped after the target directory opens (the reviewer's timing). Each asserts the roadmap is
  byte-identical, no archive chunk exists, outside is unchanged, and the sheet and its link remain. All five fail
  at `84a5a37b`.
- **Findings 3 and 4 (round 2):** at that time blocked outside the touch zones; resolved in round 3, below.

## Fix round 3 (review `gpt-5.6-sol-high` at `a91a11b6`)

- **Findings 1 to 3, `write`/`copy` metadata set by the temp file's path.** The class is any mode or times call
  on the temp file that names it through the parent directory's path, which a swap after the walk redirects.
  Fix: one rule in `_replace`. `finish` (chmod for `write`, `shutil.copystat` for `copy`) gets
  `_anchored(parent_fd, name, fd)`: `/proc/self/fd/<held parent>/<temp name>` where `/proc` exists (Linux), so
  the path resolves through the held directory descriptor and not the directory's path, and otherwise the temp
  file's own descriptor. It runs while the temp file is still open and flushed, so closing it does not move the
  times. This form also keeps the out-of-zone `tests/test_setup_writers_refuse_links.py` racer working, so no
  file outside the zones changes: it receives a path whose parent is the held directory. The round-0
  `except OSError` re-check around `finish` was only reachable through the path form and is removed.
- **Test:** `test_a_parent_swapped_after_the_temp_file_leaves_outside_metadata_alone[write|copy]`. Right after
  the temp file is created, a racer swaps the parent for a link out and plants a mode-`0666` file named like the
  temp file there. Each case is refused, the planted file's mode, times and bytes are unchanged, and the real
  directory has no temp file left. Both fail at `a91a11b6`.

## Fix round 4 (review `gpt-5.6-sol-high` at `4591a171`)

- **Finding: the root was resolved twice in one operation.** The class is any operation that resolves the root
  again after its first resolution: a root swapped for a link out between the two resolutions resolves to the
  outside directory, a real directory, so the `O_NOFOLLOW` walk would accept it. Instances found:
  - `_replace`: `check()` resolved the root, then `_locate(root, full)` resolved it again. This is the
    reviewer's `write`/`copy` instance.
  - `moving`: resolved again for `dst`.
  - `_relinked`: resolved again for every followed link.
  - `prune_empty`: re-resolved its base on every step.
  - The no-`dir_fd` fallbacks of `_replace` and `moving`: `mkdirs`/`check` resolved again.

  Fix, one rule: `_locate` takes `base`, the operation's own resolution of the root, and resolves only when it
  is not given. Each public operation resolves once and passes `base` down: `_walk` gains `base`, and
  `_make_dirs` is `mkdirs` under a given base. A swap after that resolution is met by the walk's `O_NOFOLLOW`
  open of the root and refused.
- **Test:** `test_a_root_swapped_for_a_link_before_it_is_opened_is_refused` is parametrized over `write`,
  `copy` and `mkdirs`, and over the swap timing: `before-open`, or `after-resolve` (a wrapper on public
  `Path.resolve` swaps the root right after its first resolution). It expects `SafeWriteError` naming the root,
  and nothing outside or in the real root. `write-after-resolve` and `copy-after-resolve` fail at `4591a171`.

## Fix round 5 (review `gpt-5.6-sol-high` at `b718e379`)

- **Finding: a skip decided by path before the held walk.** `_hold_planning_sheets` filtered sheets with
  `(root / origin).is_file()`. Swapping `planning` for a link out to a directory without the sheet made that
  check read the sheet as gone, so the archive skipped it. The roadmap then changed and the sheet was left
  behind; validation raised later. The class is any decision that lets an archive operand bypass the walk,
  made from a path outside the held walk.
- **Fix, one bounded rule** (in `safe_write.moving`'s docstring): only the held walk decides that `src` is
  absent. `moving` yields `None` when a directory or the file on `src`'s way is missing (links followed as in
  the walk), and otherwise yields the rename. The archive walks every sheet and keeps only the non-`None`
  results; the `is_file()` pre-filter is gone. A skipped sheet makes no destination directories, because the
  destination is walked only for a present source. Without `dir_fd` (Windows), the decision is by path, as in
  M21.37's path model.
- **Test:** `test_a_sheet_is_skipped_only_when_the_held_walk_finds_it_gone`, cases `gone` and
  `swapped-before-the-walk`. In the swap case, a wrapper on public `Path.resolve` swaps `planning` for a link
  to an empty outside directory right after the archive's link pre-check resolves the sheet, before any walk.
  The archive is refused naming `planning`, the roadmap is byte-identical, no chunk exists, and outside stays
  empty. In the `gone` case the sheet is really missing: it is skipped and the archive succeeds. The swap case
  fails at `b718e379` (the sheet is skipped, the roadmap changes, then validation raises); `gone` passes on
  both.

## Probes

- Round 5: one swap of `planning` to a link out, right after the pre-check and before the walk: refused before any roadmap change (test).
- Round 5: a sheet that is really missing: skipped and the archive succeeds (test); a dangling in-repo link or a missing directory on the way reads as absent through the held walk (`FileNotFoundError` from `_held`/`readlink`).
- Round 5: other path-based decisions in the archive flow: `_refuse_links_out` (resolve) can only refuse, never skip, and a swap after it meets the walk; the chunk path's `resolve()` only names the record (`write_json_chunk` is outside the zones); `origin != source` and `_hold_file`'s link test use held descriptors.
- Round 5: other path-based decisions in `safe_write.py`: `_replace`'s pre-check (`_walk`) only refuses; `remove`'s "absent by path" is M21.37's path model (out of scope); the no-`dir_fd` fallback is by path (documented).
- Round 5, limit: `planning` swapped for an in-repo link to a directory without the sheet is followed, as in-repo links are by the rule, so the sheet reads as gone and is skipped. Only someone who can already write inside the repository can do this.
- Round 5: full suite 6416 passed after the merge.

- Round 4: `write`, `copy` and `mkdirs` with the root swapped right after its first resolution, and right before it is opened: refused, nothing outside (test; `mkdirs` already resolved once and passed before too).
- Round 4: `moving` (archive) with the root swapped right after its first resolution, for a plain sheet and an in-repo linked sheet: refused naming the root; the sheet, its link and the outside file are unchanged (inline probe).
- Round 4: remaining `resolve()` calls in `safe_write.py`: one per public entry (`_locate` without `base`, `mkdirs`), and the no-`dir_fd` fallback `_move_by_path`, which resolves names by design (M21.37's path model, Windows only). `remove` and `open_lock` resolve once each; `open_lock`'s second `check` only names a refusal after a failed open.
- Round 4: full suite 6365 passed after the merge.

- Round 3: the race above on Linux (`/proc` branch): refused, outside mode, times and bytes unchanged, no temp left (test).
- Round 3: the same race with `/proc/self/fd` hidden (the descriptor branch): `write` and `copy` refused, outside metadata unchanged, no temp left (inline probe).
- Round 3: descriptor branch without a race: `copy` keeps the source's mode `0640` and mtime, and `write(mode=0o604)` sets `0604` (inline probe).
- Round 3: every mutating call in `safe_write.py` (grep of chmod, utime, unlink, rename, replace, mkdir, rmdir, open): in the descriptor path all go through a held descriptor. The only path-based ones are the root's own `mkdir(parents=True)` (the root is resolved once by design), the no-`dir_fd` fallback (M21.37), and `remove`, `prune_empty` and `open_lock` (unchanged, out of scope).
- Round 3: `moving` (archive) sets no metadata, so this class does not reach it.
- Round 3: `tests/test_setup_writers_refuse_links.py`'s `os.chmod` racer still swaps the destination through the held directory and is refused (5 cases pass); the full suite passes.

- Round 2: linked sheet whose link loops (`a.md -> b.md -> a.md`): refused before any change (by `_refuse_links_out`'s resolve, as at base); no chunk written.
- Round 2: sheet linked out of the repository: refused before any change by `_refuse_links_out`; the outside file is kept.
- Round 2: archive then restore with a link chain: the origin comes back as a regular file with the original bytes.
- Round 2: no-`dir_fd` fallback (`os.supports_dir_fd` without `os.open`/`os.rename`) with a sheet linked through a linked directory: the final target moves, and the origin link and target are gone.
- Round 2: shapes `sheet`, `in-repo-link`, `link-chain`, `linked-dir` through `archive_node`: all still pass (descriptor-following walk, no `resolve()`).
- Round 2: an absolute link target spelled through a non-resolved alias of the root (e.g. macOS `/tmp` vs `/private/tmp`) is refused as out of the root, because `_locate` anchors on the resolved root during the walk. This is a documented limit of the bounded rule; there is no test.
- Round 2: the metadata class (`finish` by temp path) is still open: see findings 3 and 4 above. The window only opens after a directory swap; one swap leaves the random temp name absent outside (ENOENT, re-checked into a refusal). It needs a matching entry planted outside, which the reviewer did.

- Root swapped right before it is opened, `write` into a new subdirectory and `mkdirs`: both refused, nothing outside (tests above; with round-0 package files both fail).
- Root swapped right before it is opened for a **dangling** link: `write` and `mkdirs` refused, nothing created outside (inline probe).
- Root that is already a dangling link when the call starts: followed, which is the base behaviour (the root is resolved once and nothing above it is inspected, M21.37). This is not the race, so it is unchanged.
- Root swapped before `base.mkdir(parents=True, exist_ok=True)`: `mkdir` never creates through an existing link (`FileExistsError`, or `exist_ok` on the linked directory), so nothing is created outside, and the next open refuses.
- A directory below the root, the temp file, `os.mkdir(..., dir_fd)`, `os.replace` and `_old_mode`: none follows a final link (`O_NOFOLLOW`, `O_EXCL`, `mkdir` and `rename` semantics, `follow_symlinks=False`); covered by `test_a_link_swapped_in_after_the_walk_is_refused` (6 cases).
- `finish` (chmod or copystat by temp path) after a swap: fails with ENOENT on the random name, re-checked into the rule's refusal; covered by `tests/test_setup_writers_refuse_links.py` and the chmod-racer test.
- `move` source and destination: both walk through `_held`, so the root fix covers both; archive tests (sheet parent and archive dir swapped after open) are refused, outside unchanged, the sheet stays put.
- Archive with an in-repo linked `roadmap/archive` directory: archives, sheet stored as a regular file (inline probe, as at base).
- Archive then restore of an in-repo linked sheet: the round trip works; the sheet is restored as a regular file at its origin (inline probe; restore is outside this leaf).
- Archive shapes `sheet`, `in-repo-link`, `link-chain`, `linked-dir`: all move the final target and remove the origin link; `link-chain` and `linked-dir` fail with round-0 package files.
- Fallback path (no `dir_fd`): unchanged by this round; `test_a_link_swapped_in_right_before_replace_is_refused[no-dir-fd]` passes.

## Notes for reviewers

- `os.supports_dir_fd` never lists `os.replace`, only `os.rename`; both use `renameat`. The availability check
  therefore tests `os.rename`.
- `finish` gets the temp file through the held directory (`/proc/self/fd/...`), or its own descriptor where
  there is no `/proc`; see Fix round 3. On macOS `/proc` is absent, so the descriptor form is used; that branch
  was probed on Linux by hiding `/proc`.
- `remove`, `prune_empty` and `open_lock` are unchanged: neither the acceptance criterion nor the plan names them.
- Net line change against base: package +260/-66, tests +266/-6, above A2's informational estimate. Most of the
  difference is the Windows fallback kept beside the descriptor path in `_replace` and `move`.
- Touch zones: no file outside them changed (rounds 3 and 4; round 3 removed the need to add
  `tests/test_setup_writers_refuse_links.py`). Merged `origin/WIP/improvements-0-3-1` first in each round, with no conflicts.

## Verification

- `python -m pytest -q -n 4` (full suite, round 5, after the merge and fix): 6416 passed (round 4: 6365).
- Round 3 targeted (408 passed): the round-2 list plus `tests/test_init_project.py`.
- Round 2 targeted (403 passed): the list below plus `tests/test_history_cache.py`, `tests/test_generate_brief.py`, `tests/test_digest.py`.
- Round 1 targeted: `tests/test_safe_write.py`, `tests/test_archive_ops.py`, the archive suites,
  `tests/test_setup_writers_refuse_links.py`, `tests/test_writers_refuse_links_out.py` and
  `tests/test_ops_writers_refuse_links.py`: 333 passed.
- `ruff check specy_road tests scripts`, `specy-road file-limits`, `scripts/check_test_private_imports.py`: pass.
- Red-green: with the package files at base, the 8 swap tests fail. With the package files at `0969d830`, the
  4 new fix-round tests fail.

## Added

- `safe_write._dir_fds`: whether to use the descriptor path; it is read at call time so a test can drop the support set.
- `safe_write._held`: the descriptor walk; every step, the root included, opens with `O_NOFOLLOW` (optional create below the root); it keeps every directory open until the write is done.
- `_held` branch, open failure on an absent or real directory: re-raise the original error, so a swap that comes back is not mislabelled as a refusal.
- `_held` branch, open failure on anything else: the rule's refusal, naming the swapped component (the root included).
- `safe_write._old_mode`: an existing file's mode read through the held parent.
- `_recheck` `held` parameter and identity guard (`samestat` of `lstat(path)` and `fstat(fd)`): detects a directory swapped after the walk.
- `_temp` `dir_fd` parameter and `O_NOFOLLOW`: the temp file is created in the held parent.
- `_replace` descriptor branch: writes and replaces through the held parent; the old path-based branch is kept for no-`dir_fd` platforms.
- `safe_write._anchored`: the temp file as `finish` names it, through the held directory (`/proc/self/fd`) or its own descriptor (round 3; replaces the removed `except OSError` re-check around `finish`).
- `mkdirs` descriptor branch: directories are created through the walk, not by path.
- `safe_write.moving` (public context manager): walks to an archive move's source and destination now, following in-root links through held descriptors, and yields the rename; the M21.37 fallback without `dir_fd`.
- `safe_write.MAX_LINKS`: the bound on links followed per step.
- `safe_write._open_dir`: one directory open (`O_NOFOLLOW`, optional create), shared by every walk; it returns the refusing kind so a caller can follow.
- `_held` `follow` parameter: a link below the root is re-walked from the root through `_relinked`; without it, a link is refused as before.
- `safe_write._relinked`: a link's target read through its held directory, spelled lexically from there; a target out of the root is refused naming the link.
- `safe_write._close`: closes the held descriptors when the walk restarts or ends.
- `safe_write._hold_file`: holds a file's parent, following its own link too (the source and destination of `moving`).
- `safe_write._move_by_path`: `moving`'s no-`dir_fd` rename (names resolved, M21.37 re-check, origin link removed).
- `_recheck` `expected` parameter: the origin link entry is re-checked as a regular file or a symlink.
- `archive_ops._hold_planning_sheets`: walks every sheet before the first change; replaces `_move_planning_sheets`.
- Test `test_a_link_swapped_in_right_before_replace_is_refused`, parametrized `dir_fd` (descriptors / no-dir-fd): the no-dir-fd id checks that M21.37's re-check still refuses.
- Test helper `swap_at_open` (wraps public `os.open`, adds itself to `os.supports_dir_fd`; swaps right after an open, or right before one with `before=True`): the racer.
- Test `test_a_link_swapped_in_after_the_walk_is_refused` (generated file, managed block, nested file x destination/parent): the plan's first three table rows.
- Test `test_a_root_swapped_for_a_link_before_it_is_opened_is_refused` (`write`, `mkdirs`): review finding 1.
- Test `test_a_directory_swapped_for_a_link_before_a_sheet_moves_is_refused` (5 cases, including the linked-sheet shapes and the reviewer's timing): the plan's archive row plus round-2 finding 2, asserting no roadmap change.
- Test helper `_roadmap` (module-local): the roadmap part of the snapshot, for the "before any mutation" assertion.
- Test `test_planning_sheets_move_out_of_the_flat_planning_dir`, parametrized `in-repo-link`, `link-chain`, `linked-dir`: in-repo linked sheets still move their final target (review finding 2).
- Test helper `_link_sheet` (module-local): builds the three linked-sheet shapes.
- Test `test_a_parent_swapped_after_the_temp_file_leaves_outside_metadata_alone` (`write`, `copy`): round-3 findings; a racer plants an outside file named like the temp file and checks its metadata is kept.
- `_locate` / `_walk` `base` parameter and `safe_write._make_dirs`: the root is resolved once per operation and passed down (round 4).
- Test `test_a_root_swapped_for_a_link_before_it_is_opened_is_refused` parametrized `copy` and `after-resolve`, with helper `_swap_after_resolve` (module-local; wraps public `Path.resolve`): round-4 finding.
- `moving` yields `None` when the held walk proves `src` absent (`except FileNotFoundError` plus the final-kind check); `_hold_planning_sheets` drops those instead of a path pre-filter (round 5).
- Test `test_a_sheet_is_skipped_only_when_the_held_walk_finds_it_gone` (`gone`, `swapped-before-the-walk`): round-5 finding.
