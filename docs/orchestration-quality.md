# Quality by area

Which areas of a project keep costing extra review, recorded on tracked gate commits and shown in `roadmap-context.md`. Review records and the gate itself: [orchestration-review.md](orchestration-review.md).

## The `Review-tally` trailer

`mark-implementation-reviewed` adds a `Review-tally: <NODE_ID> rounds=<n> blocks=<b> approvals=<a> integrity=<i> rca=<r> findings=<category>:<n>,…` trailer to the leaf's gate commit, after the `Reviewed-by` lines (`specy_road/review_tally.py`). The records it counts are the review history plus every record the passing gate counted, so an interactive human approval (`REVIEW-human.md`, which has no history copy) is a round. A round is one commit, with the latest record per model at it. The trailer records:

- review rounds
- rounds with a blocking record
- approvals the gate counted
- findings per category
- `specy-road integrity` findings between the integration branch's merge base and the approved commit
- RCA escalations (valid RCA records plus one still open)

The gitignored `work/reviews/<ID>/` records are only its source. The digest section and routing below read the trailers from tracked git history.

## The digest section

Every input is tracked, so every checkout and CI get the same bytes for the same `HEAD`:

| Input | Source |
| --- | --- |
| Completed leaves | Each codename whose `chore(rm-<codename>): complete, deregister` commit (written by `finish-this-task`) is reachable from `HEAD`. A node's status is never read, so a leaf approved but not finished is not counted. |
| Order | Gate-commit order: where the leaf's newest `mark implementation reviewed` commit sits in `git log --topo-order --full-history`, newest first. A leaf approved later but finished earlier is still the newer one. A completion with no gate commit sits where its completion commit does. |
| Touch zones | The live graph. For a leaf no longer live (archived), the graph as committed at its completion commit. |
| Tally | The newest `Review-tally` trailer on the codename's gate commit. A completed leaf without one landed before the trailer existed and counts as **no tally**. |
| Policy | `quality_window`, `quality_area_depth` and `quality_threshold` from `roadmap/orchestration.yaml` as committed at `HEAD`. Never the working tree or `orchestration.local.yaml`. |

The window is the last `quality_window` (default 50) completed leaves with touch zones, in that order. An area is the first `quality_area_depth` path components (default 1) of a touch zone, relative to the project root, and a leaf counts once per distinct area. Each area's row shows:

- leaves landed
- leaves with no tally (left out of every rate)
- mean review rounds
- block rate (share of tallied leaves with at least one blocking round)
- integrity findings
- RCA escalations

An area with no tallied leaves shows `—` for its rates. Areas whose block rate exceeds `quality_threshold` (default 0.5) are marked **flagged** and listed first, and ties sort by area name. With no completed leaf there is no section. Nothing in the section depends on the clock.

## Routing (`policy.quality_routing`)

With `policy.quality_routing: true` (default false), `orchestrate plan` adds a `quality_routing (area: <area>)` strong-review item to each ready leaf with a zone that is a flagged area or lies under one. One reviewer from the strong set (every `require_one_of` in `strong_review`) satisfies it. With no strong set, the plan adds a note instead. The review gate does not require the item.
