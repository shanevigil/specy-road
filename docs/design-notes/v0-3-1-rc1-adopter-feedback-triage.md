# Triage: `v0.3.1-rc1` adopter feedback

> **Outcome (open):** the upgrade-path defects and the touch-zone regression are
> fixed on `WIP/improvements-0-3-1`; the rows marked **pre-final** are still to
> do before `0.3.1`, and the rows marked **feature** wait for the next batch.
> Each row was checked against the code (rc1 tag or the WIP tip) before it was
> classified. Version numbers are the maintainer's call; nothing here proposes one.

Findings are stated as specy-road behaviour only. Adopters' repositories, names
and data are deliberately not recorded here.

## Fixed on the WIP

| Finding | Verdict and fix |
|---|---|
| `refresh-stubs` printed "nothing to refresh" without a stub pack, so `AGENTS.md` and the `.gitignore` block were never written while `validate` kept asking for it | Defect. Blocks are applied with or without a pack; no manifest is created |
| The `AGENTS.md` warning offered `init project --force`, which overwrites the scaffold | Defect. Warning names `refresh-stubs` only; `init project --force` keeps `.gitignore` |
| First `validate` after an upgrade left `?? .specyrd/` | Defect. `.specyrd/cache/` carries its own `.gitignore` |
| `validate` reported stub skew in a repo with no pack (0.2.x `init project` recorded a version) | Defect. No skew without packs |
| No single upgrade path; pre-0.3 `*/commands/` stubs left behind | `specy-road upgrade [--dry-run] [--prune]`; `refresh-stubs --prune` |
| 0.3 `work/` run-time paths needed hand-editing `.gitignore` | Added to the managed `.gitignore` block |
| `edit-node --set acceptance=a\|b` stored one criterion | Defect. Repeated `--set` appends; `--set` help; `validate` warns on `\|` |
| Skills cited `docs/*.md` files consumers do not have | Rendered as links to the toolkit docs at the installed version's tag |
| Docs offered `sync` as a refresh without saying it fast-forwards | Docs corrected |
| Bootstrap prompt asked for a second load order beside the managed block | Prompt corrected |
| CI wanted a strict mode | `validate --strict` |
| Scaffold M1.1 had no acceptance, so a fresh project warned (and failed `--strict`) | Sample is now the project's setup task with five criteria |
| Touch zones on Not Started nodes reported as "match nothing"; agents followed the "fix" hint and replaced such zones with planning-sheet paths. A WIP hint recommended the same | Defect, and a WIP regression. Not Started nodes are not checked; the hint says to correct only typos or moved paths |

## Pre-final (to do before `0.3.1`)

| Finding | Verdict | Planned change |
|---|---|---|
| Promoted and scaffolded leaves keep placeholder sheets, pass `validate`, and are pickable; `grind-session` would implement from one paragraph | Defect | Pickup and `grind-session` refuse a leaf whose sheet still has `promote`'s or `scaffold-planning`'s placeholder text and no `acceptance`; `validate` lists them once |
| `handoff status` calls review records "leftover" and advises `do-next-available-task` (which pushes) where claims are never pushed | Defect | When records exist, say so and point to `--ref <branch>` and `do-next-available-task --local` |
| Docs do not say where the gate reads review records from | Doc gap | Working tree, untracked by design; policy from the integration branch; approvals persist as `Reviewed-by` trailers |
| The first `edit-node` on a hand-authored chunk reorders every node | Working as designed (canonical key order), undocumented | Document it; offer a deliberate one-time normalisation |
| `--panel` shard cells come from the shard index, not the recorded allocation; shard prompts predate the frame | Defect | Derive cells from the allocation; carry the frame into shard prompts |
| Prompts list "`roadmap-context.md` _(missing)_" | Defect | Omit the line or say to run `digest` |
| Missing-acceptance warnings cap at 10 with no way to see all | Gap | `validate --all` (or JSON) |
| No way to mark an idea realized by a hand-built node; `--why` is stored as `verdict_why` | Gap | `brainstorm realize <IDEA> --node <ID>`; help names the field; `--append-why` |
| Running version differs silently from the repo's declared pin | Gap | One warning when a declared pin differs |
| Load order says read the digest first; brainstorm round 1 says the roadmap must not be read | Defect | Skill and block: run `brainstorm start` before reading anything |
| Brainstorm step 1 waits on eight open questions | Gap | Agent proposes an answer per question and marks covered ones "assumed"; `frame --provisional` / `--confirm` |
| No next-step hints; evidence and `verify` never reached | Gap | Hints in order; `promote` warns on strong verdicts resting on unverified evidence |
| No per-status counts; `--reason` rules inconsistent | Gap | `list --summary`; consistent `--reason` help |
| `accept A B …` prints `[ok]` per id, then saves nothing if a later id is bad | Defect | Check every id before applying or printing |
| "AGENTS.md has a section from another version" when only the content differs | Wording | Say the section differs from what this version writes |
| `promote` re-runs validation per node (warnings repeated) and derives sentence-length codenames | Defect | Validate once; cap derived codenames |

## Feature batch

| Request |
|---|
| `promote` carries clusters, overlaps, critics, the verdict and the frame into sheets, and writes an authoring prompt for the promoted batch |
| Structured promote: per-idea target parent, `--by-cluster`, `--min-recommendation`, or `--plan plan.yaml` |
| Batch `add-idea` / `revise` from a file, applied as one transaction |
| `specy-road apply changes.yaml --dry-run` for graph edits, printing the resulting waves |
| `add-node --acceptance`; display ids accepted for dependencies |
| `brainstorm merge <ID> --into <IDs>` with a `merged` status |
| `add-idea --from-gap` for ideas raised in the converge pass |
| `list-nodes --json` without title truncation; `refresh-stubs --diff` |
| `move-node` rewrites touch-zone path segments equal to an old display id |

## Not acted on

| Finding | Why |
|---|---|
| New phases routed into the first phase's chunk | Not reproduced on the rc1 tag or the WIP (consecutive `add-node --chunk phases/Mn.json` each created its own file) |
| Uncommitted chunk edits after an upgrade | An agent following the touch-zone hint (fixed above), not a command. Attribution of uncommitted edits needs agents to run `session start` |
| `validate` accepts a Complete leaf with open dependencies | Recorded as expected; no change requested |
