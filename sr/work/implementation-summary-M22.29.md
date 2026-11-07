# Implementation summary: M22.29 (safe-write-directory-descriptors)

## What changed

- `specy_road/safe_write.py`: where the platform has directory descriptors, `write`, `copy`, `mkdirs` and the new
  `move` open the resolved root once and each directory below it with `O_RDONLY | O_DIRECTORY | O_NOFOLLOW`
  relative to the one above (`_held`). A missing directory is created first with `os.mkdir(name, dir_fd=parent)`.
  A link or non-directory that fails the open is refused with M21.37's sentence. The temp file is created with
  `O_CREAT | O_EXCL | O_NOFOLLOW` in the held parent. Right before `os.replace(..., src_dir_fd, dst_dir_fd)`,
  `_recheck(full, held)` compares each held descriptor's identity (`fstat`) with an `lstat` of its path, the
  root included, and `lstat`s the final name relative to the parent. A swap is refused, and the temp file is
  unlinked through the parent descriptor. Where `os.supports_dir_fd` lacks `os.open`, `os.rename`, `os.stat`,
  `os.mkdir` or `os.unlink`, or `O_DIRECTORY`/`O_NOFOLLOW` are missing (Windows), the M21.37 code path runs
  unchanged.
- `specy_road/archive_ops.py`: `_move_planning_sheets` no longer calls `resolve()`. The sheet is moved with
  `safe_write.move(root, src, root / stored)`, where `src` is the origin as spelled, or for an in-repo linked
  sheet the link's target read once with `os.readlink` and joined lexically. The dangling origin link is then
  removed with `safe_write.remove`. `_refuse_links_out`, the pre-check, is unchanged.
- CHANGELOG `[Unreleased]` Fixed: one **Security** entry.

## Notes for reviewers

- **Finding:** `os.supports_dir_fd` never lists `os.replace`, only `os.rename`; both use `renameat`. The
  availability check therefore tests `os.rename`. The plan's wording ("lacks `os.open` or `os.replace`") cannot
  be taken literally, because then the descriptor path would never run.
- `finish` (chmod or copystat on the temp file) still gets the temp file's **path**, as before.
  `tests/test_setup_writers_refuse_links.py::test_an_ignore_file_linked_right_before_replace_is_an_error`
  (outside the zones) wraps `os.chmod` and reads `Path(tmp).parent`. Passing the descriptor broke it, so the
  change was reverted. If `finish` fails because a directory was swapped under the temp path, `_recheck` runs
  first so the error is the rule's refusal. One swap cannot make that chmod reach an outside file: the temp
  file's random name does not exist outside.
- Linked-sheet behaviour: a direct in-repo link (`planning/x.md -> ../docs/x.md`) moves its target and the link
  is removed, as before. Two edge cases now differ. A sheet whose link target is itself a link, or that passes
  through a linked directory, used to be followed by `resolve()` and is now refused by the rule (no direct test).
- `remove`, `prune_empty` and `open_lock` are unchanged: neither the acceptance criterion nor the plan names them.
- The net line change is larger than A2's informational estimate: package +133/-39, tests +116/-6. Most of the
  difference is the Windows fallback kept beside the descriptor path in `_replace` and `move`.
- Touch zones are confirmed as listed; no file outside them changed. The test-only helper `swap_after_open` is
  defined in `tests/test_safe_write.py` and imported by `tests/test_archive_ops.py`.

## Verification

- `python -m pytest -q -n 4` (full suite): 6205 passed.
- `ruff check specy_road tests scripts`, `specy-road file-limits`, `scripts/check_test_private_imports.py`,
  `scripts/check_clones.py`: all pass.
- Red-green: with `specy_road/safe_write.py` and `specy_road/archive_ops.py` at the base commit, the new
  swap tests fail (8 failed: `test_a_link_swapped_in_after_the_walk_is_refused` x6,
  `test_a_directory_swapped_for_a_link_before_a_sheet_moves_is_refused` x2).

## Added

- `safe_write._dir_fds`: whether to use the descriptor path; it is read at call time so a test can drop the support set.
- `safe_write._held`: the descriptor walk (`O_NOFOLLOW` per component, optional create); it keeps every directory open until the write is done.
- `_held` branch, open failure on an absent or real directory: re-raise the original error, so a swap that comes back is not mislabelled as a refusal.
- `_held` branch, open failure on anything else: the rule's refusal, naming the swapped component.
- `safe_write._old_mode`: an existing file's mode read through the held parent, so a rewrite does not read the mode through a swapped path.
- `_recheck` `held` parameter and identity guard (`samestat` of `lstat(path)` and `fstat(fd)`): detects a directory swapped after the walk.
- `_temp` `dir_fd` parameter and `O_NOFOLLOW`: the temp file is created in the held parent.
- `_replace` descriptor branch: writes and replaces through the held parent and cleans up through it; the old path-based branch is kept for no-`dir_fd` platforms.
- `_replace` `except OSError` around `finish`: turns a chmod or copystat failure caused by a swap into the rule's refusal.
- `mkdirs` descriptor branch: directories are created through the walk, not by path.
- `safe_write.move` (public): the archive sheet move under the rule, by descriptor with the M21.37 fallback.
- `archive_ops` `os.readlink` join for a linked origin: replaces `resolve()` with the path as spelled.
- `archive_ops` `safe_write.remove` for the dangling origin link: unlinks it under the rule.
- Test `test_a_link_swapped_in_right_before_replace_is_refused`, parametrized `dir_fd` (descriptors / no-dir-fd): the no-dir-fd id checks that M21.37's re-check still refuses.
- Test helper `swap_after_open` (wraps public `os.open`, adds itself to `os.supports_dir_fd`): the racer between the walk and the replace.
- Test `test_a_link_swapped_in_after_the_walk_is_refused` (generated file via `regenerate_generated_files`, managed block via `apply_managed_block(strict=True)`, nested file x destination/parent): the plan's first three table rows.
- Test `test_a_directory_swapped_for_a_link_before_a_sheet_moves_is_refused` (sheet parent / archive planning dir): the plan's archive row.
- Test `test_planning_sheets_move_out_of_the_flat_planning_dir`, parametrized `in-repo-link`: an in-repo linked sheet still moves its target.
