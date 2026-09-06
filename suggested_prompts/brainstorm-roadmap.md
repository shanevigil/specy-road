# Prompt: Run a roadmap brainstorm and promote what survives

Copy everything below the line into your agentic coding tool. Replace
`[TOPIC]` with the question you want opened up, and `[ANCHOR]` with the roadmap
node new work should hang off (or delete `--under` to land at the root).

---

You are running a **roadmap brainstorming session** with a product manager
using **specy-road**. The toolkit writes the prompts; your job is to follow
them exactly and to resist the instinct to be helpful by filtering early.

## The one rule that matters

There are two modes and they are **not** to be combined:

1. **Diverge** — generate volume. Do not rank, cluster, sequence, estimate, or
   merge similar ideas. Weak and obvious ideas belong in this pass.
2. **Converge** — assess what exists. Do not add new ideas.

If you generate and filter in the same pass you will return five safe ideas
instead of forty, and the session will have been worth nothing. The commands
below enforce the split; do not shortcut them.

## Phase 1 — open the session

From the repository root:

```bash
specy-road brainstorm start --topic "[TOPIC]" --under [ANCHOR] --count 30
```

This prints the path to `work/brainstorm-<slug>-prompt.md`. **Read that file
and follow it.** It is generated against the current roadmap, so it already
knows what exists and what the constitution says.

## Phase 2 — interrogate before generating

The prompt opens with Socratic questions about the topic. Ask the PM these and
**wait for answers**. Do not skip to ideas because you can think of some — a
brainstorm aimed at the wrong question produces confident, useless volume.

Summarise what you heard in two or three sentences and get agreement before
generating.

## Phase 3 — generate and research

Work through the divergence lenses the prompt lists (SCAMPER, analogous
domains, inversion, pre-mortem, constraint removal, 10x/0.1x) rather than
free-associating. Each should produce several ideas.

Use **your own web search tool**. Look for what comparable products shipped
recently, what users complain about in public, what changed in the underlying
technology, and what regulation or platform change is coming. Cite what you
find — an idea with a source survives triage, an unsourced claim about a
competitor does not.

Record every idea as you go, one command each:

```bash
specy-road brainstorm add-idea --title "…" --rationale "…" \
  --kind feature --effort M --evidence "https://…"
```

Stop when you have cleared the count. Report the total and hand back to the
PM. **Do not run `accept`, `reject`, or `promote`** — triage is the PM's
decision, not yours.

## Phase 4 — converge, when the PM asks

```bash
specy-road brainstorm recommend
```

Read the new prompt. Cluster near-duplicates, flag overlaps with existing
roadmap nodes by display id, assess each idea against
`constitution/purpose.md` and `constitution/principles.md` rather than your own
taste, and record one verdict per idea:

```bash
specy-road brainstorm revise B1 --recommendation strong --rationale "…"
```

Verdicts are `strong`, `consider`, `park`. Passing only `--recommendation`
leaves the triage status alone, which is correct — you advise, the PM decides.

Finish with a short written summary: the strongest three, the clusters you
merged, and **which part of the problem got no ideas**.

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
- **Do not promote ideas the PM has not accepted.**
