# Roadmap brainstorming

For **product managers** who want to widen the option space before committing
to a roadmap, with an LLM doing the generating and the research.

The command is `specy-road brainstorm`. It runs in two modes, and keeping them
apart is the whole design: an agent asked to generate *and* filter in one pass
filters first, and hands back five safe ideas instead of forty.

| Mode | Command | What the agent is asked for |
|------|---------|------------------------------|
| Diverge | `brainstorm start` | Volume. Socratic questioning, named divergence lenses, web research. Ranking is forbidden. |
| Converge | `brainstorm recommend` | Judgement. Clustering, overlap detection, a verdict per idea. New ideas are forbidden. |

Between the two, and after them, the PM triages. Accepting and rejecting is
never the agent's call.

---

## Where the work lives

One file per session: **`work/brainstorm-<slug>.yaml`**. It holds the topic,
the anchor node, and every idea with its triage state.

It is **tracked**, deliberately. The ideas that were rejected are as much a
record of the reasoning as the ones that became roadmap nodes, and a session
six months later should be able to see that something was already considered.

The prompt file next to it (`work/brainstorm-<slug>-prompt.md`) is regenerated
from the session plus the current graph, so it is gitignored.

```mermaid
flowchart LR
    start["brainstorm start"] --> prompt["work/…-prompt.md"]
    prompt --> agent["Agent: questions, ideas, research"]
    agent --> add["brainstorm add-idea"]
    add --> session[("work/brainstorm-SLUG.yaml")]
    session --> rec["brainstorm recommend"]
    rec --> triage["PM: accept / reject / revise"]
    triage --> promote["brainstorm promote"]
    promote --> graph["roadmap/ nodes + planning sheets"]
```

## 1. Diverge

```bash
specy-road brainstorm start --topic "How do we expand payments?" --under M3 --count 30
```

`--under` is the node accepted ideas will hang off; omit it to land at the
roadmap root. `--count` is the floor you are asking the agent to clear —
raising it is the simplest way to push past the first, safest set.

This writes the prompt and prints its path. Hand that file to your coding
agent. It instructs the agent to:

- **Interrogate the question first.** Six Socratic questions about who is
  served, what is assumed rather than known, and what is being treated as
  fixed that is actually a choice. It is told to wait for your answers.
- **Generate without filtering.** Weak and obvious ideas are explicitly
  wanted; the agent is told not to rank, cluster, sequence, estimate, or merge
  similar ideas.
- **Work through named lenses** rather than free-associating: SCAMPER,
  analogous domains, inversion, pre-mortem, constraint removal, and 10x/0.1x.
- **Research with its own web search tool** — competitors, public complaints,
  technology shifts, and incoming regulation — and cite what it found.
- **Stay inside the constitution** and not re-propose work already on the
  roadmap. The prompt inlines the current node list for exactly this reason.

The agent records each idea as it goes:

```bash
specy-road brainstorm add-idea --title "Stored payment vault" \
  --rationale "Cuts PCI scope" --kind feature --effort M \
  --evidence "https://example.com/what-i-found"
```

`--kind` is one of `feature`, `capability`, `risk`, `research`, `experiment`.
Only `--title` is required. `--evidence` repeats.

> **In the PM GUI:** the same prompts run against the model configured in
> Settings, with the chat panel in place of the CLI. Web research there uses
> the Bing endpoint you configure rather than the agent's own tool — see
> [pm-gui-brainstorm.md](pm-gui-brainstorm.md).

## 2. Converge

```bash
specy-road brainstorm recommend
```

Switches the session to `roadmap` mode and writes the convergent prompt over
the ideas already captured. The agent is asked to cluster near-duplicates,
flag overlaps with existing nodes by id, assess each idea against the
constitution, and record a verdict:

```bash
specy-road brainstorm revise B1 --recommendation strong --rationale "Clear demand"
```

Verdicts are `strong`, `consider`, or `park`. Passing only `--recommendation`
leaves the idea's triage status alone — the agent advises, you decide.

## 3. Triage

```bash
specy-road brainstorm list                  # or --json, or --status accepted
specy-road brainstorm accept B1 B4 B9
specy-road brainstorm reject B2
specy-road brainstorm revise B3 --title "Sharpened version"
```

Editing an idea's content marks it `revised`. Once an idea has been promoted
it can no longer be re-triaged: it is a roadmap node, and the node is what you
edit from then on.

## 4. Promote

```bash
specy-road brainstorm promote --dry-run
specy-road brainstorm promote
```

Every accepted, not-yet-promoted idea becomes a node. Promotion goes through
the same path as `specy-road add-node`, so the result is indistinguishable
from a hand-authored node: display id allocated under the anchor, stable
`node_key`, planning sheet scaffolded, chunk and manifest written in one
transaction, and `validate` run over the batch.

The new sheet's `## Intent` is seeded from the idea's rationale and its
`## References` gains the sources the agent cited. Rewrite the Intent once the
slice is properly scoped — the seed is a starting point, not a spec.

Options:

- `--under NODE_ID` overrides the session's anchor for this promotion.
- `--type` is `milestone` by default; `vision`, `phase`, and `task` also work.
  `gate` is refused — a gate is a human hold, not work.
- `--dry-run` prints the ids that would be created and writes nothing.

An unusable anchor is rejected before anything is written, so a bad `--under`
promotes nothing rather than half the list. Afterwards, refresh the generated
files:

```bash
specy-road export && specy-road digest
```

## Several sessions at once

`--slug` is optional when exactly one session is open, and required when more
than one is. `specy-road brainstorm sessions` lists them.

Re-running `start` on an existing session keeps its ideas and regenerates the
prompt against the current graph, which is what you want after promoting a
first batch.

## Where to read next

- [pm-workflow.md](pm-workflow.md) — the rest of the PM day-to-day
- [roadmap-authoring.md](roadmap-authoring.md) — what promotion is writing into
- [pm-gui-brainstorm.md](pm-gui-brainstorm.md) — the same flow in the browser
