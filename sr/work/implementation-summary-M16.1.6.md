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

## Fix round 2 (gpt-5.6-sol-high at c82a93b6)

- **Date-only rounds (A1).** The failing input class is a filing time known only as an interval, which round 1's end-of-day rule treated as an exact instant. One rule now replaces that rule (`filed_at` and `reconstruct`). A history stamp is exact. A record known only by its local `date` spans that day in any time zone (UTC-12 to UTC+14), starting no earlier than the reviewed commit's committer time. Such a round is replayable only if no first-parent integration commit inside the span changed `orchestration.yaml` or `git-workflow.yaml`. Otherwise it is cited-only or unknown. A record dated before its own commit is a problem too. M3.10 `68e79afa8d32` is now unknown ("the config changed between … the filing interval"), and so are all 44 date-only rounds.
- **Complete gate outcome (A2).** The failing class is an evaluator compared alone, without the gate's other conditions (routing, roster identity, family count). The fix is a design change, not a delta patch. Each gate policy (delta, resumed delta, red-green, pre-existing, deferral, strong review) is now confirmed through `review_gate.evaluate_gate`. The gate replays in a `Sandbox`: a throwaway `git clone --shared` with no remote, at the case's integration commit, on the branch its `git-workflow.yaml` names. It runs once with the configured policy and once with only the selected policy disabled, either as keys committed into `orchestration.yaml` or as files left out (PRE-EXISTING.md, DEFERRAL-*). The evaluator now only screens. RCA escalation and agreement have no GateResult field, so their evaluator is their outcome. delta drops from 11 to 5, and the 6 dropped rounds match the reviewer's count.
- **Public-command regression tests: still blocked, outside the touch zones.** Both test findings need `tests/test_review_effort_study.py`. The roadmap still zones only `scripts/review_effort_study.py` and the sheet. This is the second round asking for it. **Coordinator:** add `tests/test_review_effort_study.py` to M16.1.6's touch zones. The tests the reviewer asks for are:
  - (a) a temporary repo whose orchestration.yaml changes on the integration branch within a live record's `date` day, where `policy-evidence` must report that case `unknown`;
  - (b) a delta approval from a roster entry the gate refuses for another reason (for example, unpinned routing under `reviewers_distinct_families`), where `policy-evidence` must report delta `unchanged`.

## Probes

- Date-only cases: all 44 rounds with a date-only record now fail the stability rule and are unknown; none is replayable (`cases.csv`).
- M3.10 `68e79afa8d32`: unknown; its filing span 2026-10-29T05:41:32Z..11:59:59Z contains a config commit.
- The stamped rounds are unaffected by the interval rule: 828 have full provenance, the same as before the live records were added.
- Where else a filing time is used: only `reconstruct` and `Sandbox._fill` (which copies history up to the span's end); both go through `filed_at`.
- A record dated before its commit (lo > hi) is reported as a problem, never replayed.
- The gate-outcome class covers all six gate policies through `evaluate_gate`, not delta alone. In the full run only delta had candidate cases; its screen candidates went from 11 to 5 changed.
- The 6 dropped delta rounds (M11.19, M11.24, M11.60, M11.65, M8.3, M8.7): the sandbox gate has the same approvals and blocks in both runs (checked by hand for M11.19, M11.24 and M8.3).
- Sandbox sanity: for M15.27 round 7, the on-run counts the cursor delta approval and the off-run does not.
- A sandbox gate with a config error raises Missing (not replayable) rather than reading as unchanged; there were none in the full run.
- The sandbox writes only under its temporary directory: a shared clone with no remote, so nothing is pushed or written to the main checkout.
- No reviewers or network: the full run under `env -i PATH=/usr/bin:/bin unshare -rn` took about 3 minutes.
- Round 1's probes still hold: 60 live records join, the agreement defaults are right, and `git_text` is used.

## Acceptance

- **A1:** For each of the eight policies the script reports replayable, cited-only and unknown counts separately. One case is one node_key, commit and round (history order, or `live`) with every record at that commit. `cases.csv` lists each case's provenance: the record count, the filing time and how it was found, and the integration commit the configs were read from. A replayable case is evaluated once with the configured policy and once with only the selected policy disabled.
- **A2:** Each policy's public evaluator screens for a change, as the sheet's table lists. For a gate policy, the change must also show in the complete `evaluate_gate` outcome with every other condition unchanged. For RCA only the onset of an escalation counts, and a next-step change alone is not counted. A change counts only if no other policy's evaluator moves when this one is disabled.
- **A3:** The counts are in the sheet: 872 cases, 828 replayable; delta changed 5 and RCA 62. The recommendation is keep all eight. Unused or unknown is not a reason to remove a policy.
- **A4 (human):** I left the decision table empty.
- **A5:** No package code changed.
- **A6 (informational):** The script grew by about +418 lines, against the +120 estimate: eight evaluator adapters, archived-node reconstruction, the cross-policy guard, the filing-interval rule and the gate sandbox. `scripts/lean_metrics.py` does not exist yet.

## Touch zones

`scripts/review_effort_study.py` and this leaf's planning sheet. `tests/test_review_effort_study.py` is needed and outside the zones (see above). `Case` is a plain class rather than a dataclass, because that test loads the script without registering it in `sys.modules`. The script is 602 lines, within the file-limits cap.

## Verification

- `python -m pytest -q -p no:cacheprovider tests/test_review_effort_study.py tests/parity/review_gate`
- `ruff check specy_road tests scripts`
- `specy-road file-limits`
- `specy-road validate`: exit 0
- `python scripts/review_effort_study.py policy-evidence -o /tmp/pe`: the full count, about 3 minutes

## Added

- `policy-evidence` dispatch in `main`: the new mode, leaving the study CLI unchanged.
- `Missing` exception: an evaluator input that cannot be reconstructed for one policy, so the case falls to cited-only or unknown.
- `Case` class, with `approvals`, `has_orchestration`, `rev` and `day`: one round's records plus the reconstructed node, config, workflow and provenance.
- `_delta`, `_resumed`, `_red_green`, `_pre_existing`, `_deferral`, `_rca`, `_strong`, `_agreement`: one adapter per policy to its public evaluator (A2's table).
- `_rca` round-0 branch: a live-only commit is never a round the RCA rule counts.
- `_agreement` absent-file and absent-flag defaults: the defaults `review_gate_agreement` and `git_workflow_config` document (fix round 1).
- `Policy` class and `POLICIES` table: evaluator, disabled form, citation pattern, what "changed" means, whether it is a gate policy, and the files to withhold.
- `Sandbox` class (`outcome`, `_fill`, `_git`): replays `evaluate_gate` in a throwaway shared clone so a gate policy's change is judged on the complete gate outcome (fix round 2).
- `OFF`, `STAMP`, `EVIDENCE_OUT` constants: an unreachable escalation threshold, the history filing-time pattern, and the CSV columns.
- `filed_at` and `_utc`: the single filing-interval rule (an exact stamp, or the `date` day in any time zone) and its UTC formatting.
- The config-stability check in `reconstruct`: a date-only round is replayable only when no integration commit in its span changed the config (fix round 2).
- `node_then` (cached): the node at the reviewed commit, including nodes archived since, read through the manifest at that commit.
- `reconstruct`: rebuilds commit, node and configs from git at the round's time, recording the provenance or the reason it failed.
- `node_cases` with the `vote` dedupe key: history plus non-duplicated live records, one case per reviewed commit.
- `moves_others` guard: a change counts only if no other policy's outcome moves.
- `classify`: changed, unchanged, cited-only or unknown, per policy and case; it confirms gate policies through the sandbox.
- `evidence_main`: the argument parser, `cases.csv` and the markdown count table.
- Removed: the `_git` helper (replaced by `git_text`).
- Tests: none. The test file is outside the touch zones; the coordinator is asked to add it.
- Mocks: none.
