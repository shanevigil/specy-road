# Quality by area

Which areas of a project keep costing extra review, recorded on tracked gate commits and shown in `roadmap-context.md`. Review records and the gate itself: [orchestration-review.md](orchestration-review.md).

## The `Review-tally` trailer

`mark-implementation-reviewed` adds a `Review-tally: <NODE_ID> rounds=<n> blocks=<b> integrity=<i> rca=<r> findings=<category>:<n>,…` trailer to the leaf's gate commit (`specy_road/review_tally.py`): its review rounds, rounds with a blocking record, findings per category over the latest record per model each round, `specy-road integrity` findings between the integration branch's merge base and the approved commit, and RCA escalations (valid RCA records plus one still open). The gitignored `work/reviews/<ID>/` records are only its source; the digest section and routing below read the trailers from tracked git history, so every checkout and CI get the same numbers.

## The digest section

`roadmap-context.md` gains a "Quality by area" section once a leaf in the window carries a tally. An area is the first `quality_area_depth` path components (default 1) of a touch zone, relative to the project root; a leaf counts once per distinct area. The window is the last `quality_window` (default 50) distinct leaves with a gate commit, in `git log --topo-order` order from HEAD, that are leaves of the live graph with touch zones. Per area it lists leaves landed, leaves with no tally (landed before the trailer existed; left out of every rate), mean review rounds, block rate (share of tallied leaves with at least one blocking round), integrity findings and RCA escalations. Areas whose block rate exceeds `quality_threshold` (default 0.5) are marked **flagged** and listed first; ties sort by area name. No gate commit with a tally prints no section, and nothing in it depends on the clock.

## Routing (`policy.quality_routing`)

With `policy.quality_routing: true` (default false), `orchestrate plan` adds a `quality_routing (area: <area>)` strong-review item to each ready leaf whose zones fall in a flagged area, satisfied by one reviewer from the strong set (every `require_one_of` in `strong_review`); with no strong set it adds a note instead. The review gate does not require it.
