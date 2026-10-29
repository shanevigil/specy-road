# Implementation summary for M3.15

## Summary

All four acceptance items are implemented in commit `be22616`.

- **A1, `prompt --ref`.** `specy-road prompt` now takes `--ref <branch or commit>` and passes it to `resolve_target`, the resolver `review-packet` and `review record` already use. A reviewer prompt for a node with no registry claim, Complete or not, is now written without a workaround. The reviewer prompt passes the same `--ref` on to the `review record` command it tells the reviewer to run, because without it that command would fail for want of a claim. Without `--ref`, an unclaimed node is still refused, with the same error as before. The error now lists `prompt` and `review list` among the commands that take `--ref`.
- **A2, `handoff status` exit codes.** Given one node, the command now exits:
  - `0` when the gate is met (`approved`), or when the node is Complete with no claim. That new state is `complete_no_claim`, shown in text and `--json`. Its records are listed, and the hint says to use `--ref`, not to pick the node up, because pickup refuses a Complete leaf.
  - `1` when the gate is not met (`waiting`, `in-review`, `blocked`, `stale`).
  - `2` when the gate cannot be determined. The JSON `state` field says which case: `unclaimed` (no claim names a commit) or `error` (an unknown node or a `--ref` that does not resolve). `--ref` without a node id also exits 2.

  The sweep (no node id) only reports and still exits 0.
- **A3, `review list <ID> [--ref]`.** This new subcommand in `review_cli.py` prints each filed `REVIEW-*.md` with its verdict, model, family and commit, marking signed records and naming the errors of invalid ones. It then prints the gate at the commit under review: `gate at <ref> @ <sha>: <summary>`, followed by the problems. When no claim names a commit and no `--ref` is given, it prints `gate: not evaluated — … pass --ref`. It only reads: it does not re-validate a notes file, relabel independence, or write anything.
- **A4, orchestration.yaml starter.** `templates/project/roadmap/orchestration.yaml` is the starter, and `init project` already copies the whole template tree. The starter now has one human entry (coordinator and reviewer), one placeholder executor entry (`my-executor` / `my-vendor`, `roles: [executor]`, with a comment to rename it), the default policy and comments. `validate --generate-orchestration` copies the same file into `roadmap/orchestration.yaml` after validation passes, if no file exists. If one exists, it leaves it alone and says so on stdout, so `--strict` does not count that message as a warning.

## Changes

- `specy_road/bundled_scripts/role_prompt.py`: `build_prompt(..., ref=None)`, `--ref` on the parser, and `--ref` added to the reviewer preamble's `review record` line when given.
- `specy_road/bundled_scripts/review_cli.py`:
  - `_unclaimed` reports `complete_no_claim` for a Complete node.
  - A new `_EXIT` table maps each state to its exit code.
  - `_fail` takes an optional exit code (`2` for `--ref` without a node).
  - New `cmd_review_list` and its `review list` subparser; the module docstring is updated.
- `specy_road/review_target.py`: the module docstring and the no-claim error name the commands that take `--ref`.
- `specy_road/bundled_scripts/validate_roadmap.py`: new `generate_orchestration()` and the `--generate-orchestration` flag. `validate_orchestration_contract`'s docstring is corrected, since a missing file no longer equals the scaffold exactly.
- `specy_road/templates/project/roadmap/orchestration.yaml`: the executor entry and starter comments.
- `specy_road/cli_usage.py`: help lines for `validate --generate-orchestration`, `prompt --ref`, the `handoff status` exit codes, and `review list`.
- `specy_road/templates/specyrd/commands/specyrd-handoff-status.md`, `specyrd-prompt.md`, `specyrd-review-record.md`: the new states, exit codes, `--ref` and `review list`.
- `docs/orchestration.md`:
  - The starter and `--generate-orchestration`.
  - `--ref` on every read-only review command, and `review list`.
  - The state table: `complete_no_claim`, and `unclaimed`/`error` reworded. The old "leftover … safe to delete" wording is gone.
  - The exit-code paragraph and the upgrade note.
  - The file stays at exactly the 400-line cap: my additions were folded into existing lines.

Final touch zones used: all of the above, plus `tests/`. These were in the touch zones but not touched: `specy_road/review_gate.py`, `specy_road/cli.py` (`review` already forwards to `review_cli.py`), `specy_road/init_project.py` (it already copies the template), `specy_road/cli_init_argparse.py`, and `docs/pm-llm-review.md` (it does not cover these commands).

## Behaviour changes callers may notice

- `handoff status <ID>` used to exit 0 for every resolvable node. It now exits 1 while the gate is unmet, so the `grind-session --pre-finish-cmd` example in `docs/orchestration.md` (`handoff status "$ID" && mark-implementation-reviewed --yes`) stops at `handoff status`. Before, it stopped at the refusal from `mark-implementation-reviewed`; the loop stops in both cases.
- Undeterminable cases (an unknown node, an unclaimed node, an unresolvable `--ref`, `--ref` without a node) moved from exit 1 to exit 2.
- A fresh `init project` roster now holds the placeholder `my-executor`. Until it is renamed, `orchestrate plan` can offer it as an executor.

## Out of zone (not edited)

- `suggested_prompts/bootstrap-roadmap.md:36` still says "scaffold default is one `human` reviewer". It should mention the placeholder executor and `validate --generate-orchestration`.
- `docs/agentic-sandbox-runbook.md` uses `handoff status` while walking through the gate; it does not rely on the old exit codes, but it is worth a re-read.
- The "missing file" `validate` notice (triage row 77) belongs to M3.11 and is not added here.

## Verification

- `pytest -q tests/test_review_cli.py tests/test_review_hardening.py tests/test_models_and_prompt.py tests/test_orchestration_config.py tests/test_review_evidence.py`: 80 passed.
- `pytest -q` (full suite): 2350 passed, 2 skipped, 1 failed. The failure is `tests/test_finish_task_commands.py::test_finish_already_done_on_branch_when_complete_and_deregistered`, and it also fails on the base `b74c4ee` in a clean worktree (with `specy_road` imported from that worktree). It fails inside `finish_milestone_rollout` / `feature_rm_registry`, which this leaf does not touch.
- `specy-road file-limits`: `OK: file limits satisfied.`
- `specy-road validate`, `export --check` and `digest --check` with `--repo-root tests/fixtures/specy_road_dogfood`: OK.
- `ruff check` on every changed file: all checks passed. Over the whole tree, the only finding is a C901 in `tests/test_grind_session.py:57`, a file this leaf does not touch.
- `python scripts/check_test_private_imports.py`: 0 new. `scripts/check_clones.py` could not run because `pylint` is not installed here.

## Added

### Helpers
- `review_cli.cmd_review_list`: the `review list` command (A3).
- `review_cli._EXIT`: maps a named node's state to its exit code (A2).
- `validate_roadmap.generate_orchestration`: writes the starter when the file is missing (A4).
- `_fail(msg, code=1)`, extended with `code`: lets `--ref` without a node exit 2 (A2).
- `build_prompt(..., ref=None)` and `_reviewer_preamble(..., ref=None)`, extended with `ref`: carry `--ref` through to resolution and to the reviewer's `review record` line (A1).

### Branches and guards
- `_unclaimed`: the `complete` branch picks the `complete_no_claim` state and the `--ref` hint (A2). Reached by a Complete node with no claim; tested.
- `cmd_review_list`: a resolution error other than "no registry claim" fails, and "no registry claim" prints `gate: not evaluated`. Reached by an unknown node or bad `--ref`, and by an unclaimed node; the no-claim path is tested.
- `generate_orchestration`: an existing file is left unchanged. Reached by rerunning on a repo with a file; tested.
- `_reviewer_preamble`: ` --ref <ref>` is added only when `--ref` was given (A1); tested.

### Mocks
- `monkeypatch` of `sys.argv` in `test_init_writes_the_starter_and_validate_generates_it_when_missing`, because `validate_roadmap.main()` reads `sys.argv`.

### Tests
- New `tests/test_review_cli.py::test_a_complete_node_without_a_claim_exits_0` (A2): `complete_no_claim` in text and `--json`, exit 0, no pickup advice.
- New `tests/test_review_cli.py::test_review_list_prints_records_and_the_gate_and_writes_nothing` (A3): records with verdict, family and commit; the gate with a claim, without one, and with `--ref`; the files are byte-identical afterwards.
- New `tests/test_models_and_prompt.py::test_reviewer_prompt_takes_ref_for_a_complete_node_without_a_claim` (A1): refused without `--ref`, written with it, and the prompt carries `base:` and the `--ref` on the `review record` line.
- New `tests/test_orchestration_config.py::test_init_writes_the_starter_and_validate_generates_it_when_missing` (A4): `init project` writes the template; `validate --generate-orchestration` writes the same bytes when the file is missing and leaves an existing one alone.
- `_status` helpers in `tests/test_review_cli.py` and `tests/test_review_evidence.py` changed: they now assert the exit is 0 when the policy is met and 1 when it is not. Before, they asserted 0 for every state; A2 changes that contract, and every existing status check now also checks the exit.
- Expected codes moved from 1 to 2 for the undeterminable cases, per A2:
  - `test_records_without_a_claim_are_listed_with_their_verdicts` (unclaimed with records, previously 0; and `--ref` without a node, previously 1)
  - `test_no_claim_and_no_records_is_an_empty_directory`
  - `test_status_exit_codes_and_leftover_directories` (unknown node)
  - `test_naming_an_unclaimed_node_exits_1`, renamed `test_naming_an_unclaimed_node_exits_2`
- `test_template_validates_and_matches_defaults` changed: the policy still equals the defaults, and the roster is now the default human entry plus one executor entry (A4).
