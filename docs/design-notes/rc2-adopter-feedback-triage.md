# Triage: `v0.1.4-rc2` adopter feedback

Assessment of the 14-finding adopter handoff written after running an
autonomous grind against a real consumer repository. Each item is classified as
a **defect**, **working as designed** (documentation gap), or **feature
request**, with the reproduction that decided the call.

Everything below was reproduced against **`specy-road 0.1.4rc2`** in a throwaway
consumer repo created by `specy-road init project`. The full transcript is in
the pull request that introduced this note.

## 0. Version provenance — read this first

Three findings do not match the rc2 code, and all three point the same way:

| Reported | rc2 reality |
|---|---|
| "no `--version` at all" | `specy-road --version` and `specyrd --version` both work. Added in `c1b4002`, and `git tag --contains` lists **only** `v0.1.4-rc2`. |
| "`validate` warns only after the fact (`phase M9 has status Not Started but every descendant is Complete`)" | That warning was deleted in `24c1758`, which is in `v0.1.4-rc1` and `v0.1.4-rc2`. rc2 emits **nothing**. |
| "`add-node` … exit code 0, chunk left invalid" | `add-node` exits **1** and rolls the chunk back. Identical code in `v0.1.3`, `v0.1.4-rc1`, `v0.1.4-rc2`. |

The `--version` gap and the phase warning can only coexist in **`v0.1.3` or
earlier**. The most likely explanation is that the grind ran against a
`v0.1.3`-era install (or an editable checkout predating rc2) rather than the rc2
artifact. Worth confirming with the adopter before we act on anything that
depends on the observed exit code, because it changes one conclusion materially:
**rc2 is worse than what they tested on the silent-phase trap**, since rc2
removed the only warning they got.

None of this makes the substance of the report wrong. Two of the three headline
items are genuine defects; they are just genuine for a different reason than the
report gives.

## 1. Non-atomic writes — genuine defects, both of them

### 1a. `edit-node` saves before validating (the more serious of the two)

[`edit_node_set_pairs`](../../specy_road/bundled_scripts/roadmap_crud_ops.py)
calls `write_json_chunk` and `rename_planning_file_if_path_changed` **before**
`run_validate_raise`. On validation failure it raises, `cmd_edit` prints the
error and exits 1 — and the invalid edit stays on disk. There is no
`AtomicWritePlan` on this path at all, unlike
[`write_with_routing`](../../specy_road/bundled_scripts/roadmap_chunk_router.py).

One failed `edit-node` leaves three changes behind and blocks every later
command:

```
$ specy-road edit-node M1.1 --set "title=First phase — planning and contracts"
error: roadmap: duplicate title 'First phase — planning and contracts' on nodes M1 and M1.1
exit=1
$ git status --short
 D planning/M1.1_first-milestone_….md
 M roadmap/phases/M1.json
?? planning/M1.1_first-phase-planning-and-contracts_….md
$ specy-road validate
roadmap: duplicate title 'First phase — planning and contracts' on nodes M1 and M1.1
exit=1
```

The adopter's account of the consequence is exactly right: with a multi-`--set`
batch, some edits land and some do not, and the only way to find out which is to
read the graph. The planning-file rename makes it worse than they reported — a
failed edit can leave the sheet renamed and the chunk pointing at the old name.

The same function backs the PM GUI (`gui_app_routes_nodes` uses it for
`/api/nodes/edit`, sibling reordering, and node deletion), so this is not
CLI-only.

**Fix:** route `edit_node_set_pairs`, `delete_roadmap_node_hard`, and the
planning-file rename through `AtomicWritePlan`. The planner already snapshots
original bytes and restores them on any exception; it needs a way to stage a
file rename alongside chunk and manifest writes.

### 1b. `add-node` writes the planning sheet outside the transaction

The chunk write **is** atomic and the rollback works. But
[`cmd_add`](../../specy_road/bundled_scripts/roadmap_crud_ops.py) calls
`ensure_planning_sheet_for_new_node` before `append_node_to_chunk`, and that
sheet is never rolled back. Because
[`collect_planning_artifact_errors`](../../specy_road/bundled_scripts/planning_artifacts.py)
treats a sheet with no owning node as fatal, a failed `add-node` leaves the repo
unable to validate:

```
$ specy-road add-node --id M1.2 --parent-id M1 --type gate --title "External gate"
error: roadmap.schema: nodes/2/type: 'gate' is not one of ['vision', 'phase', 'milestone', 'task']
exit=1
$ specy-road validate
roadmap: orphan planning file planning/M1.2_unnamed_….md: no node has planning_dir '…'
exit=1
```

So the report's headline ("writes and exits 0") is not reproducible, but its
prescription ("validate the prospective graph first and refuse to write") is
correct, and the failure mode it describes — a failed `add-node` poisoning the
repo — is real.

**Fix:** stage the planning sheet in the same `AtomicWritePlan` as the chunk, or
unlink it when the write is rejected. The sheet is a net-new file, so
`AtomicWritePlan.new_paths` already handles the unlink semantics.

Note a related hole while we are in here: `validate_at` runs
`auto_heal_roadmap`, which writes to disk, **inside** the planner's `validate()`
callback. Files healed but not staged are outside the snapshot set and survive a
rollback.

**Neither defect has test coverage.** The full suite (609 tests) passes on rc2.

## 2. The silent phase-status trap — genuine defect, and rc2 regressed it

This is the one worth blocking a stable release for.

specy-road has two status models. `rollup_status` (computed in
[`compute_rollup_status`](../../specy_road/bundled_scripts/roadmap_load.py):
a parent is Complete when every leaf descendant is) drives `roadmap.md`,
`brief`, and the PM GUI. Raw own-`status` drives dependency satisfaction:
[`_statuses_by_node_key`](../../specy_road/bundled_scripts/do_next_available.py)
reads `n.get("status")`, never `rollup_status`. `finish-this-task` only flips the
leaf it finished ([`_update_chunk_status`](../../specy_road/bundled_scripts/finish_task.py)).

The result is a graph that reports itself finished while refusing to hand out the
work that depends on it, with no diagnostic anywhere:

```
$ rg '^\| `M1' roadmap.md
| `M1` | First phase — planning and contracts | phase | Human-led | Complete |
$ python3 -c "…"          # M1's own status in the chunk
[('M1', 'Not Started'), ('M1.1', 'Complete')]
$ specy-road validate
OK: roadmap and registry validate.
$ specy-road reconcile-milestone-status
Nothing to reconcile (no milestone_execution rows needing action).
$ specy-road do-next-available-task
No actionable leaf tasks available (before sync).
  blocked by unmet dependencies: M2.1
```

Two things make this worse than the report suggests:

- **`reconcile-milestone-status` is not the escape hatch.** It only considers
  nodes carrying a `milestone_execution` block
  ([`_node_milestone_fields`](../../specy_road/bundled_scripts/reconcile_milestone_status.py)),
  which is written by `start-milestone-session`. In the plain
  `do-next-available-task` → `finish-this-task` loop nothing has one, so it is a
  no-op. There is **no** supported remedy short of a hand-written `edit-node`.
- **rc2 removed the last signal.** `24c1758` deleted the stale-phase warning on
  the grounds that "validation aligns with F-013 rollup" — but only the
  *reporting* side was aligned. Dependency resolution was left on own-status, so
  the change turned a noisy-but-visible trap into a silent one.

**Fix — pick one, not both:**

- **Make dependency satisfaction rollup-aware.** Have `_statuses_by_node_key`
  consult `rollup_status` for non-leaf nodes. This is the smallest change and
  makes one model authoritative, which is the real problem. Risk: a dependency
  on a phase becomes satisfied the moment its last leaf closes, before anyone
  reviews the phase as a whole. If that matters, it is what `type: gate` nodes
  are for.
- **Flip the parent in `finish-this-task`.** When the finished leaf was the last
  non-Complete descendant of a parent, set the parent to Complete (in the same
  bookkeeping commit) or print the exact `edit-node` command. This matches the
  adopter's suggestion and keeps own-status authoritative.

Either way, restore a `validate` warning when a node's own status disagrees with
its rollup. Removing it was the regression.

## 3. Consumer `schemas/` drift — genuine gap, worse than reported

Confirmed: `schemas/` is copied into the consumer repo by `init project` and
never updated. rc2 ships `gate` in the roadmap schema's `type` enum and
`implementation_review*` in the registry schema; a repo scaffolded before those
landed rejects output that current `add-node`, `set-gate-status`, and
`mark-implementation-reviewed` produce.

The reporter hand-copied three files. That was the right call, because the one
command that looks like it would help is destructive:
[`run_init_project`](../../specy_road/init_project.py) skips existing files
**unless** `--force`, and `--force` overwrites *every* template file — including
`roadmap/manifest.json`, `roadmap/phases/M1.json`, `planning/*.md`, `vision.md`,
and `AGENTS.md`. Running `specy-road init project --force` to refresh schemas
would destroy the consumer's roadmap.

**Fix:** a `specy-road refresh-schemas` (or `init project --schemas-only`) that
copies just `schemas/`, plus a `validate` warning when a consumer schema differs
from the bundled one. Independently, `--force` deserves a narrower blast radius
or a louder warning.

## 4. Working as designed, badly documented

### Blocked leaves are offered first

Confirmed. [`_collect_do_next_tiers`](../../specy_road/bundled_scripts/do_next_available.py)
orders `blocked` → MR-rejected → rest, so marking a leaf Blocked promotes it to
top candidate:

```
| `M2.1` | Downstream work | task | — | Not Started |   ← earlier in the outline
| `M2.2` | Later sibling   | task | — | Blocked     |
$ specy-road do-next-available-task
[M2.2] Later sibling
```

The intent is defensible — a Blocked leaf is the thing most worth unblocking —
and it is documented, in exactly one line of the scaffolded
[`AGENTS.md`](../../specy_road/templates/project/AGENTS.md) ("auto-pick follows
outline (tree) order after Blocked/MR-rejected priority"). It is absent from
`do-next-available-task -h` and from `docs/dev-workflow.md`, and the pickup
output never mentions that the leaf it just handed you is Blocked.

**Fix (documentation + one line of output):** say it in `-h`, and print
`status: Blocked` in the pickup banner. The adopter's `externally_blocked`
marker request is a real gap, but `type: gate` as a dependency already covers it
and that is worth documenting prominently before adding a second mechanism.

### The `Human-led` gate is advisory

Confirmed: [`_agentic_execution_ok`](../../specy_road/bundled_scripts/do_next_available.py)
is a documented unconditional `return True`. So `execution_milestone:
Human-led` does not keep a leaf out of the queue.

This is undocumented, and the docs lean the other way —
`docs/roadmap-authoring.md` calls `execution_milestone` a "milestone-level
**gate**", and `docs/dev-workflow.md` files "Human-led gate decisions" under
human responsibilities. An adopter reading those would reasonably expect it to
block pickup.

**Fix:** say in `-h` and in `roadmap-authoring.md` that `execution_milestone` is
advisory metadata and `type: gate` is the enforcing mechanism. Stop calling it a
gate.

### `--push` does not open the PR

By design, and deliberately so:
[`work_artifact_rel_paths`](../../specy_road/finish_work_artifacts.py) documents
that "finish-this-task has no hook for 'the PR was opened'", which is why the
`work/pr-body-*.md` snapshot is excluded from cleanup. The printed
`gh pr create --body-file …` line is correct and pasteable.

That said, `--on-complete pr` plus an authenticated `gh` is the common case in an
autonomous loop, and shelling out to `gh`/`glab` when available would close it.
Reasonable **feature request**, not a defect.

### `finish-this-task` deletes `work/implementation-summary-<id>.md`

By design, controlled by `cleanup_work_artifacts_on_finish` in
`roadmap/git-workflow.yaml` and `--no-cleanup-work`. The surprise is fair, and
there is a sharper edge the report missed: `_maybe_write_pr_body` skips the
snapshot when `on_complete` is **`merge`** (see
[`pr_body_modes`](../../specy_road/finish_pr_body.py)), so on the merge path the
summary is deleted with no snapshot at all. It survives in git history — the
scaffold `.gitignore` deliberately tracks `work/implementation-summary-*.md`
and the deletion is committed — but it leaves the working tree with nothing.

**Fix:** either write the snapshot on all modes, or exclude the
implementation summary from default cleanup. Deleting the one dev-authored
artifact by default is a poor default regardless of recoverability.

## 5. Not a defect: chunk-cap overflow already has a remedy

The report says the 500-line chunk cap left "hand-editing JSON to split the M10
subtree" as the only option. `specy-road rebalance-chunks` does exactly that
job, deterministically, including the manifest update:

```
$ specy-road validate
roadmap line limit: roadmap/phases/M2.json: 40 lines (max 25); split or reduce to a single node per file
$ specy-road rebalance-chunks
  ~ roadmap/phases/M2.json  (1 nodes)
  + roadmap/phases/M2__46fcad.json  (1 nodes)
  + roadmap/phases/M2__9387ea.json  (1 nodes)
  manifest includes: 5 entries
OK: roadmap and registry validate.
```

This is a **discoverability defect**, not a missing feature. The line-limit
error says "split or reduce to a single node per file" and never names the
command that does it.

**Fix:** name `specy-road rebalance-chunks` in the line-limit error from
[`validate_roadmap_line_limits`](../../specy_road/bundled_scripts/roadmap_load.py).
A subtree-aware `move-node --chunk` is a separate, lower-priority request; note
that `move_node_outline` already exists for reparenting but is GUI-only.

## 6. Remaining papercuts

- **`list-nodes` shows raw status in an unlabelled column** — confirmed, and it
  contradicts `roadmap.md` for every parent node (`M1  phase  Not Started` next
  to `roadmap.md`'s `Complete`). Add a header row and a `rollup` column, or show
  rollup with the raw value in parentheses. This is the same two-model problem
  as §2 and should be fixed with it.
- **Top-level `--help` omits `--on-complete`** for
  `do-next-available-task` — confirmed against `_USAGE_TEXT` in
  [`cli.py`](../../specy_road/cli.py); the flag exists and works.
- **`add-node` prints `OK: roadmap and registry validate.` on stdout** —
  `run_validate_raise` redirects only stderr, so every mutation command leaks a
  validation success line into its own output. Harmless, but it is what makes
  `add-node` output look self-contradictory, which may be what the reporter saw.
- **Stale planning prose is amplified by `brief`** — correct, and consumer data.
  `collect_planning_artifact_errors` checks sheet naming, existence, and
  orphans, not node ids referenced in prose. A `validate` check that node ids
  cited inside a sheet resolve is a cheap, high-value addition; treat it as a
  feature request.

## Recommendation for `0.1.4`

**Ship-blocking:**

1. Make `edit-node` (and the GUI paths that share it) atomic — §1a.
2. Roll back the planning sheet on failed `add-node` — §1b.
3. Resolve the own-status / rollup split-brain, and restore a `validate`
   warning for the disagreement — §2.

**Strongly recommended in the same release,** because each is small and each is
a trap an autonomous run walks into:

4. `refresh-schemas` plus a schema-drift warning — §3.
5. Name `rebalance-chunks` in the line-limit error — §5.
6. Print the picked leaf's status, and document Blocked-first and advisory
   `execution_milestone` in `-h` — §4.

**Defer:** opening the PR from `--push`, `move-node --chunk`, an
`externally_blocked` marker, planning-sheet node-id validation, `list-nodes`
formatting.

**Confirm with the adopter first:** which build the grind actually ran against
(§0). If it was `v0.1.3`, re-run the grind on rc2 before we call the report
closed — rc2 changed the phase-status behaviour they were relying on.
