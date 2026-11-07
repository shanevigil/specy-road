# M21.38 — Review writers and the review lock refuse any symlink on the path

Review writers and `review_run_lock` now use `safe_write` from the project directory that holds `work/` (`project_of`: the parent of the `work` component, which is `reviews.parents[2]` for a hand-off directory). A symlink at `work`, `work/reviews`, `work/reviews/<node>`, or at the lock, record, marker, acceptance, packet or prompt file is refused before any write or launch. `SafeWriteError` is translated at the CLI to `error: <message>` on stderr, exit 1, no traceback.

`review record` checks the live `REVIEW-<model>.md` and `history/` before it writes the record or clears `REJECTED-<model>.md`. After a reviewer run, `Snapshot` keeps that project root and `restore` (and the post-run snapshot) lstat `work` and `work/reviews` before any traversal; a symlink at either is a `review_failure` and is not read, deleted or written through. Below a verified root, `replace_file` still replaces a final link and `real_dirs` still removes reviewer-planted links.

`refused_link` stays. `generated_files.py`, `bundled_scripts/upgrade.py` and `bundled_scripts/upgrade_generated.py` still call it.

Touch zones, unchanged: `specy_road/review_lock.py`, `specy_road/review_policy_pin.py`, `specy_road/review_gate_ready.py`, `specy_road/review_rejected.py`, `specy_road/review_files.py`, `specy_road/review_delegate.py`, `specy_road/review_delegate_packet.py`, `specy_road/review_write_check.py`, `specy_road/managed_block.py` (not edited), `tests/test_review_writers_refuse_links.py`, `tests/test_writers_refuse_links_out.py`, `tests/test_review_concurrent_writers.py`, `docs/orchestration-reviewer-output.md`, `CHANGELOG.md`, `specy_road/bundled_scripts/review_cli.py`, `specy_road/bundled_scripts/role_prompt.py`, `specy_road/bundled_scripts/mark_implementation_reviewed.py`.

## Added

- `review_files.project_of`: one way to name the project directory that holds `work/`, so every writer checks from that root.
- `review_files._unlink_case_variant`: the case-variant loop unlinks only an `lstat` regular file or symlink entry, and only after the path has been checked.
- `review_write_check.ancestor_symlink`: `replace_file` and `append_log` refuse a symlink at any ancestor from the project root, not only the parent.
- `review_write_check.handoff_ancestor_link`: `Snapshot.restore` and the post-run snapshot lstat `work` and `work/reviews` before they traverse.
- `review_delegate._save`: skip `save_run` when an ancestor is a symlink, so its mkdir (outside this leaf) does not create a directory through a replaced `work/reviews`.
- `review_delegate._prompt_path`: the four delegate prompt file names in one place.
- `review_delegate._prompt_pair`: both files of a pair are checked before either is written, so a link at the second name writes nothing and launches nothing.
- `role_prompt._in_project`: an explicit `-o` outside the project stays a plain write; the check is lexical, so a symlink at `work` is still inside and is refused.
- `role_prompt._write_prompt`: the in-project prompt file goes through `safe_write` before launch.
- `review_run_lock` guard: `safe_write.mkdirs` and `safe_write.open_lock` replace `mkdir` and `open`, so a symlink at `work`, `work/reviews`, the node or the lock raises before `flock`.
- `write_rejected` guard: `safe_write.check` from the project root before any mkdir; a refusal is printed and the record refusal still returns.
- `_review_record_finish` guard: the live record and `history/` are checked before `write_review` and before `clear_rejected`.
- `write_review` guard: `safe_write.check` before `mkdirs` and before the case-variant loop; a dangling link at the name is refused.
- `archive_review` guard: `history/` and the copy are checked before the directory is made.
- `ensure_packet` guard: the packet is checked from the project root, then written with `safe_write.write`.
- `write_human_approval` and `cmd_accept_policy` guard: the record and `POLICY-ACCEPTED.yaml` are written with `safe_write.write`.
- `Snapshot.restore` branch: return without reading, deleting or writing when `work` or `work/reviews` is a symlink.
- post-run `snapshot` branch: record that symlink and skip the hand-off walk and record read.
- `replace_file` guard: `ELOOP` for any ancestor symlink; a final symlink is still replaced.
- `append_log` guard: return `devnull` and do not mkdir when an ancestor is a symlink.
- CLI guards: `cmd_review_record`, `cmd_review_record_locked`, `cmd_accept_policy`, `role_prompt.main`, `_gate_or_human_approval` and `cmd_review_delegate` print `error: <message>` and exit 1 on `SafeWriteError`.
- `_approval_failure`: the same stderr reasons the gate printed inline for `SigningError`, `ReviewRunBusy` and `SafeWriteError`.
- `_write_human_or_exit`: that try/except, so `_gate_or_human_approval` stays within the complexity limit. Same exit 1 and no traceback.
- mocks: none
- `test_the_lock_refuses_a_symlink_before_any_filing`: the five callers times the five lock layouts, path on stderr, no traceback, nothing launched.
- `test_review_record_refuses_a_linked_live_record`: a dangling or live `REVIEW-<model>.md` link is refused and the outside file is unchanged.
- `test_review_record_leaves_the_record_and_marker_when_history_is_linked`: a linked `history/` leaves the live record and the rejection marker byte-identical.
- `test_write_review_does_not_unlink_through_a_linked_node_directory`: a node directory linked at an outside dir holding `review-x.md` is refused before the case-variant loop.
- `test_archive_review_refuses_a_linked_history_directory`: `archive_review` refuses a linked `history/` before mkdir.
- `test_a_refused_marker_writes_nothing_outside`: a `REJECTED-<model>.md` link, a `work/reviews` link and a `work` link refuse the marker write.
- `test_delegate_refuses_a_linked_prompt_before_launch`: each of the four prompt names, the repair pair through `--resume` with a stored refusal, refuses before launch.
- `test_a_refused_then_repair_run_does_not_launch_the_repair`: a linked `-repair` file stops the repair turn after the first launch.
- `test_accept_policy_refuses_a_linked_acceptance_file`: a dangling or live `POLICY-ACCEPTED.yaml` link is refused.
- `test_human_approval_refuses_a_linked_record`: a dangling or live `REVIEW-human.md` link is refused.
- `test_prompt_run_refuses_its_default_file_before_launch`: `prompt --run`'s default file is refused before launch.
- `test_ensure_packet_refuses_a_linked_node_directory`: a linked node directory with no packet is refused.
- `test_a_reviewer_that_replaces_reviews_with_a_link_is_a_review_failure`: a fake reviewer replacing `work/reviews` after launch leaves the outside tree unchanged and the run is `review_failure`.
- `test_write_rejected_refuses_a_linked_ancestor_before_mkdir`: `write_rejected` itself refuses a linked `work` before mkdir.
- `test_writers_refuse_links_out.py` packet row: `ensure_packet` now raises `SafeWriteError`, which that row catches.
