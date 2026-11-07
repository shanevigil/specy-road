# M21.38 — Review writers and the review lock refuse any symlink on the path

Review writers and `review_run_lock` now use `safe_write` from the project directory that holds the hand-off `work/` (`project_of`: the parent of the last `work` followed by `reviews`, which is `parents[2]` of `work/reviews/<node>` even when an earlier directory is also named `work`). A symlink at `work`, `work/reviews`, `work/reviews/<node>`, or at the lock, record, marker, acceptance, packet or prompt file is refused before any write or launch. `SafeWriteError` is translated at the CLI to `error: <message>` on stderr, exit 1, no traceback.

`review record` checks the live `REVIEW-<model>.md` and `history/` before it writes the record or clears `REJECTED-<model>.md`. After a reviewer run, `Snapshot` keeps that project root and `restore` (and the post-run snapshot) lstat `work` and `work/reviews` before any traversal; a symlink at either is a `review_failure` and is not read, deleted or written through. Below a verified root, `replace_file` still replaces a final link and `real_dirs` still removes reviewer-planted links.

`refused_link` stays. `generated_files.py`, `bundled_scripts/upgrade.py` and `bundled_scripts/upgrade_generated.py` still call it.

Touch zones, unchanged: `specy_road/review_lock.py`, `specy_road/review_policy_pin.py`, `specy_road/review_gate_ready.py`, `specy_road/review_rejected.py`, `specy_road/review_files.py`, `specy_road/review_delegate.py`, `specy_road/review_delegate_packet.py`, `specy_road/review_write_check.py`, `specy_road/managed_block.py` (not edited), `tests/test_review_writers_refuse_links.py`, `tests/test_writers_refuse_links_out.py`, `tests/test_review_concurrent_writers.py`, `docs/orchestration-reviewer-output.md`, `CHANGELOG.md`, `specy_road/bundled_scripts/review_cli.py`, `specy_road/bundled_scripts/role_prompt.py`, `specy_road/bundled_scripts/mark_implementation_reviewed.py`.

## Added

- `review_files._work_index`: the hand-off `work` is the last one followed by `reviews`, else the last `work`, so an earlier directory named `work` is not the project.
- `review_files.project_of`: the parent of that `work`, so every writer checks from the hand-off project. No `work` at all stays two parents up.
- `review_files._unlink_case_variant`: the case-variant loop unlinks only an `lstat` regular file or symlink entry, and only after the path has been checked.
- `review_write_check.ancestor_symlink`: `replace_file` and `append_log` refuse a symlink at any ancestor from the project root, not only the parent.
- `review_write_check.handoff_ancestor_link`: `Snapshot.restore` and the post-run snapshot lstat `work` and `work/reviews` before they traverse.
- `review_delegate._save`: skip `save_run` when an ancestor is a symlink, so its mkdir (outside this leaf) does not create a directory through a replaced `work/reviews`.
- `review_delegate._prompt_path`: the four delegate prompt file names in one place.
- `review_delegate._prompt_pair`: both files of a pair are checked before either is written, so a link at the second name writes nothing and launches nothing.
- `role_prompt._spelled`: a relative path is cwd-relative, with `.` and `..` collapsed and no symlink followed, before any inside-project choice.
- `role_prompt._in_project`: the spelled destination under the spelled project root. A symlink at `work` is still inside and is refused.
- `role_prompt._write_prompt`: the spelled in-project path goes through `safe_write`; an explicit `-o` outside stays a plain write of that same destination.
- `review_run_lock` guard: `safe_write.mkdirs` and `safe_write.open_lock` replace `mkdir` and `open`, so a symlink at `work`, `work/reviews`, the node or the lock raises before `flock`.
- `write_rejected` guard: `safe_write.check` from the project root before any mkdir; a refusal is printed and the record refusal still returns.
- `_review_record_finish` guard: the live record and `history/` are checked before `write_review` and before `clear_rejected`.
- `write_review` guard: `safe_write.check` before `mkdirs` and before the case-variant loop; a dangling link at the name is refused.
- `archive_review` guard: `history/` and the copy are checked before the directory is made.
- `ensure_packet` guard: the packet is checked from the project root, then written with `safe_write.write`.
- `write_human_approval` and `cmd_accept_policy` guard: the record and `POLICY-ACCEPTED.yaml` are written with `safe_write.write`.
- `_write_acceptances` after the WIP merge: M22.34's `--all-open` and plain-language text stay, and every acceptance file is checked with `safe_write` before any of them is written. A symlink or a held lock still writes nothing.
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
- `test_the_owned_root_is_the_hand_off_project_when_an_earlier_directory_is_named_work`: the hand-off node, a file under it, a `work/` path with no `reviews`, and a bare path with no `work`.
- `test_prompt_o_relative_is_cwd_relative_before_the_safe_write_choice`: `-o relative.md` and `-o nested/relative.md` from a cwd outside the project, then `-o work/from-cwd.md` from the project.
- `review_files.project_of`: a relative path whose first component is `work` returns `.` (`Path(*parts[:index])` with an empty prefix), which is `parents[2]` of `work/reviews/<node>`.
- `review_write_check.handoff_closed`: a symlink at `work`, `work/reviews`, or the node directory. `reviews_listing` returns a non-directory when this hits, so readers do not follow it.
- `mark_implementation_reviewed._refuse_linked_handoff`: `safe_write.check` of the node directory before `evaluate_gate`, so the command names the path and exits 1 without committing the registry.
- `test_a_relative_hand_off_is_owned_by_the_directory_that_holds_work`: `project_of(Path("work/reviews/M1"))` is `.`, and the lock and `write_review` land under `work/reviews/M1`.
- `test_a_relative_hand_off_does_not_follow_a_top_level_work_symlink`: the lock, `write_review`, `append_log` and `replace_file` on relative paths leave the outside tree unchanged.
- `test_mark_reviewed_refuses_a_linked_node_before_the_gate`: a valid outside `REVIEW-human.md` behind a node symlink does not count, and `--yes` does not commit the registry.
- `review_write_check.path_ancestor_link`: every ancestor of a path from a root, by `lstat`, final name excluded. `ancestor_symlink` is that walk from `project_of`.
- `review_delegate._span_text` and `review_record_write._run_span`: that walk from the saved root before the log is opened. A symlink at the node directory yields `""`.
- `test_delegate_does_not_open_a_log_behind_a_replaced_node_directory`: `review delegate` leaves an outside `RUN-opus.log` unopened (its access time) and unread.
- `test_prompt_run_does_not_open_a_log_behind_a_replaced_node_directory`: `prompt --run` does the same, exits 1, and does not raise.
- `review_record_write._run_span`: the same check before `prompt --run` reads its log.
- `role_prompt_cli._finish_cli_review_run`: the prompt close's log write and record save, reached only when the hand-off ancestors are real.
- `test_review_record_refuses_a_linked_marker_before_filing`: a dangling or live `REJECTED-<model>.md` on a successful filing writes no live record.
- `test_a_reviewer_that_replaces_reviews_with_a_link_is_a_review_failure`: the outside record is a valid `outside/M1.1/REVIEW-opus.md`, and the gate's approvals stay empty.
- `test_prompt_run_does_not_follow_a_replaced_reviews_directory`: the same plant through `prompt --run` exits 1, does not raise, and does not count the outside record.

## Probes

- `project_of` of `.../workspaces/work/repo/work/reviews/M1.1` and of `REVIEW-opus.md` under it returns `repo`, the node directory's `parents[2]`. The earlier `work` is not the hand-off. `write_review` then writes that file.
- `project_of` of `.../workspaces/work/repo/work/prompt.md` (a `work` with no `reviews`) returns `repo`, the last `work`. Same rule, not only the hand-off pair.
- `project_of` of a bare `tmp/M1.1/REVIEW-opus.md` with no `work` is still two parents up. `tests/test_review_file_case.py` still passes.
- Callers of `project_of`: `review_lock`, `write_review`, `archive_review`, `write_rejected`, `_review_record_finish`, `ensure_packet`, `write_human_approval`, `_write_acceptances`, `ancestor_symlink`, and `snapshot`. None of them searches for a component named `work`. They use this one root.
- `handoff_ancestor_link` walks `work` and `work/reviews` under the root `snapshot` stored from `project_of`. It does not pick an earlier `work`.
- Delegate prompt files are `repo_root / "work" / <name>` written with `safe_write` root `repo_root`. A directory named `work` outside the repo is above that root. Not this class.
- `prompt -o relative.md` and `prompt -o nested/relative.md` from a cwd outside the project create those files under the cwd. `repo/relative.md` and `repo/nested` are absent.
- `prompt -o work/from-cwd.md` with the cwd at the project creates `work/from-cwd.md` inside it, so a relative path is cwd-relative and then classified.
- The default prompt path, used when `-o` is omitted, is `root / "work" / prompt-<node>-<role>-<model>.md`. It is a project path, not a cwd-relative user path. Unchanged.
- The only user-supplied output path in this leaf is `prompt -o`. No other writer classifies a relative path by joining it to the project.
- A dangling and a live `REJECTED-opus.md` on a successful `review record`: exit 1, the marker path is named, the live `REVIEW-opus.md` is absent, and the outside file is unchanged. The success path checks that marker with the live record and `history/` before any write.
- `list_reviews`, `list_ready`, `list_review_history` and `run_states` list through `reviews_listing`. With `work/reviews` linked at an outside directory that holds a valid `M1.1/REVIEW-opus.md`, the gate's approvals are empty.
- `project_of(Path("work/reviews/M1"))` and `project_of(Path("work/prompt.md"))` are `.`, the same as `parents[2]` of `work/reviews/M1`. From that directory, `write_review` and `review_run_lock` create `work/reviews/M1/REVIEW-opus.md` and `.review-run.lock`. `work/work` is absent.
- With the cwd's `work` linked outside, `review_run_lock` and `write_review` raise `SafeWriteError`, `append_log` writes nothing, and `replace_file` raises `ELOOP`. The outside tree is unchanged. `ancestor_symlink` and `safe_write` both start at `.`, so the first component `work` is the link they refuse. `handoff_ancestor_link` no longer treats `.` as "not recorded"; an absent `work` still returns none.
- `handoff_closed` is that ancestor check or a symlink at the node directory. `reviews_listing` uses it, so `evaluate_gate` on a node linked at a valid `REVIEW-human.md` has no approvals and does not pass. `load_review` of that outside file is ok.
- `mark-implementation-reviewed --yes` hits `_refuse_linked_handoff` before `evaluate_gate`: exit 1, the node path and `symlink` on stderr, no `Review policy` line, registry bytes and `HEAD` unchanged, no `.review-run.lock` outside.
- `node_ids_with_reviews` still uses `is_dir`, so a linked node can appear by name. It does not read a review or commit the registry. `review_run_status`, `review_usage`, `rework_rca` and `review_deferral` open `reviews_dir` directly and are outside this leaf; the gate and the commit go through `reviews_listing` and `_refuse_linked_handoff`.
- Delegate `_model_check`, `_attempts`, `_file` and `_close` read the log through `_span_text(before.owned, ...)`. That walks every ancestor of the log from the saved root before `attempt_text`. A node directory the harness replaces with a symlink leaves the outside `RUN-opus.log` access time unchanged, and the run stays `review_failure`.
- `run_and_file` reads the log through `_run_span(before.owned, ...)`, the same walk. `close_cli_review_run` uses it on the run record and returns before `replace_file` and `save_run`. `prompt --run` exits 1 with `review_failure`, no traceback, and the outside log's access time unchanged.
- The post-run snapshot uses `handoff_closed` on the path saved before the run, so a node directory replaced by a symlink is not listed or read. `restore` still removes that symlink: it only returns early for `work` and `work/reviews`.
- `file_review` still decides `review_failure` from that snapshot. The log was the open that used to happen before the snapshot, and only `work` and `work/reviews` were checked.
- `path_ancestor_link` does not include the log file itself. A symlink at `RUN-<model>.log` is the final component; `append_log` still refuses to write through one. This round's open is the node directory.
- A relative `path` keeps a relative `root`. `replace_file(Path("work/reviews/M1/notes.md"))` with `work` linked outside still raises `ELOOP`, and the outside tree is unchanged. An absolute log under a relative root is the case that joins the root to the current directory.
- Zones added because the review named code that lives there: `specy_road/review_record_write.py` (`run_and_file`'s log read) and `specy_road/bundled_scripts/role_prompt_cli.py` (the prompt close that raised `ELOOP`).
