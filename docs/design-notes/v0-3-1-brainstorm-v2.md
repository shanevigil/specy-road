# 0.3.1: brainstorm v2 (research reconciled)

**Status:** built 2026-10-27 on `feature/brainstorm-v2` (B1 items 1–10;
`evidence` stays the URL list and structured records live in `sources[]`,
so the GUI and promote paths kept their shape; the skill stub carries the
method and no `references/` files were added). Reconciles external research on IDE-agent
ideation and roadmap planning against the current `specy-road brainstorm`,
and scopes what ships on the `WIP/improvements-0-3-1` line. Decisions marked
*open* wait on the maintainer.

## Inputs

- The research brief (`work/research-prompt-brainstorming.md`, not tracked):
  harness-native ideation, deep-research products, LLM ideation quality,
  PM tooling, human-in-the-loop design, multi-model panels, integration
  mechanics, evaluation.
- The Claude research report (2026-10-27, 68 sources) and the ChatGPT
  deep-research report (2026-10-27, 47 sources); temporary files in the repo
  root, **not committed**. Neither executed anything.
- The current feature: `docs/brainstorming.md`, `docs/pm-gui-brainstorm.md`,
  `specy_road/bundled_scripts/brainstorm_*.py`, the `specyrd-brainstorm` skill.

## What the report finds

1. **The shape is right; diversity is the weak point.** Diverge → converge →
   human triage → promote matches the evidence (LLM self-evaluation is
   unreliable; critics should be diverse). But frontier models are measurably
   homogeneous within and across vendors (NoveltyBench: fewer than three
   distinct answers in ten; "Artificial Hivemind", NeurIPS 2025), so
   `--count 60` from one context mostly buys duplicates after the first few
   dozen.
2. **Prompt mechanics beat named methods.** Measured gains come from cheap
   mechanics: stepwise "list, then make each bolder and more different"
   (pool similarity 0.377 → 0.255, near human groups), **in-context
   regeneration** against the visible pool (the one technique that brought
   three frontier models to roughly human diversity), planned allocation of
   quotas across directions, ordinary-person personas, analogical transfer,
   verbalized sampling. SCAMPER/C-K-style method prompts add little or
   nothing (TRIZ the exception); pasting creativity articles *reduced*
   diversity. The six lenses are worth keeping as **coverage** scaffolding,
   not as the diversity engine.
3. **Agent evidence is unreliable unless checked.** Audited citation accuracy
   of generative search and deep-research agents is 40–80%. A bare URL is not
   verification; a verbatim quote plus URL, date and retrieval tool, checked
   mechanically, is.
4. **The harness layer has converged.** Plan/read-only modes, sub-agents,
   in-agent web search and SKILL.md support exist in Claude Code, Codex,
   Cursor, VS Code Copilot and Gemini CLI. The popular community
   `brainstorming` skill (obra/superpowers) is Socratic requirements
   elicitation for one build, not volume ideation; specy-road's niche
   (roadmap-scoped diverge/converge with evidence) is open, and its skill must
   be named and described narrowly so the two do not collide on auto-trigger.
5. **PM tools put AI on synthesis, not ideation**: clustering feedback,
   linking insights to ideas with citations, drafting specs. A Git-tracked
   roadmap should adopt evidence links and decision records, not scoring
   dashboards or feedback ingestion.
6. **Multi-vendor panels: no evidence they beat one model regenerated**
   against its own pool; cross-vendor spread is modest. Treat as an
   experiment. Diverse *critics* in converge do raise feasibility.
7. **Sycophancy and anchoring are real**: the PM's framing becomes the frame;
   third-person framing cuts sycophancy; an inlined roadmap node list is a
   plausible anchor (untested). Hide the list in early divergence; show it at
   the overlap check.
8. Deep-research products are reachable from an IDE agent only through its
   own search or a user-configured MCP; cost $0.4–7 per task; output needs the
   same verification gate. Nothing for the CLI to call.

## Where the ChatGPT run agrees, and what it adds

Same conclusions on 1–5, 7 and 8, with stronger sources for the shape itself:
a CHI 2026 RCT (N=486, replicated N=640) found question-led, human-led
interaction improved idea quality while preserving diversity and ownership,
and model-led rewriting narrowed both. It adds:

- **Cross-vendor pooling has direct evidence** (Terwiesch et al. 2026,
  product ideas, human-rated): a balanced pool from four model families
  reached set diversity 0.763 against humans' 0.773 and 0.679 for one model
  zero-shot; random ordinary personas 0.757, random functional constraints
  0.735. The Claude run found no such study. Resolution below (B1 item 10):
  an optional, independent panel, not the default.
- **Independence before merge.** Multi-agent ideation collapses diversity
  when agents talk to each other (authority, dense communication, group size;
  ACL 2026). Workers must not see each other until their outputs are frozen;
  no debate during divergence; critics independent until summarised.
- **Format collapses diversity** (EMNLP 2025): structured output shrinks the
  idea space even at high temperature. Let the agent write concept cards in
  prose first and only then normalise into `add-idea` calls.
- **Ask, don't tell** (UK AISI): questions induce far less sycophancy than
  equivalent assertions (~24-point gap). Neutralise the PM's assertions into
  questions before generation.
- **Context increases sycophancy** (CHI 2026, +16–45% with user context) and
  **early suggestions anchor, late ones cause pivots** (IJCAI 2025, N=247):
  the same staged-exposure recipe, with one pre-research branch.
- Overlap should name the **relation**: same problem/same solution, same
  problem/different solution, prerequisite, superseded, adjacent.
- Evidence `verification` states `retrieved | blocked | not-found |
  unverified` (never "fabricated" for a fetch failure); PM tools (JPD,
  Productboard, Linear, ProdPad) make linked evidence first-class and keep
  scoring inputs visible — adopt provenance, not scores.
- Prompt wording for research: "use the strongest web-research capability
  exposed in this session; record which tool; never claim a named research
  product that is not exposed as a tool."
- Blind independent stakeholder triage before disagreements are shown
  (deferred with votes).

Where the two differ: the ChatGPT run puts the evidence sweep (as
observations, not ideas) *before* or alongside divergence; the Claude run
puts it after the shortlist. B3 keeps it after the shortlist for
verification and allows research from round 2 as an idea source: cheaper,
and it avoids the anchoring the ChatGPT run itself warns about.

## Already built, and how it maps

| Report element | What exists | Gap |
| --- | --- | --- |
| Diverge/converge separation, ranking ban, no new ideas in converge | both prompts | none |
| Socratic frame | six questions, answers not recorded | add a topic-challenging question and an outcome question; record answers in the session |
| Lenses | six, run in order | keep as coverage; add analogies and JTBD/persona; quotas per cell |
| Volume | `--count N` in one pass | rounds with regeneration against the pool |
| Constitution and roadmap inlined | both, up front, in diverge | roadmap list moves to converge (anchoring) |
| Research | inside diverge, URL only | separate evidence pass with quote/date/tool; `verify` |
| `add-idea` fields | title, rationale, kind, effort, evidence[str] | origin, cluster, evidence objects, decision record, hypothesis |
| Converge | cluster, overlap by id, constitution check, verdict | critic section; verdicts must cite a clause or evidence id |
| Triage | accept/reject/revise, flat list | `list --by cluster`, `--reason` on reject, `revisit_when` on park |
| Promote | node + sheet seeded from rationale/evidence | carry verified evidence and "alternatives considered" |
| Skill | `specyrd-brainstorm` SKILL.md (shared `.agents/skills`, symlinked for Claude Code) | narrow description; `references/` files |
| GUI | same prompt text, configured LLM + search provider | same data model; the session payload carries the v2 session fields and a reject needs a reason, but the converge pass still captures nothing structured (clusters, overlap, critics, sources from the chat are not persisted) — a known gap, the CLI is the full path |

## Decisions

**B1 (decided 2026-10-27 as recommended) — what ships on 0.3.1.** Recommendation, in order of measured
value per line of code:

1. **Rounds with regeneration.** `brainstorm start --rounds R` (default 2).
   Round 1: allocation grid (lens × direction, quotas summing to `--count`),
   constitution only, no roadmap list, no research. Round k>1
   (`brainstorm next-round`): the prompt shows the titles captured so far and
   demands only ideas outside that pool, with the verbalized-sampling cue
   ("list candidates with the probability a typical PM would propose each;
   add only those under 0.2") and the stepwise "make each bolder" cue.
2. **Delayed roadmap exposure.** Node list leaves the diverge prompt; the
   overlap check happens in converge where it already is.
3. **Evidence pass.** `brainstorm evidence` writes a prompt for shortlisted
   ideas (`strong|consider`, or ids given) asking for one to three sources
   each, at least one disconfirming; `brainstorm add-evidence B7 --url --quote
   --supports --stance for|against [--tool]` records them with
   `retrieved_at`. `brainstorm verify` (see B2) checks them.
4. **Converge additions.** Critic section (strongest objection per cluster,
   different lens; a different model or sub-agent where the roster offers
   one); verdict rationale must cite a constitution clause or an evidence id;
   `cluster_id` written by `revise --cluster`.
5. **Triage.** `list --by cluster`; `reject --reason` required; `park`
   status with `revisit_when`; verdicts hidden by default in the list.
6. **Frame.** Two more Socratic questions; `brainstorm frame --answer` or
   the agent writes `frame:` through `revise-session`; a third-person
   diverge round is one of the allocation directions.
7. **Origin attribution.** `add-idea --origin harness/model/lens/round`,
   filled from the environment where detectable.
8. **Technical profile.** `--profile technical` swaps the lens set (failure
   modes, operability, migration, debt, dependency risk, platform leverage)
   and the default kinds.
9. **Promote** carries verified evidence and the cluster's rejected siblings
   into the sheet's References / "Alternatives considered".
10. **Diversity operators and an optional panel.** The allocation grid draws
    from an operator catalog (ordinary personas, random functional
    constraints, analogical transfer, low-typicality sampling, unoccupied
    regions) with the six lenses kept for coverage. `start --panel N` writes
    N independent shard prompts, each with a distinct operator/persona
    subset and `--origin`, to be run as sub-agents or on other roster
    harnesses *without seeing each other*; the session merges on `add-idea`
    and converge clusters. No launcher of its own: the agent, or later
    `worker delegate`, runs them. Prompts ask for concept cards in prose
    before any `add-idea`, and neutralise the PM's assertions into questions.

Deferred past 0.3.1: per-role votes and blind stakeholder triage,
deep-research MCP hooks, GUI programmatic regeneration, an evaluation
harness beyond the metrics the CLI can print (counts per lens, cluster,
origin, verified-evidence share).

**B2 (decided 2026-10-27: fetch allowed, with the user's approval) — may `verify` fetch URLs?** The standing rule is that the CLI
calls no model and no search API. Fetching a known URL to check that a quote
appears on the page is neither, and the GUI already makes HTTP calls.
Decision: `brainstorm verify` lists the URLs it would fetch and asks for
confirmation before the first network call (`--yes` answers it for scripts;
non-interactive without `--yes` fetches nothing); fetching uses timeouts, a
size cap and the GUI research module's private-address guard. Evidence not
fetched stays `unverified`.

**B3 (decided 2026-10-27 as recommended) — research out of round 1.** The report moves web research out
of divergence entirely (anchoring on first search results, token spend) and
into the evidence pass; the current prompt tells the agent to research in
order to "import ideas not in the room". Recommendation: round 1 generates
without research; from round 2 the prompt allows research as an idea source
again ("what have comparable products shipped"), still recording URLs; the
quote-anchored evidence pass remains where verification happens. Keeps the
import-from-outside value without anchoring the first round.

**B4 — data model** (as built: `evidence` stays a URL list and the
structured records live in a new `sources[]`, so v1 files and the GUI keep
their shape). Session `version` 2, read-compatible with 1. Idea gains
`origin`, `cluster_id`, `sources[]` objects (`url, quote, retrieved_at, tool,
supports, stance, source_type, verification: retrieved|blocked|not-found|unverified`),
`overlap[]` (`node_id, relation`), `critic`, `hypothesis`, `assumptions`,
`decision` (`reason, decided_at, revisit_when`); status gains `parked`.
Session gains `frame`, `allocation`, `round`, `profile`, `panel`. Kinds gain
`refactor`, `platform`.

**B5 — skill package.** The existing `specyrd-brainstorm` SKILL.md gets a
narrow description ("roadmap brainstorm through specy-road; not a design
elicitation skill"), the pass sequence and the rules. As built, the lenses
and the evidence format live in the generated prompts (`brainstorm start`,
`evidence`) rather than in `references/` files, so the skill stays one file.
No per-harness wrappers.

**B6 — GUI parity.** The GUI consumes the same prompt renderers and session
file; its chat loop gets `next-round` and `evidence` as buttons in a later
change, not in this one.

## Where this diverges from the report

- No fan-out of its own (reuse the worker layer), no votes, no deep-research
  integration: smallest change that captures the measured gains.
- Research stays available from round 2 (B3) rather than evidence-pass only.
- `verify` asks before fetching (B2) so the CLI's first network call is always a visible, approved one.

## Verification

Prompt renderers are deterministic, so tests assert the round-1 prompt has
no node list and no research section, round 2 lists the pool and the
regeneration cue, the evidence prompt names only shortlisted ideas, converge
has the critic section; session round-trip for v1 and v2 files; `verify`
with a stub fetcher (quote present / absent / unreachable → true / false /
unchecked); `reject` without `--reason` refused; `list --by cluster` grouping;
promote carries evidence. The report's experiments 1–5 (regeneration vs
single shot, evidence verification rates, anchoring, cross-vendor panel,
triage load) need real harnesses and are listed in `docs/brainstorming.md`
as manual checks, not claimed.
