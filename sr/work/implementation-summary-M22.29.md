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
- `specy_road/archive_ops.py`: `_move_planning_sheets` follows one rule (fix round 1). Each name is resolved once,
  as at the base commit, so in-repo links are followed as before: the sheet, its archived place, and the parent
  of an origin link. `_refuse_links_out` has already refused links out. The move then goes through
  `safe_write.move`'s descriptor walk from those resolved names, so a link that appears on them afterwards is
  refused, and so is a name that resolves outside the root (`_locate`). The dangling origin link is removed with
  `safe_write.remove`.
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

## Probes

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
- `finish` (chmod or copystat on the temp file) still gets the temp file's **path**, because
  `tests/test_setup_writers_refuse_links.py::test_an_ignore_file_linked_right_before_replace_is_an_error`
  (outside the zones) reads `Path(tmp).parent` in its `os.chmod` wrapper. If `finish` fails because of a swap,
  `_recheck` runs first so the error is the rule's refusal.
- `remove`, `prune_empty` and `open_lock` are unchanged: neither the acceptance criterion nor the plan names them.
- Net line change against base: package +134/-38, tests +150/-6, above A2's informational estimate. Most of the
  difference is the Windows fallback kept beside the descriptor path in `_replace` and `move`.
- Touch zones are confirmed as listed; no file outside them changed. Merged `origin/WIP/improvements-0-3-1`
  first, with no conflicts.

## Verification

- `python -m pytest -q -n 4` (full suite, after the merge and fix): 6287 passed.
- Targeted: `tests/test_safe_write.py`, `tests/test_archive_ops.py`, the archive suites,
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
- `_replace` `except OSError` around `finish`: turns a chmod or copystat failure caused by a swap into the rule's refusal.
- `mkdirs` descriptor branch: directories are created through the walk, not by path.
- `safe_write.move` (public): the archive sheet move under the rule, by descriptor with the M21.37 fallback.
- `archive_ops`: names resolved once (sheet, stored, origin link's parent), then moved and removed by `safe_write`; this keeps the base's in-repo link behaviour.
- Test `test_a_link_swapped_in_right_before_replace_is_refused`, parametrized `dir_fd` (descriptors / no-dir-fd): the no-dir-fd id checks that M21.37's re-check still refuses.
- Test helper `swap_at_open` (wraps public `os.open`, adds itself to `os.supports_dir_fd`; swaps right after an open, or right before one with `before=True`): the racer.
- Test `test_a_link_swapped_in_after_the_walk_is_refused` (generated file, managed block, nested file x destination/parent): the plan's first three table rows.
- Test `test_a_root_swapped_for_a_link_before_it_is_opened_is_refused` (`write`, `mkdirs`): review finding 1.
- Test `test_a_directory_swapped_for_a_link_before_a_sheet_moves_is_refused` (sheet parent / archive planning dir): the plan's archive row.
- Test `test_planning_sheets_move_out_of_the_flat_planning_dir`, parametrized `in-repo-link`, `link-chain`, `linked-dir`: in-repo linked sheets still move their final target (review finding 2).
- Test helper `_link_sheet` (module-local): builds the three linked-sheet shapes.
