---
node_id: M8.3
model: gpt-6.1-sol
date: '2026-11-04'
verdict: block
commit: 27d39730a68c57d5c12b166a165464c4d0d6b9ca
acceptance:
  A1: pass
  A2: fail
  A3: fail
  A4: pass
  A5: pass
findings:
  correctness:
  - 'F1 — A2: specy_road/review_write_check.py:31 exempts .review-run.lock from comparison.
    Neither RootFence nor RunLog checks that file. Overwriting its existing contents
    in place changes no directory entry, so both reviewer launch paths can accept
    the verdict despite this forbidden write.'
  - 'F3 — A3: specy_road/review_record_write.py:188 retains an earlier answer whenever
    adapter.final_message returns None. A Codex stream containing a valid earlier
    agent_message followed by a terminal agent_message with text:null therefore selects
    the earlier verdict instead of requesting a rerun for the missing final answer.'
  regression:
  - 'F2 — A2: specy_road/bundled_scripts/role_prompt.py:386 closes the run without
    passing its filing Outcome. close_reviewer_cli_run ultimately calls close_run,
    which marks the run complete whenever an existing same-commit record remains valid.
    A write-failing rerun can consequently leave RUN state=complete, reason=null,
    and no reviewer-failure event.'
  boundary: []
  test_integrity: []
commands_rerun:
- 'Preconditions: verified PACKET.md exists, identified the feature worktree, and
  ran the prescribed git status command there; no disallowed changes.'
- 'PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS=''-p no:cacheprovider'' GIT_OPTIONAL_LOCKS=0
  pytest -q -n 4 -p no:cacheprovider tests/test_review_record_write.py — exited 1
  before collection: no usable temporary directory in the read-only sandbox.'
- 'AST import search identified 55 test modules importing changed production modules.
  Read-only pytest --collect-only -s -q -p no:cacheprovider over those modules succeeded:
  845 tests collected.'
- Directly invoked test_the_output_schema_is_the_record_schema_less_what_specy_road_fills,
  test_the_reviewer_process_writes_no_bytecode_or_pytest_cache, and test_the_final_complete_json_object_of_a_message_is_the_answer
  without fixtures; all three passed.
- 'PYTHONDONTWRITEBYTECODE=1 python scripts/check_test_private_imports.py — passed:
  115 current references, 118 baselined, zero new.'
- git diff --check 458dca91 27d39730 — passed.
- 'Read-only F1 probe: supplied snapshots differing only in existing .review-run.lock
  contents. written returned []; file_review returned recorded with filesystem writes
  suppressed and the record command stubbed.'
- 'Read-only F2 probe: invoked close_reviewer_cli_run with exit_code=1, a write-failure
  transcript, and an existing valid record simulated through its public validator.
  Saved state was complete, reason null, events [], despite the attempt containing
  the failure.'
- 'Read-only F3 probe: final_output(Codex(), stream) received a valid agent_message
  followed by agent_message text:null. It returned the earlier verdict; file_review
  reached recorded with filesystem writes suppressed and the record command stubbed.'
- 'Additional read-only API probes: strict_schema([]) returned an acceptance object
  with no properties; drop_nulls preserved required notes:null while removing optional
  model_version:null; reviewer_env preserved existing cache-disable options. Fresh
  unnamed-model launches retained Claude''s deny list, Codex read-only policy, and
  Cursor ask mode.'
verify_pre_existing: []
required_changes:
- 'F1: Remove .review-run.lock from snapshot exemptions, or explicitly guard its contents
  and metadata during each turn. Add a public-interface regression requiring review_failure
  and no verdict for an in-place lock-file overwrite.'
- 'F2: Propagate the current filing Outcome into prompt-CLI run closure. A review_failure
  or rerun must remain incomplete and emit its failure event even when an older same-commit
  review exists. Add a regression covering that existing-record case.'
- 'F3: Distinguish an irrelevant stream event from a terminal answer event containing
  no valid answer. A later missing or malformed terminal answer must invalidate any
  retained earlier verdict. Add a Codex resume regression requiring rerun and no newly
  filed record.'
fresh_session: true
authored_fix: false
is_coordinator: false
notes_sha256: 67c807dce350e8472bfba372b66835018633db7051f88f34993f35a8bfc1f245
launch_mode: full
toolkit_version: 0.3.1rc2+27d39730a68c
family: openai
independence: distinct-family
---

## Acceptance

A1: pass
A2: fail
A3: fail
A4: pass
A5: pass

## Findings

F1: The lock file is opened before either launch path takes its first snapshot. An overwrite of that existing file is filtered out by runtime_files/written. RootFence records the hand-off directory and RUN JSON only; RunLog checks the transcript only. The in-memory probe returned recorded. Required change F1 covers this write-check gap.

F2: run_and_file detects failure and returns nonzero, but role_prompt then calls close_reviewer_cli_run without the Outcome. Its close_run call treats an existing valid record as success. The probe saved complete/null/[] for state/reason/events. Required change F2 covers this reporting gap.

F3: Codex.final_message returns None for a recognized agent_message whose text is null. final_output treats that identically to an unrelated event and preserves an earlier answer. This concerns terminal-event extraction within one turn, distinct from the previously addressed stale output-file retry case. Required change F3 covers the missing-final-answer case.

## Verification limits

The targeted pytest verifier could not start; not a defect because the sandbox provides no writable temporary directory.

The 55 importer modules collected successfully; not a defect because collection required no fixture writes.

Write-dependent public-function probes and fixture-based execution remain unverified; not a defect because this session cannot create their required temporary files.

The failure probes used public APIs with writes suppressed; not a defect because their reported results explicitly describe simulations rather than completed harness integrations.

## Boundary and test integrity

Bookkeeping changes concern M8.3 and its generated rollup; not a defect because no unrelated registry entry changed.

The four replaced run-record tests retain their observable intent on structured output; not a defect because reviewer self-filing is now prohibited.

The private-import gate found zero new references; not a defect because the changed tests use public production names.

Removed explanatory text was moved or updated for the requested behavior; not a defect because no unrelated comment or docstring loss was identified.

## Excess

The summary includes an Added inventory covering adapter launches/extraction, schema conversion, write snapshots, turn fences, transcript checking, locking, CLI wiring, helpers and tests; not a defect because the requested inventory is present.

No additional excess change is requested; not a defect because the diff supplied no completed proof of unreachable defence, duplicate helper behavior, overlapping input coverage, or newly pinned private internals.