# Review-loop escalation: root-cause analysis when reviews keep blocking

**Status:** live design (roadmap leaf `M4.17`).

**Sources:** two research runs on the same prompt, kept untracked under the
maintainer's `work/research-reports/`: `openai-review-loop-rca.md` (the
"OpenAI report") and `claude-review-loop-rca.md` (the "Claude report"). This
note is what was adopted from them, and the remaining criteria follow it.

## The problem

An executor and two reviewers can cycle without converging: each round the
executor fixes what was flagged, and the next review blocks again. Every new
commit invalidates both reviews, so a stalled leaf costs a full executor run
plus two reviewer runs per round. The overnight run that prompted this had two
leaves that took 12 and 8 rounds; in both, an acceptance criterion admitted
more than one reasonable reading, and each round's findings named a new input
class on the same criterion.

Trying harder in the same loop does not help. The fix is to stop, diagnose
*why* the loop is stuck, and act on the cause.

## Where the two reports agree

- **Trigger on repetition, not on effort.** Both recommend pausing after **3
  consecutive rounds blocked on the same acceptance id**. The OpenAI report
  calls that a "three strikes" rule and notes that CI retries flaky tests 2–3
  times. The Claude report cites Google's flaky-test rule (report a failure
  only after it fails 3 times in a row), the Debugging Decay Index (most
  debugging value is in the first 2–3 attempts), and the Claude Code team's
  3-round review cap, which cut PRs needing 5+ rounds from 8.9% to 1.5%.
- **A total-rounds backstop.** The OpenAI report puts it at about 5 rounds; the
  Claude report keeps one as a hard stop (at 6, behind earlier triggers this
  note defers).
- **A fixed six-way classification:** specification, implementation, test,
  reviewer, environment, hard problem.
- **An independent analyst.** Neither the executor nor a reviewer on the leaf:
  both are parties to the dispute, models prefer their own output, and
  same-context loops reward-hack. Prefer a family different from theirs.
- **Evidence or it does not count.** Every claim cites a finding, a commit or
  an acceptance id. The analyst returns the cheapest corrective action, and a
  **bounded rewrite of the criterion** when the cause is the specification.
- **A machine-readable record** of trigger, classification, confidence,
  evidence and recommended action, so the next step is mechanical.

Where they differ, this note follows the Claude report on two points. *How the
analyst sees the history*: positions side by side in one prompt (models cave to
a follow-up challenge more readily than to both positions at once), rather than
the OpenAI report's "findings without verdicts". *How the analyst works*: no
debate and no self-critique loop. The Claude report finds that voting captures
what debate adds and that intrinsic self-correction lowers accuracy, so a tool
check decides disputes. The OpenAI report instead ranks self-reflection plus
search (BESTER) first, and calls debate untried.

## Adopted: triggers and signals

The loop's history is every review record filed for the leaf, in filing
order. `specy-road review record` keeps a copy of each record it files under
`work/reviews/<ID>/history/` (the top-level `REVIEW-<model>.md` is overwritten
each round; the gate still reads only those). A **round** is one reviewed
commit object: a short SHA and the full id of that commit are the same round,
and the latest record per model there counts. A round **blocks on** acceptance
id `A<n>` when that record marks `A<n>: fail`.

| Trigger | Rule | Policy key (default) |
| --- | --- | --- |
| `same_acceptance` | the last *N* rounds all block on the same acceptance id | `escalate_same_acceptance_blocks` (3) |
| `review_rounds` | *N* rounds since the last root-cause analysis | `escalate_review_rounds` (5) |

Both are in `roadmap/orchestration.yaml` `policy`, read from the integration
branch like the rest of the gate's policy. The 5-round backstop follows the
OpenAI report and the leaf's acceptance; the Claude report's 6 is the same
idea one round later, and 5 keeps the cost of a stalled loop lower (a false
trigger costs one analysis; a missed one costs a round of three agents).

Counting restarts after each analysis: an RCA record resolves every round up
to the round it names, so a leaf that keeps stalling after a fix escalates
again only after another 3 (same criterion) or 5 (total) rounds.

## Adopted: protocol

1. **Detect.** `handoff status` and `review list` compute the triggers from
   the history on every call. A triggered, unapproved leaf reports
   `escalated` with the trigger named; `review list` prints the same line.
2. **Hold reviews.** Until an RCA record covers the current trigger, every
   `prompt --role reviewer` for the leaf opens with a *Loop escalated* section
   naming the trigger, so a reviewer (and the coordinator queueing it) knows a
   further round is not the next step.
3. **Analyse.** `specy-road prompt <ID> --role rca --model <id>` builds one
   prompt from the brief (with acceptance), every round of the history side by
   side (verdict, failed ids, findings, required changes, notes) and the diffs
   between reviewed commits. The analyst must be a rostered reviewer that
   filed no record on the leaf and is not the READY file's executor. It
   classifies with evidence for and against each class, states a
   counterfactual (which past findings the minimal intervention would have
   prevented), and names the cheapest corrective action. For `specification`
   it writes a bounded rewrite of the criterion and labels every past blocking
   finding on it.
4. **Record.** The analyst writes `work/reviews/<ID>/RCA-<round>.md`, whose
   front matter is validated against `schemas/rca-record.schema.json`. An
   invalid record is reported and resolves nothing.
5. **Act.** A human or the coordinator applies the action. Rewriting an
   acceptance criterion is a roadmap edit and stays human-approved: the record
   proposes it, it never edits the roadmap.

| Classification | Cheapest corrective action (`recommended_action.type`) |
| --- | --- |
| specification | `amend_criterion`, or `split_leaf` when the rewrite would widen scope |
| implementation | `continue_with_class_fix` (fix the whole class at once), or `restart_executor_fresh` |
| test | `fix_tests`, as its own commit |
| reviewer | `change_or_reprompt_reviewer` |
| environment | `fix_environment` (rebase, regenerate the packet, fix touch zones or the base) |
| hard_problem | `escalate_human` |

## Adopted: the record

A trimmed form of the Claude report's Part F (`specy_road/schemas/rca-record.schema.json`):

- `node_id`, `model`, `date`;
- `trigger`: `rule` (`same_acceptance` | `review_rounds`), `acceptance_ids`,
  `round` (the rounds in the history when the prompt was built, which the
  prompt fills in; the record resolves every round up to it, and a `round`
  beyond the history makes the record invalid);
- `classification`: `primary`, optional `secondary`, `confidence` 0–1;
- `evidence`: at least one `{kind, ref, supports, note}`, where `kind` is
  finding, commit, acceptance, signal or check_result;
- `recommended_action`: `type` (table above), `instructions`,
  `requires_human_approval`;
- `criterion_rewrite`, required when the primary class is `specification`:
  `acceptance_id`, `original_text`, `proposed_text`, and a disposition
  (`in_scope_must_fix` | `out_of_scope_now` | `already_resolved`) for each
  past finding on that criterion.

## Deferred

Each is a candidate follow-up leaf once the history has data to calibrate it.

- **More triggers:** verdict oscillation (2 flips), finding novelty
  (embedding similarity below 0.3), pre-existing share (`git blame` on cited
  lines ≥ 50%), required-change reversal, inter-reviewer disagreement,
  severity trend, shrinking fix diffs and cost burn (Claude report S2–S10).
- **Deterministic preflight** before any model runs (packet commit is HEAD,
  touch zones exist, verify passes at the merge base, no conflict with main,
  flake reruns). Today the analyst is asked to consider environment causes
  from the evidence instead.
- **k = 3 sampling with a majority vote**, and the confidence-below-0.6 rule
  that forces `escalate_human`.
- **Tool-grounded confirmation**: the spec-ambiguity oracle probe (independent
  oracles, divergence ≥ 20% confirms a specification cause), reviewer replay,
  failing-test reproduction, bisection.
- **Enforcement**: the gate does not refuse a review while escalated; the
  prompt says so and the status reports it.
- **Retrieval of past RCA records**, outcome fields and the evaluation plan
  (replay of stalled leaves, human gold labels, rounds saved).
