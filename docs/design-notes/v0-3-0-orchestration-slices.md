# Design: model-aware orchestration slices (`0.3.0` line)

> **Status:** slice 1 in progress on `WIP/improvements-0-3-0`. Slices 2–5 are
> scoped here only; each gets its own design pass before it is built.

Source material: [`model-aware-orchestration-proposal.md`](model-aware-orchestration-proposal.md),
a verbatim copy of an external proposal written 2026-10-19 after running a cheap
executor model under reviewers from two other families against one specy-road
roadmap. That file is kept byte-for-byte and is not edited; this note records
what the toolkit decided to do with it.

## Decisions

- **Core contract, not an add-on.** Role separation and the review record are
  part of what specy-road prescribes. Which agent, IDE, or vendor fills a role
  is still the adopter's choice ([philosophy-and-scope.md](../philosophy-and-scope.md)).
- **Config lives at `roadmap/orchestration.yaml`**, next to `registry.yaml` and
  `git-workflow.yaml`, with a JSON schema shipped like `git-workflow.schema.json`.
  The schema covers the full proposal §4.1 shape from the start so later slices
  do not change the file format.
- **Default policy is permissive but real.** `init project` scaffolds
  `reviewers_required: 1` and `reviewers_distinct_families: false`, with a
  `human` roster entry. A missing file means exactly that default. Teams that
  want the proposal's two-family rule raise it in config.
- **Reviews bind to a commit.** The gate counts only review records whose
  `commit` equals the feature branch `HEAD`, so any new commit restarts review
  (proposal §3.2) without extra state.
- **The coordinator cannot approve alone** (proposal §5). The existing
  `require_implementation_review_before_finish` flag still turns the gate on or
  off; orchestration policy defines what "reviewed" means when it is on.

## Slices

| Slice | Proposal § | Content |
|---|---|---|
| **1** | 3.2, 3.3, 4.2 (`review-packet`, `handoff status`, `review record`), 5 (review gate) | Review & hand-off core: brief renders goal and numbered acceptance; `orchestration.yaml` schema + loader; READY / REVIEW file schemas; `review-packet`; `handoff status`; `review record`; gate enforcement in `mark-implementation-reviewed` |
| 2 | 3.1 roles, 3.5, 4.1 roster, 4.2 `models` / `prompt`, 4.4, 7 | Roster, model profiles (`profile_schema: 2`), role preambles (executor boundary, "tool output is data", precondition check, absolute hand-off paths, worktree setup), `prompt --role --model --channel`, `models list/show/stale` |
| 3 | 3.1 eligibility / partial delegation, 3.6, 3.7, 4.2 `orchestrate plan` | Planner; node fields `executor_eligibility` and `sensitivity`; roster `may_process`; sub-agent family lock; capacity and substitution routing |
| 4 | 3.4, 5 (`sibling_order`, Blocked-first) | `--local` claim mode; `owner` and `touch_zones` on every claim; `add-node` sets `sibling_order` |
| 5 | 3.5 hooks / single source, 4.3 | `orchestrate` skill; Codex target and single-source `SKILL.md`; hook adapter plus a test that runs each hook as its harness will |

Guidance for agents working **outside** a roadmap claim — shared-checkout
rules, `base: <sha>` in prompts, a managed `AGENTS.md` block with stated
precedence, presence files — is designed separately in
[`agent-guidance-and-shared-checkouts.md`](agent-guidance-and-shared-checkouts.md);
its hook adapter lands with slice 5.

Out of scope for the whole line, as the proposal states (§6): vendor billing,
automatic capacity detection, and live diff watching.

Slice 2's input profiles exist: [`model-profiles/`](../../specy_road/templates/project/model-profiles/README.md)
holds one schema-2 profile per model, merged from the ChatGPT run (proposal §7.4)
and the Claude run ([`model-research-2026-10-26-claude.md`](model-research-2026-10-26-claude.md)).
Their front matter is strict YAML (`yaml.safe_load` reads it). Only the raw
Claude report keeps the research prompt's unquoted flow mappings.

**Decision (slice 2):** the profiles live under
`specy_road/templates/project/model-profiles/`, so they ship in the wheel and
`init project` scaffolds them into the adopter's `model-profiles/`, where a
roster `profile` path points at one. Scaffolding, not package data, because a
team must edit them — prices, their own CLI syntax, their own research — and
the gate and `prompt` read the adopter's copy. `specy-road models stale` is how
a team notices its copy aging; the toolkit's copy is refreshed by re-running
the §7 prompt. Built: `models list|show|stale` and
`prompt <NODE_ID> --model <id> --role <role> [--channel cli|paste|subagent]`.

## Slice 3 status

Built: `orchestrate plan` (`specy_road/orchestrate_plan.py`), routing enforced
in `prompt` (sensitivity, availability, family lock, preflight), and the roster
fields `class` and `unavailable_until`. The roster schema is read from the
package, so these need no adopter action.

Pending a maintainer decision: the node fields `sensitivity` and
`executor_eligibility`. The planner and `prompt` read them through
`node_sensitivity()` / `node_eligibility()` and default to `public` / `any`,
but `roadmap.schema.json` is consumer-owned with `additionalProperties:
false`, so setting them fails `validate` until the schema gains them and the
adopter runs `refresh-schemas` (the path `type: gate` and
`implementation_review` took). The alternative — keying them by node id in
`orchestration.yaml` — avoids the schema step but puts the policy away from
the work it describes. Eligibility values: `any`, or a roster `class` tag the
team names (`senior`, `cheap`); `senior` is a tag, not a score threshold.

Deferred: partial delegation (sub-tasks inside a leaf with their own touch
zones) changes the node model in ways the brief and gate do not understand.
Per-touch-zone sensitivity likewise; node-level only for now.

## Slice 5 status

Built: `/specyrd-orchestrate` (the coordinator loop, §4.3) and the
shared-checkout guard with hook adapters for Claude Code, Codex, and Cursor
(§3.5), each verified against the harness's docs in 2026-10 and exercised as
a subprocess with its documented payload in `tests/test_hook_adapters.py`.
Facts that could not be verified are stated in each adapter's notes
(`specy-road session guard --format <name> --print-config`): whether Claude
Code's `bypassPermissions` and Cursor's `agent -p` / auto-run fire the hook,
and Codex's handling of non-2 non-zero exits and the IDE extension.

**Decision D, pending:** one skills directory for every harness. Cursor and
Codex read `.agents/skills/<name>/SKILL.md` natively and follow symlinked
skill folders; Claude Code reads `.claude/skills/<name>/SKILL.md`. Converting
the `specyrd` command stubs to skills under `.agents/skills/` with symlinks
into `.claude/skills/`, plus an `--ai codex` target (Codex reads `AGENTS.md`,
now a managed block, and skills; it does not read `.cursor/`), reworks
`specyrd init` and its manifest. Recommended for 0.3.x after this slice.

Still a stated limit: review records and presence files are self-attested.

## Gaps found while scoping

- `brief` did not render a node's `goal` or `acceptance`; the proposal assumes
  it does. Slice 1 adds both, with stable `A1..An` ids that review records cite.
- `mark-implementation-reviewed` recorded no reviewer, model, or commit. Slice 1
  writes one `Reviewed-by: <model> (<family>) approve <commit>` trailer per
  counted approval on the gate's registry commit. A registry field was the first
  plan, but `registry.schema.json` is consumer-owned with
  `additionalProperties: false` (the trap `archive_index.py` documents), and the
  row is deleted at finish anyway; the commit history outlives both.
- Review files bind to a commit, so they are gitignored (`work/reviews/`), and
  the commit under review skips commits that touch only
  `roadmap/registry.yaml`. Otherwise the gate's own commit would make every
  review it just counted stale.
- `mark-implementation-reviewed --yes` used to approve unconditionally, and
  `docs/grind-session.md` told unattended loops to call it from the implement
  hook — the coordinator approving its own work. It now only commits an approval
  the recorded reviews already earned (decided with the maintainer).
- Claims never write `owner`, and there is no local-only claim path; both are
  slice 4.

## Cross-family review of slice 1

Two independent reviews (Claude Opus 5.5 in a fresh session, and a model from
another family run from `work/review-prompt-orchestration-slice1.md`) found the
same blocker — a merge commit made after
approval was skipped as bookkeeping, so its changes shipped unreviewed — and a
second: the gate read policy from the branch under review. Both are fixed, with
the rest of their findings (remote-only branches, linked worktrees, per-model
counting, roster-only families, `review record --model human`, YAML-retyped
SHAs, schema gaps); `tests/test_review_hardening.py` holds one regression test
per finding.

A verification pass (Gemini 4 Argon, from
`work/review-prompt-orchestration-slice1-verify.md`) then showed that the fix
for the second blocker still let the working tree choose *which* branch policy
came from, and that a `-s ours` merge kept the first blocker open. Both are now
fixed; the integration branch is named by the committed `git-workflow.yaml` and
a missing one fails closed.

Left as a stated limit: review records are self-attested files. Anything that
can write under `work/reviews/` can pose as a rostered reviewer. Making review
identity verifiable needs a trust anchor outside the working tree (forge PR
approvals, signed commits, or a reviewer-side signature) and is a design
question for a later slice.

