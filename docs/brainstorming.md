# Roadmap brainstorming

For **product managers** and **developers** who want to widen the option
space before committing to a roadmap, with an agent doing the generating and
the research.

The command is `specy-road brainstorm`. It runs in four passes, and keeping
them apart is the whole design: an agent asked to generate *and* filter in
one pass filters first, and hands back five safe ideas instead of forty.

| Pass | Command | What the agent is asked for |
|------|---------|------------------------------|
| Diverge | `brainstorm start`, `brainstorm next-round` | Volume. A frame, an allocation grid, then rounds that add only what lies outside the pool so far. Ranking is forbidden. |
| Evidence | `brainstorm evidence` | Sources for the shortlist: a verbatim quote, URL, date and tool per claim, with at least one disconfirming search. |
| Converge | `brainstorm recommend` | Judgement. Clustering, overlap with existing nodes, three independent critics, a verdict per idea that cites something. New ideas are forbidden. |
| Triage, promote | `accept` / `reject` / `park`, `promote` | Nothing. These are the human's. |

The design rests on what the research found about today's models (design
note: [`design-notes/v0-3-1-brainstorm-v2.md`](design-notes/v0-3-1-brainstorm-v2.md)):
model-generated idea pools are **homogeneous** — one long pass mostly buys
duplicates after the first few dozen — and the cheap mechanics that
measurably widen them are regeneration against the visible pool, planned
allocation across directions, personas and constraints, and concept cards in
prose before any form. Named methods (SCAMPER, TRIZ) add little on their own,
so the lenses stay as coverage scaffolding. Agent citations are right 40–80%
of the time, so a URL is not evidence until a quote on the page backs it.

### CLI and PM GUI do the thinking differently

The CLI never calls a model or a search API. It assembles repo context, writes
a prompt, and hands it to **the agent already driving your IDE** — which does
the generating with its own tools: web search, sub-agents, and any
brainstorming or ideation slash commands and skills the IDE offers. The one
network call the CLI can make is `brainstorm verify`, and it asks first.

The **PM GUI** panel runs the same prompt text against its own **configured
LLM** and **configured search provider** (see
[pm-gui-brainstorm.md](pm-gui-brainstorm.md)), because a browser panel has no
IDE agent to lean on. Same session file, same triage, same promotion.

---

## Where the work lives

One file per session: **`work/brainstorm-<slug>.yaml`** (format version 2;
version-1 files still read). It holds the topic, the anchor node, the agreed
frame, the allocation grid, the current round, the lens profile, and every
idea with its provenance, sources, cluster, critics and triage decision.

It is **tracked**, deliberately. The ideas that were rejected — and why — are
as much a record of the reasoning as the ones that became roadmap nodes, and
a session six months later should be able to see that something was already
considered. Fields that are empty are left out of the file so it stays
readable.

The prompt files next to it (`work/brainstorm-<slug>-prompt.md`,
`…-sN-prompt.md`, `…-evidence-prompt.md`) are regenerated from the session
plus the current graph, so they are gitignored.

```mermaid
flowchart LR
    start["brainstorm start"] --> p1["round-1 prompt (+ shards)"]
    p1 --> agent["Agent: frame, allocate, generate"]
    agent --> add["brainstorm add-idea --origin"]
    add --> session[("work/brainstorm-SLUG.yaml")]
    session --> nr["brainstorm next-round"] --> agent
    session --> rec["brainstorm recommend"] --> crit["Agent: cluster, overlap, critics, verdicts"]
    crit --> ev["brainstorm evidence"] --> src["Agent: quote-anchored sources"]
    src --> ver["brainstorm verify (asks first)"]
    ver --> triage["PM: accept / reject --reason / park"]
    triage --> promote["brainstorm promote"] --> graph["roadmap/ nodes + planning sheets"]
```

## 1. Diverge

```bash
specy-road brainstorm start --topic "How do we expand payments?" --under M3 --count 30
```

`--under` is the node accepted ideas will hang off; omit it to land at the
roadmap root. `--count` is the floor per round. `--rounds` (default 2) is
how many diverge rounds you plan; `--profile technical` swaps the lens set
for developer roadmaps (failure modes, operability, migration paths, debt,
dependency risk, platform leverage, security); `--panel N` also writes N
independent shard prompts (below).

This writes the **round-1 prompt** and prints its path. Hand that file to your
coding agent. It instructs the agent to:

- **Interrogate the question first.** Eight Socratic questions — outcome and
  metric, who is served, what is assumed, what was tried, what is treated as
  fixed, and *what would make this the wrong topic*. It waits for answers,
  then **neutralises the frame**: every assertion the PM made becomes a
  question, because questions draw far less agreement-seeking from a model
  than statements do. The agreed frame is recorded:

  ```bash
  specy-road brainstorm frame --answer "outcome=fewer failed payments" --answer "served=SMBs"
  ```

- **Plan the search before generating.** An allocation grid of lenses ×
  directions (user segments, technical layers, business model, risk, a
  competing team's PM), each cell with a quota and a **diversity operator**:
  ordinary personas, random constraints, analogical transfer, low-typicality
  sampling, unoccupied regions. Recorded with `brainstorm frame --allocation`.
- **Generate without filtering.** Concept cards in prose first, a cell at a
  time; then make each idea bolder and more different; then record. Weak and
  obvious ideas are explicitly wanted; no ranking, clustering, sequencing,
  estimating, or merging.
- **Not research and not read the roadmap in round 1.** Both anchor the
  model — early search results to competitors, the node inventory to the
  existing solution space. Research opens in round 2; overlap is checked at
  converge, where it is needed.
- **Stay inside the constitution.** The prompt points at `vision.md` and
  `constitution/` as before.

The agent records each idea as it goes:

```bash
specy-road brainstorm add-idea --title "Stored payment vault" \
  --rationale "Cuts PCI scope" --kind feature --effort M \
  --origin claude-code/claude-opus-5-5/SCAMPER/1 \
  --hypothesis "If we do this, PCI audit cost drops because card data leaves our scope" \
  --assumption "SMBs still pay by card"
```

`--kind` is one of `feature`, `capability`, `risk`, `research`, `experiment`,
`refactor`, `platform`. `--origin` is `harness/model/lens/round[/shard]`, so
acceptance can later be read per lens and per model. Only `--title` is
required.

### Rounds

```bash
specy-road brainstorm next-round --count 15
```

Writes the **round-k prompt**: the titles of everything captured so far, and
an instruction to add only ideas that are not in, and not near, that pool —
with the mechanics that measurably widen a pool (estimate how likely a
typical PM would be to propose each candidate and keep only the unlikely
ones; name the untouched regions and fill them). Web research is now allowed
as a source of ideas, URLs recorded with `--evidence`. Two rounds of twenty
beat one of forty.

### Panel (independent shards)

```bash
specy-road brainstorm start --topic "…" --count 30 --panel 3
```

Also writes `work/brainstorm-<slug>-s1-prompt.md` … `-s3-prompt.md`: one
cell each with a distinct operator and direction, and the rule that the
worker must **not** read the other shards, the session file, or the roadmap
before it finishes — workers that see each other converge. Run them as
sub-agents of your session or on other harnesses from the roster (the best
measured gains come from different *model families*); each records with
`--origin …/1/sN` into the same session file, and converge clusters the
merge. specy-road does not launch them itself.

## 2. Converge

```bash
specy-road brainstorm recommend
```

Switches the session to `roadmap` mode and writes the convergent prompt over
the ideas already captured, with the roadmap inventory inlined for the
overlap check. The agent is asked to cluster near-duplicates (singletons are
clusters of one; outliers are never hidden), flag overlaps with existing
nodes by id **and relation** (same problem/same solution, same
problem/different solution, prerequisite, superseded, adjacent), assess
each idea against the constitution, play three **independent critics**
(value, feasibility, evidence and constitution) without reconciling them,
and record a verdict whose rationale cites a clause, a source, or an overlap:

```bash
specy-road brainstorm revise B1 --cluster C2 --overlap M3.1:adjacent \
  --critic "feasibility: needs the billing migration first" \
  --recommendation strong --rationale "Principle 3; source on B1"
```

Verdicts are `strong`, `consider`, or `park`. Passing only `--recommendation`
leaves the idea's triage status alone — the agent advises, you decide.

## 3. Evidence

```bash
specy-road brainstorm evidence            # the strong/consider shortlist
specy-road brainstorm evidence B4 B9      # or named ideas
```

Writes `work/brainstorm-<slug>-evidence-prompt.md`: for each idea, one to
three sources and at least one search that could disconfirm it, using the
strongest research capability the session exposes (and never claiming a
named research product that is not a tool). Each source needs a **verbatim
quote**, the claim it bears on, a stance, the retrieval tool and date:

```bash
specy-road brainstorm add-evidence B4 --url "https://…" \
  --quote "exact text from the page" --supports "SMBs ask for pay-by-link" \
  --stance for --tool "claude WebFetch" --source-type customer-report
```

Then check them:

```bash
specy-road brainstorm verify
```

`verify` lists the URLs and **asks before fetching** (`--yes` for scripts;
without a terminal and without `--yes` it fetches nothing). It fetches
public `https` pages only, with a timeout and a size cap, and records
`retrieved` (quote found), `not-found` (page read, quote absent), or
`blocked` (paywall, robots, transport error — never "fabricated"). Sources
it did not fetch stay `unverified`. This is the only network call the CLI
makes.

## 4. Triage

```bash
specy-road brainstorm list --by cluster       # cluster-first; verdicts hidden
specy-road brainstorm list --show-verdicts    # or --json, --status accepted
specy-road brainstorm accept B1 B4 B9
specy-road brainstorm reject B2 --reason "duplicates M3.1"
specy-road brainstorm park B7 --reason "after billing" --revisit-when "billing ships"
```

Verdicts are hidden by default so they do not steer you; clusters, critics'
objections and evidence show first. `reject` requires a reason; `park` takes
a revisit condition. Both are recorded as the idea's decision. Editing an
idea's content marks it `revised`. Once an idea has been promoted it can no
longer be re-triaged: it is a roadmap node, and the node is what you edit.

## 5. Promote

```bash
specy-road brainstorm promote --dry-run
specy-road brainstorm promote
```

Every accepted, not-yet-promoted idea becomes a node through the same path as
`specy-road add-node`: display id under the anchor, stable `node_key`,
planning sheet scaffolded, chunk and manifest written in one transaction, and
`validate` run over the batch.

The new sheet's `## Intent` is seeded from the idea's rationale; its
`## References` gains the sources (with quote and verification state), the
hypothesis and assumptions, and the cluster's rejected or parked siblings as
"alternatives considered" with their reasons. Rewrite the Intent once the
slice is properly scoped — the seed is a starting point, not a spec.

Options: `--under NODE_ID` overrides the anchor; `--type` is `milestone` by
default (`vision`, `phase`, `task` also work; `gate` is refused — a gate is a
human hold, not work); `--dry-run` writes nothing. An unusable anchor is
rejected before anything is written. Afterwards:

```bash
specy-road export && specy-road digest
```

## Several sessions at once

`--slug` is optional when exactly one session is open, and required when more
than one is. `specy-road brainstorm sessions` lists them. Re-running `start`
on an existing session keeps its ideas, frame and round and regenerates the
prompt against the current graph.

## Checking it works for you

The design is evidence-based but the evidence is from other tasks and older
models; the design note lists the experiments worth running on your own
repo (regeneration rounds against one long pass, evidence verification rates,
roadmap-anchoring, a cross-family panel, cluster-first triage time). The
session file carries what they need: `origin` per idea, `cluster_id`, and
`verification` per source.

## Where to read next

- [pm-workflow.md](pm-workflow.md) — the rest of the PM day-to-day
- [roadmap-authoring.md](roadmap-authoring.md) — what promotion is writing into
- [pm-gui-brainstorm.md](pm-gui-brainstorm.md) — the same flow in the browser
- [orchestration.md](orchestration.md) — the roster a panel can draw on
