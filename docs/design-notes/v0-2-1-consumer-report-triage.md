# Triage: `v0.2.1-rc2` consumer report (mckee_ui)

> **Outcome:** all seven new findings were fixed in **`v0.2.2`**. See the
> [CHANGELOG](../../CHANGELOG.md) entry for that release.

Assessment of the consumer report written after running four real leaves through
the toolkit on a live integration branch in a 100-node consumer repo (M0–M16,
`on_complete: pr`): two through `grind-session --on-complete merge --push --json`
unattended with no TTY, and two through `do-next-available-task --under LEAF` →
`finish-this-task --push` → the printed `gh pr create` line.

The rc1 findings the report re-tested (init `--force` no longer destroying
`CLAUDE.md`, codename preservation on title edits, `move-node`, `history
--reverse`, the honest PR pointer, `--version` exiting 2) are confirmed fixed and
are not revisited here.

## Summary

| # | Finding | Call | Fixed by |
|---|---|---|---|
| 20 | `finish-this-task` runs validate and export but not digest | **Defect** | finish and sync run all three, and stage `roadmap-context.md` |
| 21 | Session ends on the last feature branch; merged branches left behind | **Defect + feature** | Return to the integration branch; `--delete-merged-branches` |
| 22 | `--plan` "Dispatch now" order ≠ the order the loop picks | **Defect** | Batches follow pickup order; waves stay id-sorted |
| 23 | `--json` is not clean JSONL; events have no timestamp | **Defect** | Child stdout to stderr in JSON mode; `ts` on every event |
| 24 | `show-node` prints a comment line before the JSON | **Defect** | Chunk path to stderr; stdout is pure JSON |
| 25 | No warning when a generated-and-committed file is gitignored | **Feature** | `validate` warns; finish skips staging it |
| 26 | Touch zones are not validated against the working tree | **Feature** | `validate` warns on a zone matching nothing |

## 20. digest was left out of the bookkeeping commit

The self-contradiction was real and was the one thing worth blocking on: the
toolkit's own help, the scaffolded `.gitignore`, the CI workflow and four
suggested prompts all say to gate CI on `digest --check`, while the command that
closes a task refreshed `roadmap.md` and not `roadmap-context.md`. Every finish
handed CI a failure the dev never saw.

`finish-this-task` and `sync` now run `validate`, `export` and `digest`, and the
bookkeeping commit stages both generated files. Pickup was deliberately left
alone: its registry claim drifts the digest only mid-task on the feature branch,
and finish repairs that before the merge.

## 21. Where a session leaves you

`finish-this-task` checks the feature branch back out after landing a merge, and
that is right for one task done by hand — the dev is still working there. It is
wrong for a loop that merged a dozen leaves and has nobody watching. The loop now
returns to the integration branch when it stops on its own terms.

Deletion is opt-in (`--delete-merged-branches`) rather than automatic, and it is
guarded by `git merge-base --is-ancestor`. That guard is load-bearing: `finish
--push` gives the branch an upstream, so `git branch -d` only checks
merged-into-upstream and would delete a branch that never reached the integration
branch — exactly what `auto` mode leaves behind when it falls back to a PR, since
that path still exits 0.

Neither behaviour runs after a failed cycle: a failure must leave the feature
branch exactly as it was.

## 22. Two orders, one report

`--plan` rendered `parallel_batches` from the wave layering, which is sorted by
id so the wave listing reads predictably. The loop consumes `plan.ready`, which
is pickup order: tier first, then roadmap outline (sibling) order. Both were
correct in isolation and disagreed on screen. Batches now follow pickup order;
waves keep their id sort. The `--plan --json` `ready` array was already right.

## 23. JSONL and timestamps

The sub-CLIs inherit grind's stdout, so the pickup banner, the finish log and git
landed between the events. In `--json` mode child stdout now goes to stderr —
redirected at the file-descriptor level, so output still streams — and every
event carries `ts` (UTC, to the second) right after `event`.

## 24. `show-node`

One line, printed before the JSON, in a command the IDE stub describes as "Show
one roadmap node as JSON". Moved to stderr rather than hidden behind a flag: the
provenance is still visible in a terminal, and no caller has to opt in to the
behaviour the command already advertised.

## 25. Generated *and* committed

`roadmap.md` and `roadmap-context.md` are both generated and both committed, which
is unusual enough that adopters gitignore them. Local `digest --check` then passes
while a fresh clone and CI see nothing. `validate` now says so.

Detection uses `git check-ignore --no-index`: plain `check-ignore` stays silent
once a file is tracked, which is precisely the case that needs reporting. The
same check guards staging in finish, because `git add` of an ignored path aborts
the whole bookkeeping commit.

## 26. Touch zones against the working tree

Two PM-authored zones named files that were never created. The brief's §7
"confirm touch zones" TODO caught them, as designed — but at implementation time,
which is late. `validate` now warns when a zone on an open node matches nothing
on disk, as a path or as a glob. Settled nodes are skipped: work that landed and
files since renamed is not a mistake anyone should act on.

The dogfood fixture had the same defect (node `M0.2` pointed at toolkit paths
that do not exist inside the fixture tree) and was corrected in the same change.

## Not changed

- **`specy-road version`** still exits 2 rather than printing the version;
  `--version` is the documented spelling and works.
- **The `pr`-mode refusal**, the phase auto-flip declining to fire on a phase
  with an open gate, and the stale-stub warning were all called correct by the
  report and are untouched.
