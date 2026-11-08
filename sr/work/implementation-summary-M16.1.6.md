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

## Fix round 3 (gpt-5.6-sol-high at f968a7c0)

This round keeps the interrupted worker's commit `bb0b5e4f`, which already held the design change. On top of it, this round updates the docstring, the sheet and the counts.

- **R1: a pre-check re-applied gate conditions (A2).** The failing class is a pre-check that re-derives a gate condition, such as approver eligibility, applicable zones, delta claims, PRE-EXISTING claims at the READY commit, or which deferral marker is in effect. When the pre-check decided "no change", `classify` returned `unchanged` and the complete gate never ran. An ineligible required-model approval for strong review was the instance the reviewer named, but `_delta` (`delta_problem`), `_resumed` (`fresh_session_problem`), `_pre_existing` (`gate_problems` and READY lookup) and `_deferral` (`deferral_in_effect`) had the same shape. The fix removes the class: a gate policy (`evaluate is None`) is now judged by `Sandbox.outcome` alone. Its `reads` predicate only says whether the case holds an input the policy reads at all, and it returns `True` whenever it might, so a `False` can never hide a change. `moves_others` now compares only the non-gate evaluators (RCA escalation, agreement), because a gate run changes only the selected policy's keys or files. `Sandbox._fill` also copies `RED-GREEN.md`, so red-green with the key on is replayed through the gate instead of being refused.
- **Docs.** The module docstring and the sheet's method paragraph and evaluator table now describe gate-only judgement.
- **Recount.** 874 cases from 310 nodes, 830 replayable. delta changed 5 (the same five rounds), RCA escalation 63 (one new round filed today), all others 0. pre-existing went from 825 replayable / 5 cited-only to 830 / 2. Its three claiming rounds used to raise `Missing` for the missing PRE-EXISTING.md. They now replay through the gate, which with no file shows no change.
- **R2: blocked, outside the touch zones (third round asking).** The public `policy-evidence` regression test belongs in `tests/test_review_effort_study.py`. The roadmap still zones only `scripts/review_effort_study.py` and the sheet, and the coordinator's instruction for this round is to stay inside them. The reviewer's own record ("Limits") names adding that file to the zones as coordinator work. **Coordinator:** add `tests/test_review_effort_study.py` to M16.1.6's zones. The test needs a temporary repo with `strong_review: [{zones: ['**'], require_one_of: [X]}]`, an approve record from X where X is gate-ineligible (for example, not in the roster or in the implementer's family), and an assertion that `cases.csv` reports strong review `changed`. The in-process probe below shows `classify` reaching that verdict.

## Probes

- R1 class, every gate policy: `POLICIES` lists delta, resumed delta, red-green, pre-existing, deferral and strong review with `evaluate=None`, so `classify` takes the sandbox path for each. Only RCA escalation and agreement keep their own evaluator.
- R1 class, the predicates: none of `_delta`, `_resumed`, `_red_green`, `_pre_existing`, `_deferral` or `_strong` calls a gate function. They read only the policy key, the record fields, or whether a file is in `work/reviews/<ID>/`, the same directory `Sandbox._fill` copies from.
- R1 instance: an in-process probe (the script loaded with importlib, and a stub sandbox whose outcome lists an unmet item only when the policy is on). With `strong_review` naming an approver the gate would refuse, `classify` returns `changed` after 2 sandbox runs. With no items, it returns `unchanged` after 0 runs.
- The screen against defaults: the screen reads `case.config["policy"]`, which `reconstruct` fills from `DEFAULT_POLICY`. `red_green`, `reviewer_resumed_delta` and `strong_review` default to off or empty, so a `False` screen means the gate would not apply them either.
- `moves_others` after the change: it compares only `_rca` and `_agreement`, which read only their own keys and files, so disabling a gate policy cannot move them. No count changed because of it.
- Full recount: run under `PATH=/usr/bin:/bin unshare -rn` (no reviewer CLI, no network) in 2m44s. The delta-changed rounds are the same five (M15.22 r4, M15.27 r7, M15.35 r2, M21.3 r3, M22.47 r2).

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
- **A2:** A gate policy is judged by the complete `evaluate_gate` outcome alone, with every other condition unchanged. A screen skips only cases that hold no input the policy reads. RCA escalation and agreement use their own public evaluators, as the sheet's table lists. For RCA only the onset of an escalation counts, and a next-step change alone is not counted. A non-gate change counts only if no other non-gate evaluator moves.
- **A3:** The counts are in the sheet: 874 cases, 830 replayable; delta changed 5 and RCA 63. The recommendation is keep all eight. Unused or unknown is not a reason to remove a policy.
- **A4 (human):** I left the decision table empty.
- **A5:** No package code changed.
- **A6 (informational):** The script grew by about +407 lines, against the +120 estimate: eight evaluator adapters, archived-node reconstruction, the cross-policy guard, the filing-interval rule and the gate sandbox. `scripts/lean_metrics.py` does not exist yet.

## Touch zones

`scripts/review_effort_study.py` and this leaf's planning sheet. `tests/test_review_effort_study.py` is needed and outside the zones (see above). `Case` is a plain class rather than a dataclass, because that test loads the script without registering it in `sys.modules`. The script is 591 lines, within the file-limits cap.

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
- `_delta`, `_resumed`, `_red_green`, `_pre_existing`, `_deferral`, `_strong`: input-presence screens for the gate policies, which never re-derive a gate condition (fix round 3, R1). `_rca` and `_agreement`: the two non-gate evaluators.
- `_rca` round-0 branch: a live-only commit is never a round the RCA rule counts.
- `_agreement` absent-file and absent-flag defaults: the defaults `review_gate_agreement` and `git_workflow_config` document (fix round 1).
- `Policy` class and `POLICIES` table: the `reads` screen, the disabled form, the citation pattern, what "changed" means, the own `evaluate` (non-gate policies only), and the files to withhold.
- `RED-GREEN.md` in `Sandbox._fill`'s copied files: red-green with the key on replays through the gate (fix round 3).
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
- Removed (fix round 3): the gate-condition calls in the gate-policy adapters (`delta_problem`, `fresh_session_problem`, `gate_problems`, `deferral_in_effect`, `applicable_items`) and the `Missing` raise for red-green on.
- Tests: none. The test file is outside the touch zones; the coordinator is asked to add it (R2).
- Mocks: none.
