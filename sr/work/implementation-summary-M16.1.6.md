# Implementation summary: M16.1.6

## What changed

- `scripts/review_effort_study.py` gains a `policy-evidence` mode: `python scripts/review_effort_study.py policy-evidence [NODE_ID ...] [-o DIR]`. It runs no reviewer CLI and makes no network call. It reads git and the main checkout's `work/reviews` (via `review_files.reviews_root`): each node's `history/` plus every live `REVIEW-*.md` that no history copy duplicates. The existing effort-study CLI, its arguments and its output are unchanged; `main` switches only on a leading `policy-evidence` word.
- `sr/planning/M16.1.6_…md` gains the policy-to-evaluator table (A2), the evidence counts with their limits (A1), a keep/deprecate recommendation per policy (A3), and an empty maintainer-decision table for A4 (human).

## Fix round 1 (gpt-5.6-sol-high at c0ff7ff6)

- **Live records (A1/A3).** The class of failure is the record source: the scan read `history/` only. Now each live `REVIEW-*.md` joins its commit's case unless a history record duplicates it. A duplicate has the same model, full commit and verdict. Data equality was not usable, because live copies gain fields such as `independence`. A commit only a live record names becomes its own case, shown as round `live` in `cases.csv`. The RCA rule reads history alone, so for RCA that case is always unchanged. Every directory under `work/reviews` (except dot-directories) is scanned, not only those with `history/`. The sheet is recounted: 871 cases from 310 nodes. delta 11 and RCA 64 changed; pre-existing has 3 cited-only.
- **Filing time.** The source fix brought in records with no history stamp. Rather than special-casing them, there is now one rule (`filed_at`): the history stamp, or else the end of the record's own `date` day in UTC. This also makes the 10 `superseded-REVIEW-*` rounds replayable; they were unknown before. The sheet states the limit: in 44 cases the config found may be up to a day late.
- **Absent config defaults (A2).** The class of failure is a reconstructed config key or file that is absent but read without its documented default. `_agreement` now treats an absent `require_implementation_review_before_finish` as off, which is `git_workflow_config`'s default. It also treats an absent `orchestration.yaml` as asking for no reviewers, as `review_gate_agreement` does. The integration branch now comes from `resolve_integration_defaults` instead of a hand-written default of `main`. The policy keys already used `DEFAULT_POLICY`.
- **Excess.** `_git` is removed; its three call sites use `git_text`.
- **Public-command test coverage: blocked, outside the touch zones.** The finding asks for tests of `policy-evidence`, including an agreement regression case. Both belong in `tests/test_review_effort_study.py`, which is not one of this leaf's zones (`scripts/review_effort_study.py` and the sheet). Per the executor rules I did not edit it. **Coordinator:** add `tests/test_review_effort_study.py` to M16.1.6's touch zones so the next round can add the tests. The test should build a temporary git repo whose review history has a delta approval, a live-only `REVIEW-*.md` and a git-workflow file without the finish flag, run the command, and assert the counts in `cases.csv`.

## Probes

- The live records the history scan missed: 60 valid live records not duplicated by (model, commit, verdict) across 28 nodes are now in cases (re-counted with `list_reviews` against `list_review_history`).
- The data-equality dedupe I tried first is wrong: 677 of the live records differed from their history copy only in added fields (`independence`), so I replaced it with the (model, commit, verdict) key.
- Live records naming no commit: 0. A record without a commit cannot form a case, and `node_cases` leaves it out.
- Nodes with no `history/` directory: now scanned. 310 nodes have cases, up from 285.
- Records with no filing time: none left (871 of 871 have full provenance). 44 cases use the date-field rule, and their provenance says so.
- `_agreement` with an absent flag gives True and False (policy configured, disabled); explicit false gives True and False; explicit true gives False and False; an absent `orchestration.yaml` gives False.
- Other workflow reads with defaults: the integration branch now uses `resolve_integration_defaults`. No other git-workflow key is read.
- Orchestration defaults: the policy is `DEFAULT_POLICY` overlaid with the file's policy. With no file, the roster is `DEFAULT_CONFIG`'s, and `has_orchestration` is false.
- Each policy disabled alone moved no other policy in the full run (`moves_others`).
- The RCA baseline holds: every filed non-forced RCA replays (RCA has 0 unknown).
- No reviewers or network: the full run under `env -i PATH=/usr/bin:/bin unshare -rn` gave the same counts as the normal run.

## Acceptance

- **A1:** For each of the eight policies the script reports replayable, cited-only and unknown counts separately. One case is one node_key, commit and round (history order, or `live`) with every record at that commit. `cases.csv` lists each case's provenance: the record count, the filing time and how it was found, and the integration commit the configs were read from. A replayable case is evaluated once with the configured policy and once with only the selected policy disabled.
- **A2:** A change is counted from each policy's public evaluator, as the sheet's table lists. For RCA only the onset of an escalation counts, and a next-step change alone is not counted. A change counts only if no other policy's evaluator moves when this one is disabled.
- **A3:** The counts and recommendation are in the sheet: keep all eight. Unused or unknown is not a reason to remove a policy.
- **A4 (human):** I left the decision table empty.
- **A5:** No package code changed.
- **A6 (informational):** The script grew by about +309 lines (310 added, 1 removed), against the +120 estimate: eight evaluator adapters, archived-node reconstruction, the cross-policy guard and the filing-time rule. `scripts/lean_metrics.py` does not exist yet.

## Touch zones

`scripts/review_effort_study.py` and this leaf's planning sheet. `tests/test_review_effort_study.py` is needed and outside the zones (see above). `Case` is a plain class rather than a dataclass, because that test loads the script without registering it in `sys.modules`. The script is 493 lines, within the file-limits cap.

## Verification

- `python -m pytest -q -p no:cacheprovider tests/test_review_effort_study.py tests/parity/review_gate`
- `ruff check specy_road tests scripts`
- `specy-road file-limits`
- `specy-road validate`: exit 0
- `python scripts/review_effort_study.py policy-evidence -o /tmp/pe`: the full count, about 2 minutes

## Added

- `policy-evidence` dispatch in `main`: the new mode, leaving the study CLI unchanged.
- `Missing` exception: an evaluator input that cannot be reconstructed for one policy, so the case falls to cited-only or unknown.
- `Case` class, with `approvals` and `has_orchestration`: one round's records plus the reconstructed node, config, workflow and provenance.
- `_delta`, `_resumed`, `_red_green`, `_pre_existing`, `_deferral`, `_rca`, `_strong`, `_agreement`: one adapter per policy to its public evaluator (A2's table).
- `_rca` round-0 branch: a live-only commit is never a round the RCA rule counts.
- `_agreement` absent-file and absent-flag defaults: the defaults `review_gate_agreement` and `git_workflow_config` document (fix round 1).
- `POLICIES` table: evaluator, disabled form, citation pattern and what "changed" means, per policy.
- `OFF`, `STAMP`, `EVIDENCE_OUT` constants: an unreachable escalation threshold, the history filing-time pattern, and the CSV columns.
- `filed_at`: the single filing-time rule (stamp, or else the end of the `date` day).
- `node_then` (cached): the node at the reviewed commit, including nodes archived since, read through the manifest at that commit.
- `reconstruct`: rebuilds commit, node and configs from git at the round's time, recording the provenance or the reason it failed.
- `node_cases` with the `vote` dedupe key: history plus non-duplicated live records, one case per reviewed commit.
- `moves_others` guard: a change counts only if no other policy's outcome moves.
- `classify`: changed, unchanged, cited-only or unknown, per policy and case.
- `evidence_main`: the argument parser, `cases.csv` and the markdown count table.
- Removed: the `_git` helper (replaced by `git_text`).
- Tests: none. The test file is outside the touch zones; the coordinator is asked to add it.
- Mocks: none.
