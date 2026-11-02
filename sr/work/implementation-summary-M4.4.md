# Implementation summary: `M4.4` — brainstorm-decisions

Branch `feature/rm-brainstorm-decisions`, base `00ea7546`. Executor: `claude-opus-5.5`.

## Acceptance

- **A1** — `IDEA_KINDS` gains `policy` (so `add-idea --kind policy`, `revise --kind policy`, the
  diverge prompts' kind list and the PM chat all accept it). `IDEA_STATUSES` gains `decided`.
  New subcommand `brainstorm decide <IDEA_ID> --decision TEXT` sets status `decided` through
  `set_status` (so a promoted or merged idea is refused, as for every triage) and records
  `decision: {status: decided, decision: TEXT, decided_at}`. `list` prints the decision under a
  decided row; `list --summary` and `--status decided` pick the status up from `IDEA_STATUSES`.
- **A2** — `promote` (CLI and the GUI route, which both go through `promote_session`) writes every
  `decided` idea as a bullet under the anchor sheet's `## Decided policies`
  (`- **<title>:** <decision> (brainstorm `<slug>`, <id>)`), never as a node. A re-run rewrites
  only this session's bullets (so an idea no longer decided drops out, the session's last one
  included) and keeps other sessions'. `--dry-run` writes nothing and names the sheet on stderr.
  `promote` says "nothing to promote" only when no accepted idea is pending and the anchor's
  policy section already matches the session's decided ideas. No anchor sheet (roadmap root, or a
  node without a sheet): stderr names the decided ideas left unwritten. Any policy-section change
  (including only removing stale bullets) and any decided idea make promote check the anchor
  exists and is not milestone-locked, like any parent, before anything is written. On a promote that also lands nodes, the
  sheet write sits inside the existing `TreeSnapshot`, so a failed validate restores it.
- **A3** — `frame --amend KEY --answer TEXT` (exactly one `--answer`; `KEY=TEXT` is accepted too)
  replaces a recorded answer and appends `{key, answer, replaced_at}` for the previous one to the
  session's new `frame_history`; amending a key the frame does not have is refused. A plain
  `--answer KEY=TEXT` that changes a recorded answer also keeps the old one in history (same text:
  no entry), so the history never silently loses an answer. `frame --provisional` / `--confirm`
  (mutually exclusive; refused while the frame is empty) set the session's new `frame_state`.
  Every prompt that shows the frame (round 1's recorded frame, later rounds, panel shards, the
  authoring prompt) then carries a `Frame state: provisional` / `confirmed` line; an unmarked
  frame adds none, so existing prompts are unchanged.

Session file: `frame_state` and `frame_history` are optional keys, omitted when empty, so
`SESSION_VERSION` stays 2 and older files read unchanged. A `frame_state` that is not
`provisional` / `confirmed` is reported with its fix, like a bad `mode`.

## Touch zones (confirmed)

Changed: `brainstorm_session.py`, `brainstorm_cli.py`, `brainstorm_cli_args.py`,
`brainstorm_cli_v2.py`, `brainstorm_cli_args_v2.py`, `brainstorm_promote.py`,
`brainstorm_prompt.py`, `docs/brainstorming.md`, `tests/test_brainstorm_decisions.py`.
`brainstorm_cli_revise.py` needed no change. The listed zones were sufficient.

Not changed, outside the zones, worth a follow-up:
- `brainstorm_prompt_diverge.py` `WRITE_ALLOW_LINES` lists `accept`, `reject`, `park`, `promote`
  as the PM's commands; `decide` and `frame --confirm` belong there too (the docs quickstart now
  says so). The same list is mirrored in `suggested_prompts/brainstorm-roadmap.md`.
- `gui_app_routes_brainstorm.py` `_payload` does not return `frame_state` / `frame_history`
  (the CLI's `list --json` does).

## Refactors forced by the 400-line file cap

- `execution_milestone_from_promote_sets` moved verbatim from `brainstorm_promote.py` to
  `brainstorm_cli_args.py` (it parses `promote --set`; `brainstorm_cli.py` now imports it from
  there; nothing else imported it). Without it, `brainstorm_promote.py` was 423 lines.
- `_replace_section` in `brainstorm_promote.py` now finds its section through the new
  `_section_span` (same behaviour), which `decided_policies` also uses.
- `BrainstormSession.to_dict` writes `panel`, `count`, `frame`, `allocation` and `clusters` through
  one omit-when-empty mapping instead of separate `if`s (same keys, same order, plus the two new ones).
- `_frame_answers` lives in `brainstorm_cli_args_v2.py` as `frame_answers` (argument parsing,
  and `brainstorm_cli_v2.py` had no room).

Every changed file ends at or under 400 lines (`session`, `prompt` and `promote` exactly 400).

## Review round 1 (gpt-6.1-sol, block on A2)

Finding: rejecting a session's last decided idea left its policy bullet in the anchor sheet,
because `cmd_promote` and `promote_session` both returned "nothing to promote" before the
policy writer ran. Fix: `seed_decided_policies` became `decided_policies`, which only computes
the reconciled sheet text (None when the section would not change; it no longer skips the
case of no decided ideas). `promote_session` computes it first and returns early only when
there are no landings *and* no policy change; when there is a change it runs `_assert_parent`
on the anchor (existence and milestone lock) before any write, then writes through the new
`_write_policies`. `cmd_promote`'s "nothing to promote" gate now asks `decided_policies` too
(only when no accepted idea is pending, so its no-sheet warning prints once).
`test_a_rerun_replaces_this_sessions_policies_and_keeps_other_sessions` now also rejects the
last decision and checks that this session's bullet is gone, the other session's stays, and a
further promote has nothing to do; `test_removing_a_policy_is_refused_under_a_locked_anchor`
covers the lock check on the removal-only path.

`tests/test_brainstorm_chat.py` (unchanged): the reviewer's two failures
(`test_the_default_endpoint_is_accepted`, `test_searching_without_a_key_names_the_missing_piece`,
public-address validation of `api.bing.microsoft.com`) do **not** reproduce here: 19 passed on
this branch, and 19 passed on `origin/WIP/improvements-0-3-1` (`03e60de`, in a throwaway
worktree). Neither this change nor that file touches the endpoint check; the failures depend on
how the reviewer's environment resolves that host.

## Verification

- Round 1 fix: `pytest -q -p no:cacheprovider tests/test_brainstorm_*.py tests/test_gui_app_brainstorm.py`: 301 passed, exit 0
  (`tests/test_brainstorm_decisions.py`: 19 passed).
- Before review: `pytest` (full suite): 2810 passed, 2 skipped in 1136.95s, exit 0.
- `ruff check specy_road tests scripts`: passed.
- `python scripts/check_clones.py` (pylint 4.1.3 from a scratch venv): 0 new clone pairs.
- `python scripts/check_test_private_imports.py`: 0 new.
- `specy-road file-limits`: OK.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: OK.

## Added

- `IDEA_KINDS` `policy` — A1: a policy is a kind of idea agents can record.
- `IDEA_STATUSES` `decided` — A1: a decision is its own status, not parked or rejected.
- `FRAME_STATES` constant in `brainstorm_session.py` — A3: the allowed `frame_state` values, validated on read.
- `BrainstormSession.frame_state` / `frame_history` fields, written when non-empty and read back — A3.
- Read-side guard in `_session_from_dict`: a bad `frame_state` raises with the fix (the `mode` check became a two-key loop) — a hand-edited file is reported, never coerced.
- `cmd_decide` in `brainstorm_cli_v2.py` and its `decide` parser in `brainstorm_cli_args_v2.py` — A1.
- Guard in `cmd_decide`: an empty `--decision` is refused — the decision text is what promote writes.
- `_set_answer` in `brainstorm_cli_v2.py` — A3: one place that keeps a replaced answer in `frame_history`.
- `frame_answers` in `brainstorm_cli_args_v2.py` — A3: parses `--answer KEY=TEXT` pairs or `--amend KEY` with one `--answer`.
- Guards in `frame_answers`: `--amend` needs exactly one non-empty `--answer`; a leading `KEY=` on it is dropped — so the amend form and the plain form both work.
- Guard in `cmd_frame`: `--amend` of a key the frame lacks is refused — nothing to keep in history.
- Guard in `cmd_frame`: `--provisional` / `--confirm` refused on an empty frame — there is nothing to mark.
- `frame` flags `--amend`, `--provisional`, `--confirm` (the last two a mutually exclusive group) — A3.
- `stage()` treats `decided` as triage — so the next-step hint after `decide` points at promote.
- `_print_rows` decision line for decided ideas, and `frame_state` / `frame_history` in `list --json` — A1/A3 visibility.
- `cmd_promote` "nothing to promote" gate also asks `decided_policies`, so a pending policy change (a new decision or a removed one) still runs promote — A2.
- `_section_span` in `brainstorm_promote.py` — A2: reads the existing `## Decided policies` body; shared with `_replace_section`.
- `decided_policies` in `brainstorm_promote.py` — A2: the anchor sheet's text with this session's bullets reconciled (other sessions' kept), or None when unchanged.
- `_write_policies` in `brainstorm_promote.py` — A2: writes (unless dry run) and reports that text; split out to keep `promote_session` under C901.
- Branch in `decided_policies`: no anchor sheet → stderr names the unwritten ideas — so a root-anchored session does not drop decisions silently.
- Branch in `promote_session`: a policy change alone still runs; the anchor is checked (exists, unlocked) when any idea is decided or the section changes; the snapshot is taken only when nodes are written — A2.
- `_frame_state_lines` in `brainstorm_prompt.py` — A3: the state marker every frame-showing prompt appends.
- Mocks: none.
- Tests, `tests/test_brainstorm_decisions.py` (19):
  - `test_add_idea_accepts_kind_policy` — A1 kind.
  - `test_decide_sets_status_decided_and_records_the_decision` — A1 status, record, list, summary.
  - `test_decide_needs_a_decision` — A1 required/empty `--decision`.
  - `test_decide_refuses_a_merged_idea` — `decide` goes through `set_status`'s refusals.
  - `test_promote_writes_decided_ideas_into_the_anchor_sheet_not_as_nodes` — A2 main path, beside a normal promotion.
  - `test_promote_with_only_decided_ideas_writes_the_section` — A2 without accepted ideas.
  - `test_promote_dry_run_writes_no_policies` — A2 dry run.
  - `test_a_rerun_replaces_this_sessions_policies_and_keeps_other_sessions` — A2 idempotence, multi-session safety, and removal of the session's last decision (review round 1).
  - `test_removing_a_policy_is_refused_under_a_locked_anchor` — the lock check on the removal-only path (review round 1).
  - `test_decided_ideas_without_an_anchor_sheet_are_reported_not_written` — A2 root anchor.
  - `test_amend_keeps_the_previous_answer_in_history` — A3 amend + history on disk.
  - `test_amend_takes_key_equals_text_too` — A3 amend form.
  - `test_amend_refuses_an_unrecorded_key_or_several_answers` — A3 guards.
  - `test_re_answering_a_key_keeps_only_changed_answers_in_history` — A3 plain re-answer.
  - `test_provisional_and_confirm_mark_the_frame_and_later_prompts_show_it` — A3 state + later round prompts.
  - `test_shard_prompts_show_the_frame_state` — A3 panel shards.
  - `test_provisional_and_confirm_are_exclusive_and_need_a_frame` — A3 guards.
  - `test_an_unmarked_frame_adds_no_state_line` — existing prompts unchanged.
  - `test_a_bad_frame_state_in_the_file_is_reported` — read-side guard.
