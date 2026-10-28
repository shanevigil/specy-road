# Implementation summary for M3.4

## Summary

Brainstorm prompts no longer anchor on the roadmap or open with a cold questionnaire, and every pass keeps its own prompt file.

- **A1:** The `specyrd-brainstorm` skill (first paragraph, above the first command) and load-order item 0 of the managed AGENTS.md block now say to run `brainstorm start` before reading the digest or anything else. `suggested_prompts/brainstorm-roadmap.md` says the same.
- **A2:** Round 1's Step 1 is now "frame the question before answering it". The agent proposes an answer for each canonical key from what the PM already said, marks the covered ones `assumed`, shows the whole proposed frame in one message, and asks only about a required key it could not propose.
  - The keys live in `FRAME_KEYS`. Required: `outcome`, `served`, `assumed-vs-known`, `not-the-question`. Optional: `metric`, `tried`, `fixed-or-choice`, `do-nothing`, `deadline`, `budget`.
  - The `frame` example prefixes an unconfirmed answer with `assumed:`.
- **A3:** `allocation_cells()` reads `sN: <cell>` (or `sN = …`) lines from the recorded allocation. A shard with a labelled line gets that cell; an unlabelled shard falls back to the old operator/direction-by-index choice.
  - With `--panel`, the round-1 prompt tells the coordinator to label one cell per shard.
  - `frame` rewrites the panel shard prompts in round 1, so they carry the recorded frame and cells. Shards are written at `start`, before any frame exists.
  - To rewrite at the same size, `start` records `--count` on the session as `count`. It is optional, written only when set, and a file without it still reads.
- **A4:** `prompt_path(root, slug, pass_name)` and `write_prompt(..., pass_name=...)` write one file per pass:
  - `-r<N>-prompt.md` for each diverge round;
  - `-r1-s<K>-prompt.md` for each panel shard;
  - `-recommend-prompt.md` and `-evidence-prompt.md`.

  Rerunning the same pass (for example `start` again in round 1) regenerates that pass's file; no pass writes another pass's file. `close` moves the new names and also the bare and `-s<K>` names that older versions wrote.
- **A5:** The `roadmap-context.md` line is omitted when the digest is absent. Other governance files keep their `_(missing)_` marker.
- **A6:** `start` prints a warning to stderr when the current branch is the integration branch (from `resolve_integration_defaults`), suggesting `git checkout -b chore/brainstorm-<slug>`. It still proceeds.
- **A7:** `next_step()` gives the follow-up command, always with `--slug`. The order is round → `next-round` / `recommend` → `evidence` then `verify` → triage (`list --by cluster`, accept/reject/park) → `promote --dry-run` / `promote` → `export && digest`, then `close`.
  - Printed by `start`, `next-round`, `recommend`, `evidence`, `verify`, `accept`/`reject`/`park` and `promote`.
  - In-pass commands the agent repeats (`add-idea`, `add-evidence`, `revise`, `frame`, `list`) print no hint. A hint on each of 40 `add-idea` calls would be noise; I read "every command" as every pass command.

## Changes

- `specy_road/bundled_scripts/brainstorm_prompt_diverge.py`: `FRAME_KEYS`, the `frame_lines` rewrite, the shard-labelling note in `allocation_lines`, `allocation_cells`, and `shard_lines` reading the cell.
- `specy_road/bundled_scripts/brainstorm_prompt.py`: the digest line is omitted when absent; `write_prompt(pass_name=)`.
- `specy_road/bundled_scripts/brainstorm_session.py`: `prompt_path(..., pass_name)`, plus the `count` field (dataclass, `to_dict`, read).
- `specy_road/bundled_scripts/brainstorm_cli_v2.py`:
  - per-pass names in `write_round_prompts`, with shard writing split into `_write_shard_prompts`;
  - the shard rewrite in `frame`;
  - `next_step`, `integration_branch_warning`, and hints in `next-round`, `evidence`, `verify` and `park`.
- `specy_road/bundled_scripts/brainstorm_cli.py`: the warning, `count`, and hints in `start`, `recommend`, triage and `promote`.
- `specy_road/bundled_scripts/brainstorm_cli_args_v2.py`: `--panel` and `--allocation` help.
- `specy_road/bundled_scripts/brainstorm_close.py`: `PROMPT_PASS_RE` and `_prompt_names`. The other-session guard now asks whether the name matches any other open session's pattern (it used to check whether the stem equals another slug).
- Docs:
  - `docs/brainstorming.md`;
  - `specy_road/templates/specyrd/commands/specyrd-brainstorm.md`;
  - `specy_road/templates/specyrd/agents-md-block.md` (one clause, still one line);
  - `specy_road/templates/project/work/README.md`;
  - `suggested_prompts/brainstorm-roadmap.md`.
- Tests:
  - new `tests/test_brainstorm_prompt_fixes.py`;
  - `tests/test_brainstorm_cli.py`, `tests/test_brainstorm_v2.py` and `tests/test_brainstorm_verify.py` read the per-pass file names.

Final touch zones: the brief's list plus the three paths the coordinator added (`brainstorm_close.py`, `templates/project/work/README.md`, `suggested_prompts/brainstorm-roadmap.md`). Two listed files needed no change: `brainstorm_prompt_evidence.py` and `brainstorm_cli_args.py`. Nothing outside the zones needed changing either: `gui_app_routes_brainstorm.py` only renders prompts and never writes prompt files, and the gitignore patterns (`work/brainstorm-*-prompt.md`) already cover the new names.

## Notes for reviewers

- **Block wording and the bootstrap prompt:** the block says `brainstorm start` (A1's own wording), not `` `specy-road brainstorm start` ``.
  - `tests/test_review_round6_docs.py::test_bootstrap_prompt_merges_the_block_verbatim_and_names_every_command_and_env_var` requires every `` `specy-road <cmd>` `` in the block to appear in `suggested_prompts/bootstrap-agents-md.md`. That file is outside the zones and does not mention brainstorm.
  - The block already refers to commands without the prefix elsewhere (`finish-this-task`).
  - If the bootstrap prompt should name `brainstorm`, that is a one-line follow-up there.
- **Copies of the block's old load-order wording, outside the zones:** `sr/AGENTS.md` and `docs/philosophy-and-scope.md:35`.
  - `refresh-stubs` rewrites `sr/AGENTS.md`.
  - `docs/philosophy-and-scope.md` is prose and needs a hand edit if it should match.
- **Shared names in `close`:** a name two open sessions could both own stays in `work/`. For example, `brainstorm-a-r1-prompt.md` while sessions `a` and `a-r1` are both open. Leaving a gitignored prompt behind is harmless; moving another session's prompt is the bug the guard prevents. New-format names of two different slugs cannot collide.
- `brainstorm_session.py` sits at 399 lines (cap 400). `PROMPT_PASS_RE` lives in `brainstorm_close.py`, its only reader.

## Verification

- `python -m pytest -q`: 2245 passed, 2 skipped.
- `ruff check specy_road tests scripts`: all checks passed.
- `python specy_road/bundled_scripts/validate_file_limits.py`: OK.
- `python scripts/check_clones.py --pylint <scratch venv pylint 4.1.3>`: 12 current, 12 baselined, 0 new.
- `python scripts/check_test_private_imports.py`: 118 current, 118 baselined, 0 new.
- Dogfood fixture: `validate_roadmap.py`, `export_roadmap_md.py --check` and `specy-road digest --check` all OK.
- Manual: `start --panel 2 --count 8` then `frame --allocation "s1: …"` on a fixture copy. Shard 1 shows the cell and the frame and asks for at least 4 ideas.

## Walkthrough

1. `specy-road brainstorm start --topic X --panel 2 --count 8` writes `work/brainstorm-x-r1-prompt.md` and `-r1-s1-`/`-r1-s2-` files, then prints `next: … next-round --slug x (round 2 of 2)`. On the integration branch it also warns on stderr.
2. The round-1 prompt's Step 1 lists the ten keys, with four marked required, and asks the agent to propose answers.
3. `brainstorm frame --answer outcome=… --allocation "s1: …"` prints `shard: … (rewritten)` twice. Shard 1 carries the cell and the frame.
4. `add-idea`, `next-round`, `recommend` and `evidence` each leave their own prompt file, and each prints the next command.

## Added

- `FRAME_KEYS` (brainstorm_prompt_diverge.py): the canonical keys with their questions and required flags, so A2's list lives in one place.
- `allocation_cells` and `_SHARD_CELL` (brainstorm_prompt_diverge.py): parse `sN:` cells from the free-text allocation (A3).
- Branch in `shard_lines` (cell from the allocation, else by shard number): A3's "derive from the allocation when one exists" plus the old behaviour as the fallback.
- Branch in `allocation_lines` (`if session.panel`): tells the coordinator how to label cells so shards can receive them.
- `_write_shard_prompts` (brainstorm_cli_v2.py): shared by `start` and `frame`, the latter so shard prompts carry the frame (A3).
- Branch in `cmd_frame` (panel and round 1): rewrites the shards after recording.
- `BrainstormSession.count` (brainstorm_session.py): the `--count` from `start`, so `frame` rewrites shards at the same size; a non-int or a value below 1 in the file reads as 0 (`frame` then uses the default of 20).
- `prompt_path(pass_name)` and `write_prompt(pass_name=)`: per-pass file names (A4). This replaces the `suffix` string surgery.
- `PROMPT_PASS_RE` and `_prompt_names` (brainstorm_close.py): `close` matches the per-pass names and legacy names; the guard checks other open sessions' patterns.
- Digest-line branch in `_governance_lines`: omit `roadmap-context.md` when absent (A5).
- `integration_branch_warning` (brainstorm_cli_v2.py): A6. It reuses `resolve_integration_defaults` and `current_branch_name`; no new git helper.
- `next_step` (brainstorm_cli_v2.py) and its calls in 8 commands: A7.
- Mocks: none. One `monkeypatch.delenv("SPECY_ROAD_INTEGRATION_BRANCH")` so the runner's env cannot pick the branch.
- Tests (tests/test_brainstorm_prompt_fixes.py):
  - `test_skill_and_managed_block_say_to_start_before_reading_the_digest`: A1.
  - `test_round_one_frame_proposes_answers_over_the_canonical_keys`: A2.
  - `test_frame_rewrites_panel_shards_with_their_allocation_cells_and_the_frame`: A3, covering labelled and unlabelled shards, the frame, and the recorded count.
  - `test_each_pass_keeps_its_own_prompt_and_names_the_next_command`: A4 and A7 in one walk-through, since both need the same command sequence.
  - `test_prompts_omit_the_digest_line_when_there_is_no_digest`: A5.
  - `test_start_warns_on_the_integration_branch_only`: A6, on a real `git init` copy.
- Test in tests/test_brainstorm_cli.py: `test_close_leaves_a_name_another_open_session_could_own`. It covers the other-session guard, which had no test.
- Extended tests:
  - `test_close_moves_the_session_and_its_prompts_and_nothing_else` now covers the per-pass and legacy names.
  - `test_panel_writes_independent_shards` now asserts no round-2 shard file.
  - `test_the_diverge_prompt_opens_with_socratic_questions` asserts the new Step 1 heading and the keyed `served` line. The old heading text is replaced by A2.
  - The `_prompt` helpers in three test files take a pass name.
