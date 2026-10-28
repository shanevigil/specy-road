# Prompt: Run a roadmap brainstorm and promote what survives

Copy everything below the line into your agentic coding tool. Replace
`[TOPIC]` with the question you want opened up, and `[ANCHOR]` with the roadmap
node new work should hang off (or delete `--under` to land at the root).

---

You are running a **roadmap brainstorming session** with a product manager
using **specy-road**. The toolkit writes the prompts; your job is to follow
them exactly and to resist the instinct to be helpful by filtering early.

## The one rule that matters

There are separate passes and they are **not** to be combined:

1. **Diverge** (in rounds) — generate volume. Do not rank, cluster, sequence,
   estimate, or merge similar ideas. Weak and obvious ideas belong here.
2. **Converge** — assess what exists. Do not add new ideas.
3. **Evidence** — source the shortlist with verbatim quotes. Do not add ideas.

If you generate and filter in the same pass you will return five safe ideas
instead of forty, and the session will have been worth nothing. The commands
below enforce the split; do not shortcut them.

## What you may write

Until the PM runs `promote`, a brainstorm changes **only the session file**,
and only through `specy-road brainstorm frame`, `add-idea`, `add-evidence`
and `revise`. Do **not** edit code, tests or configuration (not even to try
an idea), and do not touch `planning/`, `roadmap/`, `roadmap/registry.yaml`,
`shared/` or `constitution/`; do not write under `work/` except through
those commands. Proposals are not nodes, sheets or claims until the PM
promotes them.

## Phase 1 — open the session

Run this **before reading anything else** — not `roadmap-context.md`, not the
roadmap, not `planning/`, even if AGENTS.md says to read the digest first.
From the repository root:

```bash
specy-road brainstorm start --topic "[TOPIC]" --under [ANCHOR] --count 30
```

This prints the path to `work/brainstorm-<slug>-r1-prompt.md`. **Read that file
and follow it.** It points at the constitution; it deliberately does not show
you the roadmap or ask for research in round 1, because both anchor you. If
`start` warns that you are on the integration branch, brainstorm on the
`chore/brainstorm-<slug>` branch it suggests. Every command prints the next
step.

## Phase 2 — frame before generating

The prompt lists the frame keys (outcome, served, not-the-question,
assumed-vs-known are required; metric, deadline, budget and the rest are
optional). Do not hand the PM a questionnaire: **propose an answer** to each
from what they already said, mark the ones their words cover `assumed`, and
show the whole proposed frame in one message for them to correct. Ask only
about a required key you could not propose. Do not skip framing because you
can think of ideas — a brainstorm aimed at the wrong question produces
confident, useless volume.

Rewrite the PM's assertions as questions, then record the frame with
`specy-road brainstorm frame --answer key=…` (prefix an unconfirmed answer
with `assumed:`).

## Phase 3 — plan, then generate

Write the allocation grid the prompt asks for (lenses × directions, a quota
and a diversity operator per cell) and record it with
`brainstorm frame --allocation "…"`. Then generate a cell at a time as prose
concept cards, make each idea bolder and more different, and only then record:

```bash
specy-road brainstorm add-idea --title "…" --rationale "…" \
  --kind feature --effort M --origin <harness>/<model>/<lens>/1
```

Stop when you have cleared the count. Report the total and hand back to the
PM. **Do not run `accept`, `reject`, or `promote`** — triage is the PM's
decision, not yours.

## Phase 3b — later rounds, when the PM asks

```bash
specy-road brainstorm next-round --count 15
```

Read the new prompt: the pool so far and the rule to add only what is outside
it. From this round you may use **your own web search tool** as a source of
ideas — what comparable products shipped, what users complain about in
public, what changed in the technology, what regulation is coming — citing
URLs with `--evidence`.

## Phase 4 — converge, when the PM asks

```bash
specy-road brainstorm recommend
```

Read the new prompt. Cluster near-duplicates, flag overlaps with existing
roadmap nodes by display id and relation, play the three independent critics
it names, assess each idea against `constitution/purpose.md` and
`constitution/principles.md` rather than your own taste, and record one
verdict per idea whose rationale cites a clause, a source, or an overlap:

```bash
specy-road brainstorm revise B1 --cluster C1 --overlap M3.1:adjacent \
  --critic "feasibility: …" --recommendation strong --why "…"
```

Verdicts are `strong`, `consider`, `park`. Passing only `--recommendation`
leaves the triage status alone, which is correct — you advise, the PM decides.

Finish with a short written summary: the strongest three, the clusters you
merged, and **which part of the problem got no ideas**.

## Phase 4b — evidence, when the PM asks

```bash
specy-road brainstorm evidence
```

For each shortlisted idea find one to three sources and one disconfirming
search, with the strongest research tool this session exposes. Record each
with a **verbatim quote**:

```bash
specy-road brainstorm add-evidence B4 --url "…" --quote "…" --supports "…" --stance for --tool "…"
```

The PM runs `specy-road brainstorm verify`; do not run it yourself.

## Phase 5 — promote (only when the PM says to)

After the PM has accepted ideas:

```bash
specy-road brainstorm promote --dry-run
specy-road brainstorm promote
specy-road export && specy-road digest
```

Promotion writes real nodes through the same path as `add-node`, scaffolds
their planning sheets, and validates. Then verify:

```bash
specy-road validate
specy-road export --check
specy-road digest --check
```

## Authoritative references

- `docs/brainstorming.md` — the full command surface and session format
- `docs/roadmap-authoring.md` — what promotion writes into (node types,
  `node_key` vs display `id`, planning sheets)
- `constitution/purpose.md`, `constitution/principles.md` — what to assess
  ideas against
- `specy-road brainstorm -h` — the parser is the source of truth for flags

## Non-goals

- **Do not hand-edit `work/brainstorm-*.yaml`.** Use the commands; they
  allocate ids and enforce the state machine.
- **Do not hand-edit `roadmap/` JSON to add promoted ideas.** `promote` routes
  chunks and manifest atomically; hand edits break that.
- **Do not register brainstormed work in `roadmap/registry.yaml`.** The
  registry is for active claims on work being implemented, not for proposals.
- **Do not implement an idea during the session.** No code, test, config,
  `planning/` or `shared/` edits until the PM has promoted it and assigned
  the work through the normal roadmap flow.
- **Do not promote ideas the PM has not accepted.**
