# Implementation summary: M16.1.6

## What changed

- `scripts/review_effort_study.py` gains a `policy-evidence` mode: `python scripts/review_effort_study.py policy-evidence [NODE_ID ...] [-o DIR]`. It runs no reviewer CLI and makes no network call; it reads `work/reviews/*/history` (the main checkout's, via `review_files.reviews_root`) and git only. The existing effort-study CLI, its arguments and its output are unchanged (`main` dispatches on a leading `policy-evidence` word only).
- `sr/planning/M16.1.6_…md` gains the policy-to-evaluator table (A2), the evidence counts with their limits (A1), a keep/deprecate recommendation per policy (A3) and an empty maintainer-decision table for A4 (human).

## Acceptance

- **A1:** For each of the eight policies the script reports replayable, cited-only and unknown counts separately. One case is one review round (node_key, commit, round number) with every history record at that commit. A case is replayable when its records validate and have a filing time and git gives back the commit, the node at that commit, and the orchestration and git-workflow config on the integration branch before the round's latest filing time. `cases.csv` lists that provenance per case. Each replayable case is evaluated with the configured policy and again with only the selected policy disabled.
- **A2:** A change is counted from each policy's public evaluator per the sheet's table. RCA counts the onset of an escalation, and a next-step change alone is not counted. A change counts only if no other policy's evaluator moves when this one is disabled (`moves_others`). No case leaked in the full run.
- **A3:** Counts are in the sheet: 838 cases from 285 nodes, 828 with full provenance. delta changed 11 rounds and RCA escalation changed 62. The other six changed none, because they were unused or off in this project, or their evidence was not kept (pre-existing: 3 cited-only). The recommendation is keep for all eight, and the sheet says unused or unknown is not a removal reason.
- **A4 (human):** I left the maintainer's decision table empty.
- **A5:** No package code changed (`git diff --stat` shows only the script and the sheet).
- **A6 (informational):** About +277 script lines (278 added, 1 removed), against the +120 estimate. The difference is the eight evaluator adapters, the reconstruction of archived nodes from the manifest at the commit, and the cross-policy check from "Done but wrong". `scripts/lean_metrics.py` does not exist yet (M16.1.7 has not landed), so I report no metric deltas.

## Done-but-wrong checks

- Replay reproduces what happened: every non-forced RCA record filed at a round replays as an escalation under the configured policy, or the case is unknown for RCA. All RCA records replayed. For the record-level policies the records hold reviewer verdicts, not gate verdicts, so the configured run is the baseline. The sheet says so.
- One policy at a time: `moves_others` makes any cross-effect count as not changed. None occurred.
- No reviewers launched: the full run used `env -i PATH=/usr/bin:/bin unshare -rn python scripts/review_effort_study.py policy-evidence` (claude, codex and agent are not on that PATH, and there is no network), and it gave the same counts.

## Touch zones

Confirmed as listed: `scripts/review_effort_study.py` and this leaf's planning sheet. No test was added. `tests/test_review_effort_study.py` is outside the zones, so the new mode has no automated test. A reviewer or the planner may want a zone for that file in a follow-up. `Case` is a plain class rather than a dataclass because that test loads the script without registering it in `sys.modules`, and `@dataclass` then fails at import.

New lines follow the file's existing width (ruff passes). M16.1.8's 100-column baseline has not landed yet.

## Verification

- `python -m ruff check scripts/review_effort_study.py`: clean; C901 (with `--ignore-noqa`): clean
- `python -m pytest -q -p no:cacheprovider tests/test_review_effort_study.py tests/parity/review_gate`: 67 passed
- `specy-road validate`: exit 0
- `specy-road file-limits`: OK (the script is about 460 lines)
- `python scripts/review_effort_study.py policy-evidence -o /tmp/pe`: the full count, about 2 minutes

## Added

- `policy-evidence` dispatch in `main`: the new mode, keeping the study CLI unchanged.
- `Missing` exception: an evaluator input not reconstructable for one policy, so the case falls to cited-only or unknown.
- `Case` class (and `Case.approvals`): one round's records plus reconstructed node, config, workflow and provenance; the latest approval per model.
- `_delta`, `_resumed`, `_red_green`, `_pre_existing`, `_deferral`, `_rca`, `_strong`, `_agreement`: one adapter per policy to its public evaluator (A2's table).
- `POLICIES` table: evaluator, disabled form, citation pattern and changed meaning per policy (A1, A2).
- `OFF`, `STAMP`, `EVIDENCE_OUT` constants: an unreachable escalation threshold, the history filing-time pattern, and the CSV columns.
- `_git` helper: stripped git stdout.
- `node_then` (cached): the node at the reviewed commit, including nodes archived since, through the manifest at that commit.
- `reconstruct`: rebuilds commit, node and config from git at the round's time, and records provenance or the reason it failed (A1).
- `node_cases`: one case per review round, with the full record set at that commit, including invalid records that name it.
- `moves_others` guard: a change counts only if no other policy's outcome moves ("Done but wrong" check 2).
- `classify`: changed, unchanged, cited-only or unknown per policy and case.
- `evidence_main`: the argument parser, `cases.csv` and the markdown count table.
- RCA baseline guard in `_rca`: a filed RCA that does not replay makes the case unknown ("Done but wrong" check 1).
- Tests: none (the test file is outside the touch zones).
- Mocks: none.
