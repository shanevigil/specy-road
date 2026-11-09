# Implementation summary — M16.2.1

Delete dead and unwired code from the decided list (D1-D6) and add vulture as an
advisory CI step. Implementation commit: `84918fc6` on
`feature/rm-delete-dead-and-unwired-code-from-a-decided-list-and-add-vulture-as-an-advisory-ci-step`
(base `1d6697d8`).

## Acceptance

- **A1 (D1-D6 applied).** Re-scanned with `git grep` at pickup: every listed name had no
  production caller.
  - D1 deleted: `roadmap_chunk_utils.resolve_chunk_file`,
    `finish_land_integration.integration_commits_ahead_of_remote`,
    `milestone_session.remove_milestone_session`,
    `roadmap_gui_settings_tokens._obfuscate_llm_git`,
    `worker_adapter_parsers.has_prompt_placeholder`.
    `upgrade_templates.missing_work_template_rels` was skipped: the coordinator's resolution
    says it was already removed (`54c94dbb`).
  - D2 deleted: `specyrd_hooks.HOOKS_REL`, `integrity_removals.REMOVAL_KEY` (and the
    `import re` only it used), and `review_packet`'s unused `test_integrity_section` import.
    `tests/test_integrity.py` reached that function through `review_packet`, so it now
    reads it from `review_packet_observed`, where it is defined. It imports the module, not
    the name, because pytest would collect a bare `test_integrity_section` as a test.
    Kept and whitelisted: `_IndentedDumper.increase_indent`'s `indentless` and
    `FixRound.__call__`'s `option_string`.
  - D3 deleted with tests: `export_roadmap_md.render_phase_doc`,
    `managed_block.remove_managed_block`,
    `planning_sheet_bootstrap.ensure_planning_sheet_for_new_node` and
    `remove_planning_sheet_if_present`, `review_record_rules.defect_word`,
    `worker_state.record_intervention`, `roadmap_layout.compute_depths`.
    `export_roadmap_md._render_details` went too: `render_phase_doc` was its only caller.
    The section comment in `worker_state.py` changed from "lease, checkpoint,
    intervention" to "lease, checkpoint".
  - D4 deleted: `specy_road/bundled_scripts/migrate_stable_node_keys.py`.
  - D5 and D6 kept (see A2 and the whitelist).
- **A2.** `behaviour_changes.py` is kept. Its docstring no longer names M13.14 as its
  consumer. The whitelist lists `CATALOGUE` and `BehaviourChange.contradicted_by`.
- **A3.**
  - `.github/workflows/validate.yml` gains the step "Dead code (vulture, 60% confidence,
    advisory)", which runs `vulture specy_road scripts --min-confidence 60` with
    `continue-on-error: true`.
  - `scripts/vulture_whitelist.py` lists: the FastAPI routes, middleware and handlers; the
    `pytest_runtest_logstart` hook in `scripts/lean_metrics.py`; the two callback
    parameters; and the D5 and D6 names. No entry point is reported at 60%, so none is
    listed.
  - `vulture==2.16` is exact-pinned in the `dev` extra and is not in
    `project.dependencies`.
  - `requirements-ci.txt` was regenerated with `pip-compile requirements-ci.in -o
    requirements-ci.txt` under Python 3.12. The lock diff is only the added `vulture==2.16`.
    `requirements-ci.in` needed no change, because it already installs `-e .[dev]`.
  - `pip-audit -r requirements-ci.txt` reports "No known vulnerabilities found".
- **A4.**
  - The parity harness (`tests/parity/`) is unchanged and green.
  - **`planned_test_changes` was not set on M16.2.1 when I picked it up.** The integration
    branch has no field, and `integrity_gate` is not on in `sr/roadmap/orchestration.yaml`.
    I applied the decided D3 rows as written.
  - `specy-road integrity M16.2.1` prints the lines below. The coordinator should set them as
    this leaf's `planned_test_changes` so that A4's equality holds:

    ```text
    assert-loss: tests/test_outline_renumber.py::test_effective_dependency_includes_ancestor 2->1
    assert-loss: tests/test_review_record_rules.py::test_record_refuses_an_approve_whose_notes_carry_an_unclassified_observation 7->6
    removed-test: tests/test_export_roadmap_md.py::test_render_phase_doc_decision_decided
    removed-test: tests/test_export_roadmap_md.py::test_render_phase_doc_decision_pending
    removed-test: tests/test_export_roadmap_md.py::test_render_phase_doc_includes_acceptance
    removed-test: tests/test_export_roadmap_md.py::test_render_phase_doc_includes_goal
    removed-test: tests/test_export_roadmap_md.py::test_render_phase_doc_no_details_section_when_absent
    removed-test: tests/test_managed_block.py::test_removing_the_block_leaves_the_rest_alone
    removed-test: tests/test_managed_block.py::test_removing_when_there_is_no_block_is_a_no_op
    removed-test: tests/test_planning_sheet_bootstrap.py::test_ensure_planning_sheet_creates_file_and_sets_planning_dir
    removed-test: tests/test_planning_sheet_bootstrap.py::test_ensure_planning_sheet_gate_writes_gate_template
    removed-test: tests/test_planning_sheet_bootstrap.py::test_ensure_planning_sheet_noop_for_unknown_type
    removed-test: tests/test_planning_sheet_bootstrap.py::test_ensure_planning_sheet_raises_when_planning_path_is_directory
    removed-test: tests/test_planning_sheet_bootstrap.py::test_remove_planning_sheet_if_present
    removed-test: tests/test_review_record_rules.py::test_defect_word
    removed-test: tests/test_worker_state.py::test_intervention_bumps_the_epoch_and_checkpoint_records_head
    ```

    Each line removes only assertions on deleted code:
    - The two `assert-loss` lines are the `compute_depths` and `defect_word` assertions.
    - The `test_worker_state.py` line is the old name of a test that keeps its
      checkpoint and flag assertions. Its `record_intervention` assertions went, and it was
      renamed `test_checkpoint_records_head_and_a_flag_is_set_once` so its name stays true.
  - What still covers the behaviour of the deleted tests:
    - `plan_planning_sheet_for_new_node` is still exercised through add-node and outline
      group (the CRUD and scenario tests).
    - The defect vocabulary is still exercised through `test_note_problem` and
      `test_clause_problem` in `tests/test_review_record_rules.py`.
- **A5 (informational).** Package `specy_road/`: 16 files, +5 / -299. Tests: 7 files,
  +3 / -190.
  - `scripts/line_width_baseline.json` and `scripts/ruff_quality_baseline.json` were
    lowered only for the files this leaf touched.
  - The ruff baseline was lowered with `ruff_quality_baseline.py --shrink`. I restricted it
    to touched files, because `--shrink` also dropped entries for files that other leaves
    had already removed.
  - The width entries were lowered by hand, per that script's docstring.
  - `scripts/lean_metrics.py --check` did not finish inside my tool's 10-minute limit,
    because it runs the whole suite under coverage. Its deltas are therefore not reported
    here.

## Advisory vulture findings left (not on the decided list)

The CI step prints these at 60%. Most are names used only by tests, which the scan does not
read, or are false positives: attributes set on `shlex` and `sqlite3` objects, dataclass
fields, and argparse's `allow_abbrev`. Two are in this leaf's zones but outside D1-D6, so
they were left alone for a later decision:

- `managed_block.refused_link`'s `any_link` parameter (100%); its docstring says it is
  "kept for callers".
- `review_record_rules.unexplained_defects`, used by tests and named in a docstring.

`review_packet_observed.test_integrity_section` now shows as test-only, because D2 removed
its unused re-export. That file is outside the zones.

## Touch zones

The list is accurate. Files changed: the zoned package files, except `registry_yaml.py` and
`worker_cli_args.py`, which were kept as decided. Also changed: `scripts/vulture_whitelist.py`
(new), `.github/workflows/validate.yml`, `pyproject.toml`, `requirements-ci.txt`, both
baselines, and the seven test files above. `requirements-ci.in` was unchanged. No path
outside the zones was needed.

## Verification

- `ruff check specy_road tests scripts`, `specy-road file-limits`, and `validate`,
  `export --check` and `digest --check` on the dogfood fixture: all clean.
  `scripts/check_clones.py` reports 0 new pairs. `scripts/check_test_private_imports.py`
  passes.
- `pytest -n 4`: 7002 passed, 15 skipped.
- `pip-audit -r requirements-ci.txt`: no known vulnerabilities.

## Fix round 1 (review by gpt-6.1-sol at 0d672ccf)

**Finding:** A4 fails because M16.2.1 has no `planned_test_changes`.

**Class:** the leaf's approved-removal plan is missing. A4 compares this leaf's removed tests
against that plan, so with no plan the equality cannot hold.

**Where it lives:** in the roadmap node data on the integration branch
(`sr/roadmap/phases/M16__511edd.json`, node M16.2.1). `docs/roadmap-authoring.md` says a
declaration made on the leaf branch does not count. That file is outside this leaf's touch
zones, and executors may not edit roadmap or registry files. **This leaf cannot fix the
finding.**

**Coordinator action:** on `WIP/improvements-0-3-1`, set M16.2.1's `planned_test_changes` to
the 16 lines listed under A4 above. They are unchanged after the merge (see Probes). Then
regenerate the review packet.

**Code changes this round:** none. The reviewer passed A1-A3 and every removal line. The only
commit this round is the merge of `origin/WIP/improvements-0-3-1`, which brought only upstream
changes, and this summary update. No other part of the change depends on the missing field.

## Probes

- `planned_test_changes` on `origin/WIP/improvements-0-3-1` after `git fetch`: absent
  (`None`). The finding stands upstream.
- `specy-road integrity M16.2.1` after the merge: 16 lines (14 `removed-test`,
  2 `assert-loss`). Sorted, they are identical to the A4 list in this summary.
  - So the merge added no removal or weakening.
  - So the list the coordinator sets is still exact.
- Other removal sources: every test diff in this leaf is in the seven test files named under
  A4. The merge's test changes (`tests/test_lean_gates.py`,
  `tests/test_verify_wheel_contents.py`) come from upstream and produce no integrity line.
- `.github/workflows/validate.yml` after the merge: the advisory vulture step is intact
  (lines 149-154). The upstream edits there are only to comments on the hygiene step and the
  checkout step.
- `ruff check specy_road tests scripts`: passed. `specy-road file-limits`: exit 0.

## Added

- Helpers: `scripts/vulture_whitelist.py` with `_Names` and `USED`. It is the vulture
  whitelist A3 requires. `_Names` makes the file runnable and ruff-clean, so it has no
  undefined names and no bare expressions. `__all__` keeps vulture from reporting `USED`.
- Branches or guards: none.
- Mocks: none.
- Tests: none. One test was renamed, to
  `tests/test_worker_state.py::test_checkpoint_records_head_and_a_flag_is_set_once`,
  because its old name described the deleted `record_intervention`.
- CI step: "Dead code (vulture, 60% confidence, advisory)" in
  `.github/workflows/validate.yml`, for A3.
- Dependency: `vulture==2.16` in the `dev` extra and in `requirements-ci.txt`, for A3.
