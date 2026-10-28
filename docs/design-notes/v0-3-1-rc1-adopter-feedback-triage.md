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
| In the nested layout, committed-copy reads (roster and policy from the integration branch, pinned profiles, packet summary, roadmap at a ref) resolved paths from the git root and found nothing; found while running the toolkit's own roadmap | Defect. Reads resolve from the project root (`<ref>:./<path>`) |
| A test suite run inside a delegated worker saw itself as a live worker (the runner's `SPECY_ROAD_WORKER_ID` leaked into guard and presence tests); found dogfooding | Defect. `conftest` clears the variable like `SPECY_ROAD_REPO_ROOT` |
| Pickup and `mark-implementation-reviewed` stashed `work/` (untracked included) around the registry commit; files other sessions wrote during the window were stranded in the shared stash, and a failed restore only warned | Defect. No stash: clean-tree checks ignore `work/`, and registry commits name the registry alone |
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
| A custom `channels.cli` without `{session}` makes `resume` and `message` fall back to the vendor default, changing permissions mid-leaf; Claude's `--session-id` cannot serve resume | Defect | A placeholder that expands to the launch or resume flag, or a separate `cli_resume`; document the harness settings-file route |
| `orchestrate plan` reports "needs a rostered executor with may_process…" when the roster is not on the integration branch yet | Misleading message | Name the ref the roster was read from, and say when the local file is absent there or differs; `validate` warns the same |
| `worker sync` does not flag a gap in event sequence numbers | Gap | Report gaps |
| `session start --path a b` fails; `--path` must be repeated | Wording | Accept several values or say to repeat the flag |
| A worker in a linked worktree under the default permission mode cannot write its READY hand-off, which lives in the main checkout; the adapter passes no `--add-dir` | Defect | `--add-dir` for the hand-off directory on launch |
| `worker reconcile` reports files under a directory touch zone as outside it, and reports the brief as changed when a re-render is identical | Defect | Reuse the packet's boundary match; compare content |
| `handoff status` presents the executor's recorded verify exits as if re-run | Wording | Label as executor-reported |
| `worker sync` truncates a completion's final message, which is where a missing READY is explained | Gap | Show the full message when READY is absent |
| Merge-mode finish pushes the integration branch, including unrelated local commits, with no notice and `--help` suggesting `--push` is needed | Gap | State what will be pushed before acting; document |
| Harness model ids with effort suffixes cannot match a profile, so reviewer prompts carry no model notes | Gap | `launch_model` on the roster entry or profile `aliases` |
| `review-packet -o` writes only the given path; `prompt --role reviewer` then reports no packet | Wording / gap | Write the canonical copy too, or say the packet must be at the default path |
| The reviewer precondition does not say which checkout to check; coordinator bookkeeping in the main checkout makes it report "not landed" | Wording | Name the leaf's worktree; ignore `work/` bookkeeping |
| A stale session of the same user can only be warned about | Gap | `session end <id>` / takeover |
| The cursor adapter's default launch omits `--trust`; untested whether a fresh worktree stalls | Check | Verify; add if needed |
| `validate` advises lowering an honest In Progress parent to Not Started whenever the rollup is coarser | Noise | Warn only when a stored Complete disagrees with the rollup or vice versa |
| `specy-road version` (bare) is an unknown command | Gap | Alias of `--version`; unknown commands exit non-zero |
| Widening a claimed node's touch zones with `edit-node` leaves the registry claim's copy stale, and the packet boundary and finish check read the claim's copy first; no command updates a live claim | Gap (found dogfooding) | `edit-node --set touch_zones` on a claimed node also updates its registry entry, or a `claim update` command |
| In a nested layout an executor whose cwd is the git root wrote `work/implementation-summary-<ID>.md` there instead of under the project root; the prompt gives project-relative paths without naming the root; found dogfooding | Defect | Executor prompt and brief name the project root and give cwd-relative paths |
| The brief's touch-zone section tells the implementer to add or remove zones as needed, while the executor prompt says an out-of-zone change stops the leaf; a worker following the prompt stops where the brief would have let it continue | Contradiction (found dogfooding) | The brief says: propose zone changes in the summary and stop; the executor prompt stays authoritative |

## Feature batch

| Request |
|---|
| `promote` carries clusters, overlaps, critics, the verdict and the frame into sheets, and writes an authoring prompt for the promoted batch |
| Structured promote: per-idea target parent, `--by-cluster`, `--min-recommendation`, or `--plan plan.yaml` |
| Batch `add-idea` / `revise` from a file, applied as one transaction |
| `specy-road apply changes.yaml --dry-run` for graph edits, printing the resulting waves |
| `add-node --acceptance`; display ids accepted for dependencies |
| `brainstorm merge <ID> --into <IDs>` with a `merged` status |
| `brainstorm cluster <CID> --name/--best/--critic`: clusters as objects |
| `finish-this-task --delete-branch` (merge mode) and a `branches prune` command for merged feature branches |
| `add-idea --from-gap` for ideas raised in the converge pass |
| `list-nodes --json` without title truncation; `refresh-stubs --diff` |
| `move-node` rewrites touch-zone path segments equal to an old display id |
| Opt-in auto-pick ordering by `execution_milestone` (Agentic-led first); show the milestone beside the next auto-pick in `--plan` |

## Not acted on

| Finding | Why |
|---|---|
| New phases routed into the first phase's chunk | Not reproduced on the rc1 tag or the WIP (consecutive `add-node --chunk phases/Mn.json` each created its own file) |
| Uncommitted chunk edits after an upgrade | An agent following the touch-zone hint (fixed above), not a command. Attribution of uncommitted edits needs agents to run `session start` |
| `validate` accepts a Complete leaf with open dependencies | Recorded as expected; no change requested |
| `worker delegate` worktrees cannot include separately versioned nested repositories | Out of scope for now: specy-road assumes one git repository per project; supporting nested repositories touches pickup, delegate, reconcile and finish |
