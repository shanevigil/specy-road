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

### Converging loops are not escalated by round count

Counting rounds does not tell a stuck loop from one that is finishing. In
one reported run the blocking findings per round fell 13, 2, 2, 1, 0, every
acceptance item passed from round 2, and round 4 blocked only on a private
test import, yet the loop was escalated ("openai reviewers blocked the last 3
rounds") and an RCA was recommended. So the trend is now a signal
(`specy_road/review_trend.py`):

- **Findings per round:** every item in the four finding categories
  (correctness, regression, boundary, test_integrity) of each blocking record
  at that round, summed across records; plus the acceptance ids it fails.
  There is no severity weighting.
- **Converging:** over the last `escalate_same_acceptance_blocks` rounds since
  the last analysis, the count never rose, fell at least once, and the latest
  round fails no acceptance id. Fewer than that many rounds since the last
  analysis (or a threshold of 1, or a round whose count is unknown) is not
  enough evidence, so the loop is not converging and nothing is deferred:
  with `escalate_review_rounds: 2`, counts 5, 1 still escalate at round 2.
- **Effect:** while converging, the `same_family` and `review_rounds` rules
  do not escalate; `same_acceptance` (which cannot fire while acceptance
  passes), a forced analysis and the fix-round budget (`max_fix_rounds`)
  still apply. `handoff status` prints `findings by round: 13, 2, 2, 1, 0;
  acceptance all pass since round 2`, adds `converging; escalation deferred`
  when a rule was held back, and `--json` carries the per-round list under
  `findings_trend`.
- **Default change:** `policy.escalate_when_converging` defaults to false,
  which changes behaviour for existing projects; set it to true to escalate
  regardless of trend, as before. A flat or rising series still escalates.

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
| any, when findings name new input classes | `defer_findings` (below) |

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
  past finding on that criterion, each with an optional `input_class`;
- `deferred_findings`, required when the action is `defer_findings`: per
  finding its `reviewer`, `commit`, `category`, `acceptance_id`,
  `input_class`, `follow_up_title` and `follow_up_acceptance`.

## Adopted: the fix-round budget and deferral

A loop whose reviewers find a *new* input class every round (deferred leaf
M8.3 ran five blocking rounds from one reviewer that way) only stopped when a
maintainer stopped it by hand. That call is now a recorded step, opt-in per
project:

- **Budget.** `policy.max_fix_rounds` (unset: no budget, nothing changes)
  counts the leaf's blocking rounds. Once spent while a review still blocks,
  `handoff status` reports `fix_round_budget_spent`; the next step comes from
  an ordered state table (`specy_road/review_next_step.py`) keyed on the
  budget, the covering RCA (none, non-defer, unapplied or applied deferral),
  remaining blocks and an available independent analyst or executor. Each row
  yields a command that runs as printed, `blocked` with a human decision, or
  none; later leaves add rows there.
- **Input class.** A short free-text label the analyst writes per finding; it
  is stored, never inferred. Two match when equal after lower-casing and
  collapsing whitespace; there is no fuzzy or semantic matching.
- **The rule.** A finding may be deferred only when its input class matches
  none an RCA record or applied deferral from an earlier round named
  (`deferred_findings` or a disposition's `input_class`), and it is not a
  `correctness` finding on an acceptance id an earlier round marked `pass`. A
  class seen before means the loop is circling, and a regression on a passing
  criterion is this leaf's to fix; neither leaves the leaf. An item's round
  is its blocking commit's, no later than the round the RCA covers, and only
  what was named before that round is evidence.
- **One rule.** `qualify_deferral` holds every rule (round, new input class,
  binding, coverage, protected criteria) and is the only place they live:
  `review defer` calls it before writing, and the gate calls it again on each
  marker every evaluation. Each item binds one to one to a finding of the
  blocking record (same category and text); every finding is bound and every
  failed id named. A record does not tie findings to criteria, so a block with
  a correctness finding that fails an id an earlier round passed is never
  deferred.
- **Applying it.** `specy-road review defer <ID> --rca <record>` is
  human-only (an interactive terminal, no `--yes`). It refuses the whole record
  when any item breaks the rule; otherwise it adds the follow-up leaf beside
  the leaf through the `add-node` write, records a closed `decision` in
  `roadmap/decisions.yaml` naming every deferred finding, the follow-up leaf
  and the approver, and writes `DEFERRAL-<round>.yaml` beside the record, all
  as one transaction that rolls back on any failure.
- **Audit trail and gate.** RCA record → decision entry → follow-up leaf. The
  gate stops counting a block only when a shape-valid marker names its
  reviewer and commit and is in effect (`deferral_in_effect`, the one check
  the gate, the next step and the rework's governing design use): the RCA it
  names is valid, of round and items equal to the marker's; its decision is
  closed, on the leaf, and worded as `review defer` records it, naming each
  item's reviewer, full commit, finding, category, acceptance id and input
  class (the ledger is read only then); and its items still qualify. A marker
  citing another decision, or rewritten after `review defer`, resolves
  nothing; a malformed marker resolves nothing and is reported; another
  reviewer's block, or the same reviewer's on a later commit, still counts.

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
